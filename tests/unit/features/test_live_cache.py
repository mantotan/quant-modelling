"""Tests for LiveFeatureCache -- thread-safe live inference feature cache."""

import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pytest

from qm.core.types import Asset, PartialBar, Timeframe
from qm.features.intrabar import ALL_FEATURE_NAMES
from qm.features.live_cache import (
    LiveFeatureCache,
    TickRingBuffer,
    _build_reorder_indices,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_partial(
    elapsed: float = 240.0,
    remaining: float = 60.0,
    open_price: float = 3400.0,
    current: float = 3420.0,
    high: float = 3430.0,
    low: float = 3390.0,
    volume: float = 100.0,
    trade_count: int = 500,
    asset: Asset = Asset.ETH,
) -> PartialBar:
    base = datetime(2026, 3, 20, 12, 0, 0, tzinfo=timezone.utc)
    return PartialBar(
        window_start=base,
        window_end=base,
        asset=asset,
        timeframe=Timeframe.M5,
        open=open_price,
        high_so_far=high,
        low_so_far=low,
        current_price=current,
        volume_so_far=volume,
        trade_count=trade_count,
        elapsed_seconds=elapsed,
        remaining_seconds=remaining,
    )


# ---------------------------------------------------------------------------
# TickRingBuffer tests
# ---------------------------------------------------------------------------

class TestTickRingBuffer:
    def test_empty_buffer(self):
        buf = TickRingBuffer(capacity=100)
        assert buf.count == 0
        assert buf.volume == 0.0
        assert buf.latest_price is None
        assert buf.ohlcv_snapshot() is None

    def test_push_and_snapshot(self):
        buf = TickRingBuffer(capacity=100)
        buf.push(100.0, 1.0, 1000.0)
        buf.push(102.0, 2.0, 1001.0)
        buf.push(99.0, 0.5, 1002.0)

        assert buf.count == 3
        assert buf.volume == pytest.approx(3.5)
        assert buf.latest_price == 99.0

        snap = buf.ohlcv_snapshot()
        assert snap is not None
        assert snap["open"] == 100.0
        assert snap["high"] == 102.0
        assert snap["low"] == 99.0
        assert snap["close"] == 99.0
        assert snap["volume"] == pytest.approx(3.5)
        assert snap["trade_count"] == 3

    def test_eviction_at_capacity(self):
        buf = TickRingBuffer(capacity=3)
        buf.push(100.0, 1.0, 1000.0)
        buf.push(101.0, 1.0, 1001.0)
        buf.push(102.0, 1.0, 1002.0)
        # Buffer full, push one more
        buf.push(103.0, 1.0, 1003.0)
        assert buf.count == 3
        # Volume should be 3.0 (evicted first tick's 1.0, added new 1.0)
        # But total_count tracks all-time, let's check the deque
        ticks, vol, count = buf.snapshot()
        assert len(ticks) == 3
        assert ticks[0].price == 101.0  # first tick (100) evicted
        assert ticks[-1].price == 103.0

    def test_clear(self):
        buf = TickRingBuffer(capacity=100)
        buf.push(100.0, 1.0, 1000.0)
        buf.push(101.0, 2.0, 1001.0)
        buf.clear()
        assert buf.count == 0
        assert buf.volume == 0.0
        assert buf.latest_price is None

    def test_thread_safety(self):
        """Push from multiple threads, verify no crashes or data corruption."""
        buf = TickRingBuffer(capacity=1000)
        errors = []

        def writer(thread_id: int):
            try:
                for i in range(100):
                    buf.push(100.0 + i, 0.1, time.time())
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=writer, args=(i,)) for i in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        assert buf.count == 400  # 4 threads * 100 ticks


# ---------------------------------------------------------------------------
# Feature reorder tests
# ---------------------------------------------------------------------------

class TestBuildReorderIndices:
    def test_identity_reorder(self):
        names = ["a", "b", "c"]
        idx = _build_reorder_indices(names, names)
        np.testing.assert_array_equal(idx, [0, 1, 2])

    def test_reversed_reorder(self):
        source = ["a", "b", "c"]
        target = ["c", "b", "a"]
        idx = _build_reorder_indices(source, target)
        np.testing.assert_array_equal(idx, [2, 1, 0])

    def test_partial_reorder(self):
        source = ["a", "b", "c", "d"]
        target = ["d", "b"]
        idx = _build_reorder_indices(source, target)
        np.testing.assert_array_equal(idx, [3, 1])

    def test_missing_feature_raises(self):
        source = ["a", "b"]
        target = ["a", "b", "z"]
        with pytest.raises(ValueError, match="features not produced"):
            _build_reorder_indices(source, target)

    def test_actual_feature_names_identity(self):
        """Verify current IntraBarFeatureCalculator names reorder to themselves."""
        idx = _build_reorder_indices(ALL_FEATURE_NAMES, ALL_FEATURE_NAMES)
        assert len(idx) == len(ALL_FEATURE_NAMES)
        np.testing.assert_array_equal(idx, np.arange(len(ALL_FEATURE_NAMES)))


