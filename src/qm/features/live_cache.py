"""Live feature computation cache with thread-safe tick buffering.

Provides the production inference path for real-time trading:
1. Receives ticks from websocket feed
2. Accumulates them in a thread-safe ring buffer
3. On demand, computes features via IntraBarFeatureCalculator
4. Reorders features to match the saved model's feature_names_ order
5. Returns feature vector ready for CompiledPredictor.predict()

Uses the Rust FeatureCalculator from qm_fast when available (< 0.01ms).
Falls back to Python IntraBarFeatureCalculator if Rust module not built.

Usage:
    from qm.features.live_cache import LiveFeatureCache

    cache = LiveFeatureCache.from_model_dir(
        Path("data/models/pulse_v2/ETH_5m"),
        asset=Asset.ETH,
        timeframe=Timeframe.M5,
    )
    # On each bar completion, feed Sentinel pipeline features:
    cache.update_history({"rsi_14": 35.2, "stoch_k": 22.5, ...})
    # On each tick at t >= 0.80:
    cache.on_tick(price=3450.12, size=0.5, timestamp=now)
    # Get prediction-ready feature vector:
    features = cache.get_features(partial_bar)  # np.ndarray matching model order
"""

from __future__ import annotations

import collections
import logging
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Deque

import numpy as np

from qm.core.types import Asset, PartialBar, Timeframe

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Rust / Python fallback (preserved from original skeleton)
# ---------------------------------------------------------------------------

try:
    from qm_fast import FeatureCalculator as RustFeatureCalculator
    from qm_fast import L2Orderbook as RustL2Orderbook
    from qm_fast import RingBuffer as RustRingBuffer

    RUST_AVAILABLE = True
    logger.info("qm_fast Rust module loaded -- using Rust hot path")
except ImportError:
    RUST_AVAILABLE = False
    logger.info("qm_fast not available -- using Python fallback")


def get_feature_calculator():
    """Return the best available feature calculator.

    Returns Rust FeatureCalculator if qm_fast is installed,
    otherwise returns Python IntraBarFeatureCalculator.
    """
    if RUST_AVAILABLE:
        return RustFeatureCalculator()

    from qm.features.intrabar import IntraBarFeatureCalculator

    return IntraBarFeatureCalculator()


def get_orderbook():
    """Return the best available orderbook implementation."""
    if RUST_AVAILABLE:
        return RustL2Orderbook()
    return None  # no Python fallback for orderbook


def get_ring_buffer(capacity: int):
    """Return Rust RingBuffer if available."""
    if RUST_AVAILABLE:
        return RustRingBuffer(capacity)
    return None


# ---------------------------------------------------------------------------
# Thread-safe tick ring buffer
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class Tick:
    """A single trade tick."""

    price: float
    size: float
    timestamp: float  # Unix timestamp (seconds)


class TickRingBuffer:
    """Thread-safe ring buffer for accumulating ticks within a bar window.

    Fixed capacity -- oldest ticks are evicted when full. All operations
    are O(1). Thread safety via a single lock (ticks arrive from websocket
    thread, features are read from trading loop thread).
    """

    def __init__(self, capacity: int = 10_000) -> None:
        self._capacity = capacity
        self._buffer: Deque[Tick] = collections.deque(maxlen=capacity)
        self._lock = threading.Lock()
        self._total_volume: float = 0.0
        self._total_count: int = 0

    def push(self, price: float, size: float, timestamp: float) -> None:
        """Add a tick. Thread-safe."""
        with self._lock:
            if len(self._buffer) == self._capacity:
                evicted = self._buffer[0]
                self._total_volume -= evicted.size
                self._total_count -= 1
            self._buffer.append(Tick(price=price, size=size, timestamp=timestamp))
            self._total_volume += size
            self._total_count += 1

    def clear(self) -> None:
        """Reset for a new bar window. Thread-safe."""
        with self._lock:
            self._buffer.clear()
            self._total_volume = 0.0
            self._total_count = 0

    def snapshot(self) -> tuple[list[Tick], float, int]:
        """Return (ticks_copy, total_volume, total_count). Thread-safe."""
        with self._lock:
            return list(self._buffer), self._total_volume, self._total_count

    @property
    def count(self) -> int:
        with self._lock:
            return self._total_count

    @property
    def volume(self) -> float:
        with self._lock:
            return self._total_volume

    @property
    def latest_price(self) -> float | None:
        with self._lock:
            if self._buffer:
                return self._buffer[-1].price
            return None

    def ohlcv_snapshot(self) -> dict[str, float] | None:
        """Compute OHLCV summary from buffered ticks. Thread-safe.

        Returns None if buffer is empty.
        """
        with self._lock:
            if not self._buffer:
                return None
            o = self._buffer[0].price
            h = max(t.price for t in self._buffer)
            l = min(t.price for t in self._buffer)  # noqa: E741
            c = self._buffer[-1].price
            return {
                "open": o,
                "high": h,
                "low": l,
                "close": c,
                "volume": self._total_volume,
                "trade_count": self._total_count,
            }


