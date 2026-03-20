"""Builds OHLCV bars from raw trade streams.

Constructs bars from individual trades rather than relying on exchange-provided
bars. This ensures precise alignment to Polymarket window boundaries and
consistent aggregation across exchanges.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone

from qm.core.constants import TIMEFRAME_MINUTES
from qm.core.types import Asset, Bar, PartialBar, Timeframe
from qm.data.ingestion.bar_aligner import BarAligner

logger = logging.getLogger(__name__)


@dataclass
class _BarAccumulator:
    """Accumulates trades within a single bar window."""

    window_start: datetime
    window_end: datetime
    open: float = 0.0
    high: float = float("-inf")
    low: float = float("inf")
    close: float = 0.0
    volume: float = 0.0
    trade_count: int = 0
    vwap_numerator: float = 0.0  # sum(price * volume)
    is_initialized: bool = False

    def update(self, price: float, size: float) -> None:
        if not self.is_initialized:
            self.open = price
            self.is_initialized = True
        self.high = max(self.high, price)
        self.low = min(self.low, price)
        self.close = price
        self.volume += size
        self.trade_count += 1
        self.vwap_numerator += price * size

    @property
    def vwap(self) -> float:
        if self.volume == 0:
            return self.close
        return self.vwap_numerator / self.volume

    def to_bar(self, asset: Asset, timeframe: Timeframe) -> Bar:
        return Bar(
            timestamp=self.window_start,
            asset=asset,
            timeframe=timeframe,
            open=self.open,
            high=self.high if self.high != float("-inf") else self.open,
            low=self.low if self.low != float("inf") else self.open,
            close=self.close,
            volume=self.volume,
            trade_count=self.trade_count,
            vwap=self.vwap,
        )

    def reset(self, window_start: datetime, window_end: datetime) -> None:
        self.window_start = window_start
        self.window_end = window_end
        self.open = 0.0
        self.high = float("-inf")
        self.low = float("inf")
        self.close = 0.0
        self.volume = 0.0
        self.trade_count = 0
        self.vwap_numerator = 0.0
        self.is_initialized = False


@dataclass
class _AssetBarState:
    """Per-asset, per-timeframe bar accumulation state."""

    accumulators: dict[Timeframe, _BarAccumulator] = field(default_factory=dict)


class BarBuilder:
    """Builds OHLCV bars from raw trades for multiple assets and timeframes.

    On each trade:
    1. Determine which bar window(s) the trade belongs to
    2. If the trade crosses a window boundary, close the current bar and emit it
    3. Accumulate the trade into the current (or new) bar

    Returns completed bars. Callers should persist them and broadcast BarCompleted events.
    """

    def __init__(
        self,
        assets: list[Asset],
        timeframes: list[Timeframe],
    ) -> None:
        self._aligner = BarAligner()
        self._timeframes = timeframes
        self._state: dict[Asset, _AssetBarState] = {
            asset: _AssetBarState() for asset in assets
        }

    def on_trade(
        self,
        asset: Asset,
        price: float,
        size: float,
        timestamp: datetime,
    ) -> list[Bar]:
        """Process a single trade. Returns list of completed bars (0, 1, or more).

        A bar is completed when a trade arrives that belongs to the NEXT window,
        meaning the previous window's bar is done.
        """
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)

        completed: list[Bar] = []
        state = self._state[asset]

        for tf in self._timeframes:
            minutes = TIMEFRAME_MINUTES[tf]
            window_start, window_end = self._aligner.get_window(timestamp, minutes)

            acc = state.accumulators.get(tf)

            if acc is None:
                # First trade for this asset/timeframe — initialize accumulator
                acc = _BarAccumulator(
                    window_start=window_start,
                    window_end=window_end,
                )
                state.accumulators[tf] = acc
                acc.update(price, size)
                continue

            if timestamp >= acc.window_end:
                # Trade is in a new window — close the current bar
                if acc.is_initialized:
                    completed.append(acc.to_bar(asset, tf))

                # Handle gap: if trade skips multiple windows, emit empty bars
                # (optional — for now just jump to the new window)
                acc.reset(window_start, window_end)
                acc.update(price, size)
            else:
                # Trade is in the current window — accumulate
                acc.update(price, size)

        return completed

    def get_partial_bar(
        self,
        asset: Asset,
        timeframe: Timeframe,
        now: datetime | None = None,
    ) -> PartialBar | None:
        """Non-blocking snapshot of the in-progress bar accumulator.

        Args:
            asset: Which asset to query.
            timeframe: Which timeframe accumulator.
            now: Explicit timestamp (for backtesting). Defaults to wall clock.

        Returns:
            PartialBar snapshot, or None if accumulator is uninitialized.
        """
        state = self._state.get(asset)
        if state is None:
            return None
        acc = state.accumulators.get(timeframe)
        if acc is None or not acc.is_initialized:
            return None
        ts = now or datetime.now(timezone.utc)
        # Bar has expired -- wait for next tick to flip to new window
        if ts >= acc.window_end:
            return None
        total_seconds = (acc.window_end - acc.window_start).total_seconds()
        elapsed = max(0.0, (ts - acc.window_start).total_seconds())
        remaining = total_seconds - elapsed
        return PartialBar(
            window_start=acc.window_start,
            window_end=acc.window_end,
            asset=asset,
            timeframe=timeframe,
            open=acc.open,
            high_so_far=acc.high if acc.high != float("-inf") else acc.open,
            low_so_far=acc.low if acc.low != float("inf") else acc.open,
            current_price=acc.close,
            volume_so_far=acc.volume,
            trade_count=acc.trade_count,
            elapsed_seconds=elapsed,
            remaining_seconds=remaining,
        )

    def flush(self, asset: Asset) -> list[Bar]:
        """Flush all in-progress bars for an asset (e.g., on disconnect).

        Returned bars are marked as potentially incomplete.
        """
        completed: list[Bar] = []
        state = self._state[asset]
        for tf, acc in state.accumulators.items():
            if acc.is_initialized:
                completed.append(acc.to_bar(asset, tf))
        return completed

    def flush_all(self) -> list[Bar]:
        """Flush all in-progress bars across all assets."""
        completed: list[Bar] = []
        for asset in self._state:
            completed.extend(self.flush(asset))
        return completed
