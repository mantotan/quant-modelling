"""Turnover features: relative volume dynamics.

Measures volume relative to its 20-bar average, the short/long volume
trend, and the acceleration of turnover. Overlaps with the existing
``volume_ratio`` (volume/SMA10) — the 3-stage feature selection filter
will resolve collinearity automatically.
"""

from __future__ import annotations

import polars as pl

from qm.features.base import FeatureCalculatorBase
from qm.features.registry import FeatureSpec

_EPS = 1e-10


class TurnoverFeatures(FeatureCalculatorBase):
    name = "turnover"
    lookback = 25

    def specs(self) -> list[FeatureSpec]:
        base = ("volume",)
        return [
            FeatureSpec(
                "turnover_ratio", "turnover", 20, base,
                description="Volume / 20-bar average volume",
            ),
            FeatureSpec(
                "turnover_trend", "turnover", 20, base,
                description="5-bar / 20-bar volume SMA ratio",
            ),
            FeatureSpec(
                "turnover_accel", "turnover", 25, base,
                dependencies=("turnover_ratio",),
                description="5-bar change in turnover ratio",
            ),
        ]

    def compute(self, bars: pl.DataFrame) -> pl.DataFrame:
        vol_sma_20 = pl.col("volume").rolling_mean(window_size=20, min_samples=10)
        vol_sma_5 = pl.col("volume").rolling_mean(window_size=5, min_samples=3)

        bars = bars.with_columns(
            (pl.col("volume") / (vol_sma_20 + _EPS)).alias("turnover_ratio"),
            (vol_sma_5 / (vol_sma_20 + _EPS)).alias("turnover_trend"),
        )

        bars = bars.with_columns(
            pl.col("turnover_ratio").diff(5).alias("turnover_accel"),
        )

        return bars