# ---------------------------------------------------------------------------
# Feature order mapper
# ---------------------------------------------------------------------------

def _load_model_feature_order(model_dir: Path) -> list[str]:
    """Load the canonical feature order from a saved LightGBM model.

    This is the ONLY source of truth for feature ordering. Mismatched
    feature order is a silent correctness failure -- the model will
    produce garbage predictions without raising any error.
    """
    model_path = model_dir / "model.lgb"
    if not model_path.exists():
        raise FileNotFoundError(
            f"No model.lgb found at {model_path}. "
            "Cannot determine feature order for live inference."
        )

    import lightgbm as lgb

    booster = lgb.Booster(model_file=str(model_path))
    names = booster.feature_name()
    logger.info(
        "Loaded feature order from %s: %d features", model_path, len(names)
    )
    return names


def _build_reorder_indices(
    source_names: list[str], target_names: list[str]
) -> np.ndarray:
    """Build index array to reorder source features to match target order.

    source_names: feature names as produced by IntraBarFeatureCalculator
    target_names: feature names as required by the saved model

    Returns int array where result[i] = index in source for target[i].
    Raises ValueError if any target feature is missing from source.
    """
    source_index = {name: i for i, name in enumerate(source_names)}
    indices = []
    missing = []
    for name in target_names:
        if name in source_index:
            indices.append(source_index[name])
        else:
            missing.append(name)

    if missing:
        raise ValueError(
            f"Model requires {len(missing)} features not produced by "
            f"IntraBarFeatureCalculator: {missing}"
        )

    return np.array(indices, dtype=np.intp)


# ---------------------------------------------------------------------------
# LiveFeatureCache -- the main production class
# ---------------------------------------------------------------------------

