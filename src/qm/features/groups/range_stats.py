"""Range statistics features.

Rolling statistics of the normalised high-low range ((high-low)/close).
Extends the single-bar ``bar_range`` feature in the price group into
distributional signals for volatility expansion/contraction detection.
"""

from __future__ import annotations

import polars as pl

from qm.features.base import FeatureCalculatorBase
from qm.features.registry import FeatureSpec

_EPS = 1e-10


class RangeStatsFeatures(FeatureCalculatorBase):
    name = "range_stats"
    lookback = 30

    def specs(self) -> list[FeatureSpec]:
        base = ("high", "low", "close")
        return [
            FeatureSpec(
                "range_pct_10", "range_stats", 10, base,
                description="10-bar rolling mean of normalised range",
            ),
            FeatureSpec(
                "range_pct_20", "range_stats", 20, base,
                description="20-bar rolling mean of normalised range",
            ),
            FeatureSpec(
                "range_std_10", "range_stats", 10, base,
                description="10-bar rolling std of normalised range",
            ),
            FeatureSpec(
                "range_ratio", "range_stats", 20, base,
                dependencies=("range_pct_10", "range_pct_20"),
                description="Short/long range ratio (expansion/contraction)",
            ),
        ]

    def compute(self, bars: pl.DataFrame) -> pl.DataFrame:
        norm_range = (pl.col("high") - pl.col("low")) / (pl.col("close") + _EPS)

        bars = bars.with_columns(
            norm_range.rolling_mean(window_size=10, min_samples=5).alias("range_pct_10"),
            norm_range.rolling_mean(window_size=20, min_samples=10).alias("range_pct_20"),
            norm_range.rolling_std(window_size=10, min_samples=5).alias("range_std_10"),
        )

        bars = bars.with_columns(
            (pl.col("range_pct_10") / (pl.col("range_pct_20") + _EPS)).alias("range_ratio"),
        )

        return bars
