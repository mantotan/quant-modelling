"""Time-based features: hour of day, day of week, session indicators."""

from __future__ import annotations

import polars as pl

from qm.features.base import FeatureCalculatorBase
from qm.features.registry import FeatureSpec


class TimeFeatures(FeatureCalculatorBase):
    name = "time"
    lookback = 1

    def specs(self) -> list[FeatureSpec]:
        return [
            FeatureSpec("hour_sin", "time", 1, ("time",), description="Sine of hour (cyclical)"),
            FeatureSpec("hour_cos", "time", 1, ("time",), description="Cosine of hour (cyclical)"),
            FeatureSpec("dow_sin", "time", 1, ("time",), description="Sine of day of week"),
            FeatureSpec("dow_cos", "time", 1, ("time",), description="Cosine of day of week"),
            FeatureSpec("is_asia_session", "time", 1, ("time",), description="Asia hours (0-8 UTC)"),
            FeatureSpec("is_eu_session", "time", 1, ("time",), description="EU hours (7-16 UTC)"),
            FeatureSpec("is_us_session", "time", 1, ("time",), description="US hours (13-22 UTC)"),
            FeatureSpec("is_weekend", "time", 1, ("time",), description="Saturday or Sunday"),
        ]

    def compute(self, bars: pl.DataFrame) -> pl.DataFrame:
        import math

        hour = pl.col("time").dt.hour().cast(pl.Float64)
        dow = pl.col("time").dt.weekday().cast(pl.Float64)  # Polars: 1=Monday, 7=Sunday

        return bars.with_columns(
            (hour * 2 * math.pi / 24).sin().alias("hour_sin"),
            (hour * 2 * math.pi / 24).cos().alias("hour_cos"),
            (dow * 2 * math.pi / 7).sin().alias("dow_sin"),
            (dow * 2 * math.pi / 7).cos().alias("dow_cos"),
            (hour.is_between(0, 8)).cast(pl.Int8).alias("is_asia_session"),
            (hour.is_between(7, 16)).cast(pl.Int8).alias("is_eu_session"),
            (hour.is_between(13, 22)).cast(pl.Int8).alias("is_us_session"),
            (dow.is_in([6, 7])).cast(pl.Int8).alias("is_weekend"),  # 6=Saturday, 7=Sunday
        )