class LiveFeatureCache:
    """Thread-safe live feature cache for production inference.

    Wraps IntraBarFeatureCalculator with:
    - A TickRingBuffer for accumulating websocket trades
    - Automatic feature reordering to match saved model's feature_names_
    - History cache updates from Sentinel pipeline bar completions
    - Readiness gating (no predictions until first bar completes)

    One instance per (asset, timeframe) pair.
    """

    def __init__(
        self,
        asset: Asset,
        timeframe: Timeframe,
        model_feature_order: list[str],
        tick_buffer_capacity: int = 10_000,
    ) -> None:
        self._asset = asset
        self._timeframe = timeframe
        self._tick_buffer = TickRingBuffer(capacity=tick_buffer_capacity)

        # Feature calculator (Rust or Python)
        self._calculator = get_feature_calculator()
        self._is_rust = RUST_AVAILABLE and not isinstance(
            self._calculator,
            __import__(
                "qm.features.intrabar", fromlist=["IntraBarFeatureCalculator"]
            ).IntraBarFeatureCalculator,
        )

        # Build reorder map: calculator output -> model expected order
        # Handle both property (Python) and method (Rust) interfaces
        names_attr = self._calculator.feature_names
        calc_names = names_attr() if callable(names_attr) else names_attr
        self._reorder_idx = _build_reorder_indices(calc_names, model_feature_order)
        self._n_features = len(model_feature_order)
        self._model_feature_order = model_feature_order

        # Bar window tracking
        self._bar_open_price: float | None = None
        self._bar_window_start: datetime | None = None
        self._bar_window_end: datetime | None = None

        logger.info(
            "LiveFeatureCache initialized for %s/%s: %d features, "
            "tick buffer capacity %d",
            asset.value,
            timeframe.value,
            self._n_features,
            tick_buffer_capacity,
        )

    @classmethod
    def from_model_dir(
        cls,
        model_dir: Path,
        asset: Asset,
        timeframe: Timeframe,
        tick_buffer_capacity: int = 10_000,
    ) -> "LiveFeatureCache | CrossAssetLiveFeatureCache":
        """Create a LiveFeatureCache using feature order from a saved model.

        Auto-detects cross-asset models: if the model's feature_names_
        contain ``btc_*`` features and asset is not BTC, returns a
        ``CrossAssetLiveFeatureCache`` that manages a parallel BTC
        feature calculator.

        Args:
            model_dir: Directory containing model.lgb (and optionally model.treelite).
            asset: Trading asset.
            timeframe: Bar timeframe.
            tick_buffer_capacity: Max ticks to buffer per bar window.
        """
        feature_order = _load_model_feature_order(model_dir)
        btc_features = [f for f in feature_order if f.startswith("btc_")]

        if btc_features and asset != Asset.BTC:
            # Cross-asset model: build primary cache without btc_* features,
            # then wrap with CrossAssetLiveFeatureCache
            non_btc_order = [f for f in feature_order if not f.startswith("btc_")]
            primary = cls(
                asset=asset, timeframe=timeframe,
                model_feature_order=non_btc_order,
                tick_buffer_capacity=tick_buffer_capacity,
            )
            from qm.features.intrabar import IntraBarFeatureCalculator
            btc_calc = IntraBarFeatureCalculator()
            return CrossAssetLiveFeatureCache(
                primary_cache=primary,
                btc_calculator=btc_calc,
                cross_feature_names=btc_features,
                model_feature_order=feature_order,
            )

        return cls(
            asset=asset,
            timeframe=timeframe,
            model_feature_order=feature_order,
            tick_buffer_capacity=tick_buffer_capacity,
        )

    # ----- Tick ingestion (called from websocket thread) -----

    def on_tick(self, price: float, size: float, timestamp: float) -> None:
        """Record a trade tick. Thread-safe.

        Args:
            price: Trade price.
            size: Trade size (base currency).
            timestamp: Unix timestamp in seconds.
        """
        self._tick_buffer.push(price, size, timestamp)

    def new_bar_window(
        self,
        window_start: datetime,
        window_end: datetime,
        open_price: float,
    ) -> None:
        """Signal the start of a new bar window. Clears the tick buffer.

        Called when the previous bar completes and a new bar window begins.
        """
        self._tick_buffer.clear()
        self._bar_window_start = window_start
        self._bar_window_end = window_end
        self._bar_open_price = open_price

    # ----- History cache (called from Sentinel pipeline on bar completion) -----

    def update_history(self, features: dict[str, float]) -> None:
        """Update cached historical features from last completed bar.

        Called once per bar completion with Sentinel pipeline output.
        Thread-safe (IntraBarFeatureCalculator.update_cache is dict assignment).
        """
        asset_key = self._asset.value if self._is_rust else self._asset
        self._calculator.update_cache(asset_key, features)

    @property
    def is_ready(self) -> bool:
        """True when history cache has real data (not just defaults)."""
        asset_key = self._asset.value if self._is_rust else self._asset
        return self._calculator.is_ready(asset_key)

    # ----- Feature computation (called from trading loop at t=0.80) -----

    def _compute_raw(self, partial_bar: PartialBar) -> np.ndarray:
        """Call the underlying calculator, adapting for Rust vs Python interface."""
        if self._is_rust:
            result = self._calculator.compute(
                partial_bar.asset.value,
                partial_bar.open,
                partial_bar.high_so_far,
                partial_bar.low_so_far,
                partial_bar.current_price,
                partial_bar.volume_so_far,
                partial_bar.trade_count,
                partial_bar.elapsed_seconds,
                partial_bar.remaining_seconds,
            )
            return np.array(result, dtype=np.float64)
        else:
            # Python interface: PartialBar object
            return self._calculator.compute(partial_bar)

    def get_features(self, partial_bar: PartialBar) -> np.ndarray:
        """Compute features for the current bar snapshot.

        Returns np.ndarray of shape (n_features,) in model-expected order.
        This is the hot path -- must be < 1ms.
        """
        raw = self._compute_raw(partial_bar)
        # Reorder to match model's feature_names_
        return raw[self._reorder_idx]

    def get_features_2d(self, partial_bar: PartialBar) -> np.ndarray:
        """Compute features as (1, n_features) array for model.predict().

        Convenience wrapper that reshapes for direct use with
        CompiledPredictor.predict() or lgb.Booster.predict().
        """
        return self.get_features(partial_bar).reshape(1, -1)

    def build_partial_bar(self) -> PartialBar | None:
        """Build a PartialBar from the current tick buffer state.

        Returns None if no ticks or no bar window has been set.
        This builds a PartialBar from accumulated ticks without
        needing an external BarBuilder -- useful for the live path
        where ticks arrive directly to this cache.
        """
        if self._bar_window_start is None or self._bar_open_price is None:
            return None

        snapshot = self._tick_buffer.ohlcv_snapshot()
        if snapshot is None:
            return None

        now = time.time()
        start_ts = self._bar_window_start.timestamp()
        end_ts = self._bar_window_end.timestamp() if self._bar_window_end else start_ts + 300
        elapsed = max(0.0, now - start_ts)
        remaining = max(0.0, end_ts - now)

        return PartialBar(
            window_start=self._bar_window_start,
            window_end=self._bar_window_end,
            asset=self._asset,
            timeframe=self._timeframe,
            open=self._bar_open_price,
            high_so_far=snapshot["high"],
            low_so_far=snapshot["low"],
            current_price=snapshot["close"],
            volume_so_far=snapshot["volume"],
            trade_count=int(snapshot["trade_count"]),
            elapsed_seconds=elapsed,
            remaining_seconds=remaining,
        )

    # ----- Diagnostics -----

    @property
    def asset(self) -> Asset:
        return self._asset

    @property
    def timeframe(self) -> Timeframe:
        return self._timeframe

    @property
    def n_features(self) -> int:
        return self._n_features

    @property
    def model_feature_order(self) -> list[str]:
        return list(self._model_feature_order)

    @property
    def tick_count(self) -> int:
        return self._tick_buffer.count

    @property
    def tick_volume(self) -> float:
        return self._tick_buffer.volume

    def __repr__(self) -> str:
        return (
            f"LiveFeatureCache("
            f"asset={self._asset.value}, "
            f"timeframe={self._timeframe.value}, "
            f"features={self._n_features}, "
            f"ready={self.is_ready}, "
            f"ticks={self.tick_count})"
        )


