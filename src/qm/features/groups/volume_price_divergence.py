"""Volume-price divergence features.

Measures rolling correlation between close price levels and volume
at multiple lookbacks. Divergence between short- and medium-term
correlations signals trend exhaustion.

Distinct from the existing ``volume_price_corr`` in the volume group
which correlates volume with *returns* (not price levels).
"""

from __future__ import annotations

import polars as pl

from qm.features.base import FeatureCalculatorBase
from qm.features.registry import FeatureSpec


class VolumePriceDivergenceFeatures(FeatureCalculatorBase):
    name = "volume_price_divergence"
    lookback = 30

    def specs(self) -> list[FeatureSpec]:
        base = ("close", "volume")
        return [
            FeatureSpec(
                "vp_corr_10", "volume_price_divergence", 10, base,
                description="Rolling correlation of close and volume (10-bar)",
            ),
            FeatureSpec(
                "vp_corr_20", "volume_price_divergence", 20, base,
                description="Rolling correlation of close and volume (20-bar)",
            ),
            FeatureSpec(
                "vp_divergence", "volume_price_divergence", 20, base,
                dependencies=("vp_corr_10", "vp_corr_20"),
                description="Short-medium volume-price correlation divergence",
            ),
            FeatureSpec(
                "vp_corr_change", "volume_price_divergence", 15, base,
                dependencies=("vp_corr_10",),
                description="5-bar change in short-term volume-price correlation",
            ),
        ]

    def compute(self, bars: pl.DataFrame) -> pl.DataFrame:
        bars = bars.with_columns(
            pl.rolling_corr(
                pl.col("close"), pl.col("volume"),
                window_size=10, min_samples=5,
            ).alias("vp_corr_10"),
            pl.rolling_corr(
                pl.col("close"), pl.col("volume"),
                window_size=20, min_samples=10,
            ).alias("vp_corr_20"),
        )

        bars = bars.with_columns(
            (pl.col("vp_corr_20") - pl.col("vp_corr_10")).alias("vp_divergence"),
            pl.col("vp_corr_10").diff(5).alias("vp_corr_change"),
        )

        return bars
