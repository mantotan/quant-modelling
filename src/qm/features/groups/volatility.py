"""Volatility features: realized vol, Parkinson, Garman-Klass, vol-of-vol."""

from __future__ import annotations

import math

import polars as pl

from qm.features.base import FeatureCalculatorBase
from qm.features.registry import FeatureSpec


class VolatilityFeatures(FeatureCalculatorBase):
    name = "volatility"
    lookback = 30

    def specs(self) -> list[FeatureSpec]:
        base = ("open", "high", "low", "close")
        return [
            FeatureSpec("realized_vol_10", "volatility", 11, base, description="10-bar realized vol"),
            FeatureSpec("realized_vol_20", "volatility", 21, base, description="20-bar realized vol"),
            FeatureSpec("parkinson_vol_10", "volatility", 11, base, description="Parkinson estimator"),
            FeatureSpec("garman_klass_vol_10", "volatility", 11, base, description="Garman-Klass estimator"),
            FeatureSpec("vol_of_vol_20", "volatility", 30, base,
                        dependencies=("realized_vol_10",), description="Volatility of volatility"),
            FeatureSpec("vol_ratio", "volatility", 21, base,
                        dependencies=("realized_vol_10", "realized_vol_20"),
                        description="Short vol / long vol ratio"),
        ]

    def compute(self, bars: pl.DataFrame) -> pl.DataFrame:
        eps = 1e-10
        log_ret = pl.col("close").log().diff()
        log_hl = (pl.col("high") / (pl.col("low") + eps)).log()

        # Parkinson: sqrt(1/(4*n*ln2) * sum(ln(H/L)^2))
        parkinson_factor = 1 / (4 * math.log(2))

        # Garman-Klass: 0.5 * ln(H/L)^2 - (2*ln2-1) * ln(C/O)^2
        gk_factor = 2 * math.log(2) - 1
        log_co = (pl.col("close") / (pl.col("open") + eps)).log()

        bars = bars.with_columns(
            # Realized volatility (std of log returns)
            log_ret.rolling_std(window_size=10, min_samples=5).alias("realized_vol_10"),
            log_ret.rolling_std(window_size=20, min_samples=10).alias("realized_vol_20"),
            # Parkinson volatility
            (
                (log_hl.pow(2) * parkinson_factor).rolling_mean(window_size=10, min_samples=5).sqrt()
            ).alias("parkinson_vol_10"),
            # Garman-Klass volatility
            (
                (0.5 * log_hl.pow(2) - gk_factor * log_co.pow(2))
                .rolling_mean(window_size=10, min_samples=5)
                .abs()
                .sqrt()
            ).alias("garman_klass_vol_10"),
        )

        # Vol-of-vol and vol ratio (depend on computed columns)
        bars = bars.with_columns(
            pl.col("realized_vol_10")
            .rolling_std(window_size=20, min_samples=10)
            .alias("vol_of_vol_20"),
            (pl.col("realized_vol_10") / (pl.col("realized_vol_20") + eps)).alias("vol_ratio"),
        )

        return bars