# ---------------------------------------------------------------------------
# Cross-asset live feature cache (BTC context for non-BTC models)
# ---------------------------------------------------------------------------


class CrossAssetLiveFeatureCache:
    """Wraps a primary LiveFeatureCache + BTC context calculator.

    For models trained with cross-asset BTC features, this cache computes
    the primary asset's features AND BTC tick features, concatenates them,
    and reorders to match the saved model's feature_names_.

    Two usage modes:

    **Live** (trade.py): Feed BTC ticks via ``on_context_tick()``. BTC
    features are computed from the parallel tick buffer.

    **Backtest** (dutch_backtest.py): Inject a prebuilt BTC PartialBar
    via ``set_btc_partial()``. No tick buffer needed.
    """

    def __init__(
        self,
        primary_cache: LiveFeatureCache,
        btc_calculator: object,
        cross_feature_names: list[str],
        model_feature_order: list[str],
    ) -> None:
        self._primary = primary_cache
        self._btc_calc = btc_calculator
        self._btc_tick_buffer = TickRingBuffer(capacity=5_000)
        self._cross_names = cross_feature_names

        # Map btc_* names to indices in BTC calculator output
        from qm.features.cross_asset_intrabar import CROSS_ASSET_TICK_MAP
        from qm.features.intrabar import TICK_FEATURE_NAMES

        self._btc_source_indices: list[int] = []
        for name in cross_feature_names:
            source = CROSS_ASSET_TICK_MAP[name]
            self._btc_source_indices.append(TICK_FEATURE_NAMES.index(source))

        # Build reorder: [primary_calc_features + btc_features] → model order
        calc_names = primary_cache._calculator.feature_names
        if callable(calc_names):
            calc_names = calc_names()
        combined = list(calc_names) + list(cross_feature_names)
        self._reorder_idx = _build_reorder_indices(combined, model_feature_order)
        self._n_features = len(model_feature_order)
        self._model_feature_order = list(model_feature_order)

        # BTC bar state (live path)
        self._btc_open: float | None = None
        self._btc_bar_start: datetime | None = None
        self._btc_bar_end: datetime | None = None
        self._btc_last_tick_time: float = 0.0

        # BTC partial override (backtest path)
        self._btc_partial_override: PartialBar | None = None

        logger.info(
            "CrossAssetLiveFeatureCache: %s/%s + %d BTC features, %d total",
            primary_cache._asset.value,
            primary_cache._timeframe.value,
            len(cross_feature_names),
            self._n_features,
        )

    # ----- BTC tick ingestion (live path) -----

    def on_context_tick(
        self, price: float, size: float, timestamp: float
    ) -> None:
        """Feed BTC ticks from parallel price stream."""
        self._btc_tick_buffer.push(price, size, timestamp)
        self._btc_last_tick_time = timestamp

    def new_btc_bar(
        self, open_price: float, start: datetime, end: datetime
    ) -> None:
        """Signal start of a new BTC bar window."""
        self._btc_tick_buffer.clear()
        self._btc_open = open_price
        self._btc_bar_start = start
        self._btc_bar_end = end

    def update_btc_history(self, features: dict[str, float]) -> None:
        """Update BTC historical features on BTC bar completion."""
        self._btc_calc.update_cache(Asset.BTC, features)

    # ----- BTC partial override (backtest path) -----

    def set_btc_partial(self, btc_partial: PartialBar | None) -> None:
        """Inject BTC PartialBar directly (backtest replay path).

        When set, ``get_features()`` uses this instead of the tick buffer.
        Set to ``None`` to revert to tick buffer mode.
        """
        self._btc_partial_override = btc_partial

    # ----- Feature computation -----

    def _build_btc_partial(self) -> PartialBar | None:
        """Build BTC PartialBar from tick buffer (live path)."""
        snapshot = self._btc_tick_buffer.ohlcv_snapshot()
        if snapshot is None or self._btc_open is None:
            return None

        import time as _time

        now = _time.time()
        start_ts = (
            self._btc_bar_start.timestamp()
            if self._btc_bar_start
            else now
        )
        end_ts = (
            self._btc_bar_end.timestamp()
            if self._btc_bar_end
            else start_ts + 300
        )

        return PartialBar(
            window_start=self._btc_bar_start,
            window_end=self._btc_bar_end,
            asset=Asset.BTC,
            timeframe=self._primary._timeframe,
            open=self._btc_open,
            high_so_far=snapshot["high"],
            low_so_far=snapshot["low"],
            current_price=snapshot["close"],
            volume_so_far=snapshot["volume"],
            trade_count=int(snapshot["trade_count"]),
            elapsed_seconds=max(0.0, now - start_ts),
            remaining_seconds=max(0.0, end_ts - now),
        )

    def get_features(self, partial_bar: PartialBar) -> np.ndarray:
        """Compute primary + BTC cross-asset features, reorder to model order.

        Uses ``set_btc_partial()`` override if set (backtest), otherwise
        builds BTC PartialBar from tick buffer (live).
        """
        primary_raw = self._primary._compute_raw(partial_bar)

        # Get BTC partial: override (backtest) or tick buffer (live)
        btc_partial = self._btc_partial_override or self._build_btc_partial()
        if btc_partial is not None:
            btc_raw = self._btc_calc.compute(btc_partial)
            btc_feats = np.asarray(btc_raw)[self._btc_source_indices]
        else:
            btc_feats = np.zeros(len(self._btc_source_indices))
            # Staleness check (live path only)
            if self._btc_last_tick_time > 0:
                import time as _time

                stale = _time.time() - self._btc_last_tick_time
                if stale > 30:
                    logger.warning("BTC context stale: %.0fs since last tick", stale)

        combined = np.concatenate([primary_raw, btc_feats])
        return combined[self._reorder_idx]

    def get_features_2d(self, partial_bar: PartialBar) -> np.ndarray:
        """Compute features as (1, n_features) array for model.predict()."""
        return self.get_features(partial_bar).reshape(1, -1)

    # ----- Delegate primary-asset interface -----

    def on_tick(self, price: float, size: float, timestamp: float) -> None:
        self._primary.on_tick(price, size, timestamp)

    def new_bar_window(
        self, window_start: datetime, window_end: datetime, open_price: float
    ) -> None:
        self._primary.new_bar_window(window_start, window_end, open_price)

    def update_history(self, features: dict[str, float]) -> None:
        self._primary.update_history(features)

    def build_partial_bar(self) -> PartialBar | None:
        return self._primary.build_partial_bar()

    @property
    def is_ready(self) -> bool:
        return self._primary.is_ready

    @property
    def asset(self) -> Asset:
        return self._primary.asset

    @property
    def timeframe(self) -> Timeframe:
        return self._primary.timeframe

    @property
    def n_features(self) -> int:
        return self._n_features

    @property
    def model_feature_order(self) -> list[str]:
        return list(self._model_feature_order)

    @property
    def tick_count(self) -> int:
        return self._primary.tick_count

    @property
    def tick_volume(self) -> float:
        return self._primary.tick_volume

    def __repr__(self) -> str:
        return (
            f"CrossAssetLiveFeatureCache("
            f"asset={self._primary._asset.value}, "
            f"timeframe={self._primary._timeframe.value}, "
            f"features={self._n_features}, "
            f"btc_features={len(self._cross_names)}, "
            f"ready={self.is_ready})"
        )
