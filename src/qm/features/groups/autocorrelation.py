"""Autocorrelation features: rolling return autocorrelation at multiple lags.

High positive autocorrelation signals trending/momentum regimes.
Negative autocorrelation signals mean-reversion. The sum of lags
provides a composite mean-reversion signature.
"""

from __future__ import annotations

import polars as pl

from qm.features.base import FeatureCalculatorBase
from qm.features.registry import FeatureSpec

_WINDOW = 20
_LAGS = (1, 2, 3, 5)


class AutocorrelationFeatures(FeatureCalculatorBase):
    name = "autocorrelation"
    lookback = 25

    def specs(self) -> list[FeatureSpec]:
        specs = [
            FeatureSpec(
                f"autocorr_{lag}", "autocorrelation",
                _WINDOW + lag, ("close",),
                description=f"Rolling autocorrelation lag {lag} (window={_WINDOW})",
            )
            for lag in _LAGS
        ]
        specs.append(
            FeatureSpec(
                "autocorr_sum", "autocorrelation", 25, ("close",),
                dependencies=tuple(f"autocorr_{lag}" for lag in _LAGS),
                description="Sum of autocorrelation lags (mean-reversion signature)",
            ),
        )
        return specs

    def compute(self, bars: pl.DataFrame) -> pl.DataFrame:
        ret = pl.col("close").pct_change()

        for lag in _LAGS:
            bars = bars.with_columns(
                pl.rolling_corr(
                    ret,
                    ret.shift(lag),
                    window_size=_WINDOW,
                    min_samples=_WINDOW // 2,
                ).alias(f"autocorr_{lag}"),
            )

        bars = bars.with_columns(
            sum(pl.col(f"autocorr_{lag}") for lag in _LAGS).alias("autocorr_sum"),
        )

        return bars
