"""Volume features: OBV, volume surprises, ADTV ratio."""

from __future__ import annotations

import polars as pl

from qm.features.base import FeatureCalculatorBase
from qm.features.registry import FeatureSpec


class VolumeFeatures(FeatureCalculatorBase):
    name = "volume"
    lookback = 20

    def specs(self) -> list[FeatureSpec]:
        base = ("close", "volume")
        return [
            FeatureSpec("volume_sma_10", "volume", 11, ("volume",), description="10-bar volume SMA"),
            FeatureSpec("volume_ratio", "volume", 11, ("volume",),
                        dependencies=("volume_sma_10",), description="Volume / SMA(10)"),
            FeatureSpec("obv_change", "volume", 2, base, description="OBV 1-bar change"),
            FeatureSpec("obv_sma_ratio", "volume", 11, base, description="OBV / SMA(OBV, 10)"),
            FeatureSpec("volume_price_corr", "volume", 20, base,
                        description="Rolling correlation of volume and return"),
        ]

    def compute(self, bars: pl.DataFrame) -> pl.DataFrame:
        eps = 1e-10
        direction = pl.when(pl.col("close") > pl.col("close").shift(1)).then(1).\
            when(pl.col("close") < pl.col("close").shift(1)).then(-1).\
            otherwise(0)

        obv = (direction * pl.col("volume")).cum_sum()

        bars = bars.with_columns(
            pl.col("volume").rolling_mean(window_size=10, min_samples=5).alias("volume_sma_10"),
            obv.alias("_obv"),
        )

        bars = bars.with_columns(
            (pl.col("volume") / (pl.col("volume_sma_10") + eps)).alias("volume_ratio"),
            pl.col("_obv").diff().alias("obv_change"),
            (pl.col("_obv") / (pl.col("_obv").rolling_mean(window_size=10, min_samples=5) + eps))
            .alias("obv_sma_ratio"),
            pl.rolling_corr(
                pl.col("volume"),
                pl.col("close").pct_change(),
                window_size=20,
                min_samples=10,
            ).alias("volume_price_corr"),
        )

        return bars.drop("_obv")
