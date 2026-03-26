"""Magnitude target: predict whether the next bar's move exceeds the rolling median.

Tests the hypothesis that features (vol, funding, OI) predict the SIZE of
moves, not direction. Used as a trading gate: only trade direction when
the magnitude model says "big move coming."
"""

from __future__ import annotations

import polars as pl


class MagnitudeTarget:
    """Target: 1 if |return[t+1]| > rolling_median(|return|), else 0.

    Args:
        lookback: Rolling window for computing the median absolute return.
    """

    def __init__(self, lookback: int = 100) -> None:
        if lookback < 10:
            msg = f"lookback must be >= 10, got {lookback}"
            raise ValueError(msg)
        self.lookback = lookback

    def compute(self, bars: pl.DataFrame) -> pl.Series:
        """Compute magnitude target.

        Last row is null (no future bar).
        """
        abs_ret = ((bars["close"] - bars["open"]) / bars["open"]).abs()
        threshold = abs_ret.rolling_median(
            window_size=self.lookback,
            min_samples=self.lookback // 2,
        )
        future_abs_ret = abs_ret.shift(-1)
        return (future_abs_ret > threshold).cast(pl.Int8).alias("target")

    def compute_with_meta(self, bars: pl.DataFrame) -> pl.DataFrame:
        """Compute target with metadata for analysis."""
        abs_ret = ((bars["close"] - bars["open"]) / bars["open"]).abs()
        threshold = abs_ret.rolling_median(
            window_size=self.lookback,
            min_samples=self.lookback // 2,
        )
        future_abs_ret = abs_ret.shift(-1)

        return bars.with_columns(
            self.compute(bars),
            future_abs_ret.alias("future_abs_return"),
            threshold.alias("magnitude_threshold"),
        )