# ---------------------------------------------------------------------------
# LiveFeatureCache tests
# ---------------------------------------------------------------------------

class TestLiveFeatureCache:
    @pytest.fixture
    def cache(self) -> LiveFeatureCache:
        """Create a cache using the default feature order (no reordering needed)."""
        return LiveFeatureCache(
            asset=Asset.ETH,
            timeframe=Timeframe.M5,
            model_feature_order=list(ALL_FEATURE_NAMES),
            tick_buffer_capacity=1000,
        )

    def test_init(self, cache: LiveFeatureCache):
        assert cache.asset == Asset.ETH
        assert cache.timeframe == Timeframe.M5
        assert cache.n_features == len(ALL_FEATURE_NAMES)
        assert not cache.is_ready
        assert cache.tick_count == 0

    def test_on_tick(self, cache: LiveFeatureCache):
        cache.on_tick(3400.0, 1.0, time.time())
        cache.on_tick(3401.0, 0.5, time.time())
        assert cache.tick_count == 2
        assert cache.tick_volume == pytest.approx(1.5)

    def test_update_history_makes_ready(self, cache: LiveFeatureCache):
        assert not cache.is_ready
        cache.update_history({"rsi_14": 55.0, "rsi_7": 60.0})
        assert cache.is_ready

    def test_get_features_shape(self, cache: LiveFeatureCache):
        partial = _make_partial()
        features = cache.get_features(partial)
        assert features.shape == (len(ALL_FEATURE_NAMES),)
        assert features.dtype == np.float64

    def test_get_features_2d_shape(self, cache: LiveFeatureCache):
        partial = _make_partial()
        features = cache.get_features_2d(partial)
        assert features.shape == (1, len(ALL_FEATURE_NAMES))

    def test_feature_reordering(self):
        """Create cache with reversed feature order, verify features are reordered."""
        reversed_order = list(reversed(ALL_FEATURE_NAMES))
        cache = LiveFeatureCache(
            asset=Asset.ETH,
            timeframe=Timeframe.M5,
            model_feature_order=reversed_order,
            tick_buffer_capacity=100,
        )
        partial = _make_partial()

        # Get features from both the cache (reordered) and raw calculator
        from qm.features.intrabar import IntraBarFeatureCalculator

        raw_calc = IntraBarFeatureCalculator()
        raw_features = raw_calc.compute(partial)
        reordered_features = cache.get_features(partial)

        # Reversed: first element of reordered should equal last of raw
        np.testing.assert_array_almost_equal(
            reordered_features, raw_features[::-1]
        )

    def test_new_bar_window_clears_ticks(self, cache: LiveFeatureCache):
        cache.on_tick(3400.0, 1.0, time.time())
        cache.on_tick(3401.0, 0.5, time.time())
        assert cache.tick_count == 2

        now = datetime.now(tz=timezone.utc)
        cache.new_bar_window(
            window_start=now,
            window_end=now,
            open_price=3400.0,
        )
        assert cache.tick_count == 0

    def test_build_partial_bar_returns_none_without_window(self, cache: LiveFeatureCache):
        assert cache.build_partial_bar() is None

    def test_build_partial_bar_returns_none_without_ticks(self, cache: LiveFeatureCache):
        now = datetime.now(tz=timezone.utc)
        cache.new_bar_window(now, now, 3400.0)
        assert cache.build_partial_bar() is None

    def test_build_partial_bar_with_ticks(self, cache: LiveFeatureCache):
        now = datetime.now(tz=timezone.utc)
        cache.new_bar_window(now, now, 3400.0)
        ts = time.time()
        cache.on_tick(3400.0, 1.0, ts)
        cache.on_tick(3420.0, 2.0, ts + 1)
        cache.on_tick(3390.0, 0.5, ts + 2)

        pb = cache.build_partial_bar()
        assert pb is not None
        assert pb.asset == Asset.ETH
        assert pb.timeframe == Timeframe.M5
        assert pb.open == 3400.0
        assert pb.high_so_far == 3420.0
        assert pb.low_so_far == 3390.0
        assert pb.current_price == 3390.0
        assert pb.volume_so_far == pytest.approx(3.5)
        assert pb.trade_count == 3

    def test_repr(self, cache: LiveFeatureCache):
        r = repr(cache)
        assert "ETH" in r
        assert "5m" in r
        assert "features=" in r

    def test_model_feature_order_is_copy(self, cache: LiveFeatureCache):
        """Verify model_feature_order returns a copy, not a reference."""
        order1 = cache.model_feature_order
        order2 = cache.model_feature_order
        assert order1 == order2
        assert order1 is not order2


class TestLiveFeatureCacheFromModelDir:
    """Tests for from_model_dir class method (requires model files on disk)."""

    def test_missing_model_dir_raises(self, tmp_path: Path):
        with pytest.raises(FileNotFoundError, match="No model.lgb found"):
            LiveFeatureCache.from_model_dir(
                tmp_path / "nonexistent",
                asset=Asset.ETH,
                timeframe=Timeframe.M5,
            )
