"""Percentile rank features.

Scale-invariant distributional features: where the current value sits
relative to the trailing 20-bar window. Uses the min-max normalisation
pattern from funding.py for percentile rank approximation.
"""

from __future__ import annotations

import polars as pl

from qm.features.base import FeatureCalculatorBase
from qm.features.registry import FeatureSpec

_WINDOW = 20
_EPS = 1e-12


class RankFeatures(FeatureCalculatorBase):
    name = "rank_features"
    lookback = 25

    def specs(self) -> list[FeatureSpec]:
        return [
            FeatureSpec(
                "return_rank_20", "rank_features", _WINDOW + 1, ("close",),
                description="Percentile rank of 1-bar return in trailing 20 bars",
            ),
            FeatureSpec(
                "volume_rank_20", "rank_features", _WINDOW, ("volume",),
                description="Percentile rank of volume in trailing 20 bars",
            ),
            FeatureSpec(
                "range_rank_20", "rank_features", _WINDOW, ("high", "low"),
                description="Percentile rank of bar range in trailing 20 bars",
            ),
        ]

    def compute(self, bars: pl.DataFrame) -> pl.DataFrame:
        ret = pl.col("close").pct_change()
        bar_range = pl.col("high") - pl.col("low")

        def _pctile_rank(expr: pl.Expr) -> pl.Expr:
            rmin = expr.rolling_min(window_size=_WINDOW, min_samples=_WINDOW // 2)
            rmax = expr.rolling_max(window_size=_WINDOW, min_samples=_WINDOW // 2)
            return (expr - rmin) / (rmax - rmin + _EPS)

        bars = bars.with_columns(
            _pctile_rank(ret).alias("return_rank_20"),
            _pctile_rank(pl.col("volume")).alias("volume_rank_20"),
            _pctile_rank(bar_range).alias("range_rank_20"),
        )

        return bars
