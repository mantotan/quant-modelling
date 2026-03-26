"""Cumulative direction target: predict whether price is higher h bars later.

Unlike BinaryDirectionTarget which compares open/close of a single future
bar (noise), this compares close[t+h] to close[t] — capturing the
cumulative trend over multiple bars where signal survives averaging.

close[t] is the current price (known at prediction time — no leakage).
"""

from __future__ import annotations

import polars as pl


class CumulativeDirectionTarget:
    """Target: 1 if close[t+h] >= close[t], else 0.

    Captures multi-bar trend direction. Longer horizons have more trend
    signal and less microstructure noise.

    Args:
        horizon_bars: How many bars ahead to compare. For 5m bars:
            3 = 15 min, 6 = 30 min, 12 = 1 hour.
    """

    def __init__(self, horizon_bars: int = 3) -> None:
        if horizon_bars < 1:
            msg = f"horizon_bars must be >= 1, got {horizon_bars}"
            raise ValueError(msg)
        self.horizon_bars = horizon_bars

    def compute(self, bars: pl.DataFrame) -> pl.Series:
        """Compute cumulative direction target.

        Target: close[t+h] >= close[t]
        Last ``horizon_bars`` rows are null (no future data).
        """
        future_close = bars["close"].shift(-self.horizon_bars)
        current_close = bars["close"]
        return (future_close >= current_close).cast(pl.Int8).alias("target")

    def compute_with_meta(self, bars: pl.DataFrame) -> pl.DataFrame:
        """Compute target with metadata for analysis."""
        target = self.compute(bars)
        future_close = bars["close"].shift(-self.horizon_bars)
        cumulative_return = (future_close - bars["close"]) / bars["close"]

        return bars.with_columns(
            target,
            cumulative_return.alias("target_return"),
        )
