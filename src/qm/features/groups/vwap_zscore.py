"""VWAP z-score features.

Normalises the close-VWAP deviation as a z-score at multiple lookback
windows. Extends the existing ``vwap_deviation`` (close/vwap - 1) in
the price group with standard-deviation normalisation for a more
robust mean-reversion signal.
"""

from __future__ import annotations

import polars as pl

from qm.features.base import FeatureCalculatorBase
from qm.features.registry import FeatureSpec

_EPS = 1e-10


class VwapZscoreFeatures(FeatureCalculatorBase):
    name = "vwap_zscore"
    lookback = 30

    def specs(self) -> list[FeatureSpec]:
        base = ("close", "vwap")
        return [
            FeatureSpec(
                "vwap_zscore_10", "vwap_zscore", 10, base,
                description="VWAP deviation z-score (10-bar window)",
            ),
            FeatureSpec(
                "vwap_zscore_20", "vwap_zscore", 20, base,
                description="VWAP deviation z-score (20-bar window)",
            ),
            FeatureSpec(
                "vwap_zscore_cross", "vwap_zscore", 20, base,
                dependencies=("vwap_zscore_10", "vwap_zscore_20"),
                description="Cross-lookback z-score signal (short - long)",
            ),
        ]

    def compute(self, bars: pl.DataFrame) -> pl.DataFrame:
        if "vwap" not in bars.columns:
            return bars

        deviation = pl.col("close") - pl.col("vwap")

        bars = bars.with_columns(
            (deviation / (deviation.rolling_std(window_size=10, min_samples=5) + _EPS))
            .alias("vwap_zscore_10"),
            (deviation / (deviation.rolling_std(window_size=20, min_samples=10) + _EPS))
            .alias("vwap_zscore_20"),
        )

        bars = bars.with_columns(
            (pl.col("vwap_zscore_10") - pl.col("vwap_zscore_20"))
            .alias("vwap_zscore_cross"),
        )

        return bars
