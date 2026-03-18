"""Regime-detection features based on volatility and trend state.

Classifies the current market regime using rolling percentiles of
realised volatility and trend direction.  Regime awareness allows
the model to learn context-dependent patterns (e.g., momentum works
in trends, mean-reversion works in low-vol ranges).

Graceful no-op: if ``realized_vol_10`` is absent the compute()
method returns the input unchanged.

Feature list
------------
- ``regime_vol_state``   — categorical regime (0=low, 1=normal, 2=high, 3=crisis)
                           based on rolling percentile of realised vol
- ``regime_vol_zscore``  — z-score of realised vol over a rolling window,
                           continuous measure of vol regime extremity
- ``regime_trend_state`` — trend direction (1=up, 0=flat, -1=down) based on
                           rolling return sign over a lookback window
"""

from __future__ import annotations

import polars as pl

from qm.features.base import FeatureCalculatorBase
from qm.features.registry import FeatureSpec

# Source columns (computed by VolatilityFeatures group)
_VOL_COL = "realized_vol_10"

# Rolling window for percentile / z-score calculation
_LOOKBACK = 120  # ~10h at 5m cadence

# Percentile thresholds for vol regime classification
_LOW_PCTILE = 25.0
_HIGH_PCTILE = 75.0
_CRISIS_PCTILE = 95.0

# Trend detection window (bars)
_TREND_WINDOW = 20


class RegimeFeatures(FeatureCalculatorBase):
    """Detects market regime from volatility and trend state."""

    name = "regime"
    lookback = _LOOKBACK

    def specs(self) -> list[FeatureSpec]:
        return [
            FeatureSpec(
                "regime_vol_state", "regime", _LOOKBACK,
                (_VOL_COL,),
                dependencies=(_VOL_COL,),
                description="Categorical vol regime: 0=low, 1=normal, "
                            "2=high, 3=crisis (rolling percentile)",
            ),
            FeatureSpec(
                "regime_vol_zscore", "regime", _LOOKBACK,
                (_VOL_COL,),
                dependencies=(_VOL_COL,),
                description="Z-score of realised vol over rolling window",
            ),
            FeatureSpec(
                "regime_trend_state", "regime", _TREND_WINDOW,
                ("close",),
                description="Trend direction: 1=up, 0=flat, -1=down "
                            "(rolling return sign)",
            ),
        ]

    def compute(self, bars: pl.DataFrame) -> pl.DataFrame:
        """Compute regime features. No-op if vol column is absent."""
        if _VOL_COL not in bars.columns:
            return bars

        # 1. Vol z-score: (current_vol - rolling_mean) / rolling_std
        bars = bars.with_columns(
            (
                (pl.col(_VOL_COL) - pl.col(_VOL_COL).rolling_mean(
                    window_size=_LOOKBACK, min_samples=10
                ))
                / (pl.col(_VOL_COL).rolling_std(
                    window_size=_LOOKBACK, min_samples=10
                ) + 1e-10)
            ).alias("regime_vol_zscore"),
        )

        # 2. Vol state: classify using rolling min/max percentile approach
        #    Compute (vol - rolling_min) / (rolling_max - rolling_min) as
        #    a percentile proxy, then bucket into regimes.
        vol_min = pl.col(_VOL_COL).rolling_min(
            window_size=_LOOKBACK, min_samples=10
        )
        vol_max = pl.col(_VOL_COL).rolling_max(
            window_size=_LOOKBACK, min_samples=10
        )
        vol_pctile = (pl.col(_VOL_COL) - vol_min) / (vol_max - vol_min + 1e-12)

        bars = bars.with_columns(
            pl.when(vol_pctile >= _CRISIS_PCTILE / 100.0)
            .then(3)  # crisis
            .when(vol_pctile >= _HIGH_PCTILE / 100.0)
            .then(2)  # high
            .when(vol_pctile <= _LOW_PCTILE / 100.0)
            .then(0)  # low
            .otherwise(1)  # normal
            .cast(pl.Int8)
            .alias("regime_vol_state"),
        )

        # 3. Trend state: sign of rolling return over _TREND_WINDOW bars
        if "close" in bars.columns:
            rolling_ret = pl.col("close").pct_change(n=_TREND_WINDOW)
            bars = bars.with_columns(
                pl.when(rolling_ret > 0.001)
                .then(1)   # up trend
                .when(rolling_ret < -0.001)
                .then(-1)  # down trend
                .otherwise(0)  # flat
                .cast(pl.Int8)
                .alias("regime_trend_state"),
            )
        else:
            bars = bars.with_columns(
                pl.lit(0, dtype=pl.Int8).alias("regime_trend_state"),
            )

        return bars
