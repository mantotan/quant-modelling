"""Price-based features: returns, VWAP deviation, gaps, bar internals."""

from __future__ import annotations

import polars as pl

from qm.features.base import FeatureCalculatorBase
from qm.features.registry import FeatureSpec


class PriceFeatures(FeatureCalculatorBase):
    name = "price"
    lookback = 20

    def specs(self) -> list[FeatureSpec]:
        base = ("open", "high", "low", "close", "volume")
        return [
            FeatureSpec("return_1", "price", 2, base, description="1-bar simple return"),
            FeatureSpec("return_5", "price", 6, base, description="5-bar simple return"),
            FeatureSpec("return_12", "price", 13, base, description="12-bar simple return"),
            FeatureSpec("log_return_1", "price", 2, base, description="1-bar log return"),
            FeatureSpec("vwap_deviation", "price", 1, ("close", "vwap"), description="Close / VWAP - 1"),
            FeatureSpec("gap", "price", 2, ("open", "close"), description="Open / prev Close - 1"),
            FeatureSpec("bar_range", "price", 1, ("high", "low"), description="High - Low"),
            FeatureSpec("bar_position", "price", 1, base, description="(Close-Low)/(High-Low)"),
            FeatureSpec("body_ratio", "price", 1, base, description="|Close-Open|/(High-Low)"),
            FeatureSpec("upper_shadow", "price", 1, base, description="Upper wick ratio"),
            FeatureSpec("lower_shadow", "price", 1, base, description="Lower wick ratio"),
        ]

    def compute(self, bars: pl.DataFrame) -> pl.DataFrame:
        eps = 1e-10
        hl_range = pl.col("high") - pl.col("low")

        return bars.with_columns(
            # Returns
            (pl.col("close") / pl.col("close").shift(1) - 1).alias("return_1"),
            (pl.col("close") / pl.col("close").shift(5) - 1).alias("return_5"),
            (pl.col("close") / pl.col("close").shift(12) - 1).alias("return_12"),
            pl.col("close").log().diff().alias("log_return_1"),
            # VWAP deviation
            (pl.col("close") / (pl.col("vwap") + eps) - 1).alias("vwap_deviation"),
            # Gap (open vs previous close)
            (pl.col("open") / pl.col("close").shift(1) - 1).alias("gap"),
            # Bar internals
            hl_range.alias("bar_range"),
            ((pl.col("close") - pl.col("low")) / (hl_range + eps)).alias("bar_position"),
            ((pl.col("close") - pl.col("open")).abs() / (hl_range + eps)).alias("body_ratio"),
            # Shadows
            (
                (pl.col("high") - pl.max_horizontal("open", "close")) / (hl_range + eps)
            ).alias("upper_shadow"),
            (
                (pl.min_horizontal("open", "close") - pl.col("low")) / (hl_range + eps)
            ).alias("lower_shadow"),
        )
