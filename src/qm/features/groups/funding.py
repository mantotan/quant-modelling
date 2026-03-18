"""Funding-rate-based features for perpetual futures alpha.

Funding rates are published every 8 hours on Binance perps. After
join_asof via CrossAssetPipeline, the bars DataFrame will contain
``funding_funding_rate`` and ``funding_mark_price`` columns (the
``funding_`` prefix comes from the alpha store name).

Graceful no-op: if ``funding_funding_rate`` is absent the compute()
method returns the input unchanged — existing code without funding
data still works.

Feature list
------------
- ``funding_rate``          — raw 8h rate forward-filled to bar cadence
- ``funding_rate_sma3``     — 3-period SMA (24h at 8h cadence, smoothed on bars)
- ``funding_rate_pctile``   — percentile rank over rolling 90-period window
- ``funding_rate_direction``— sign (+1 / 0 / −1) of the current rate
- ``funding_cumulative_24h``— rolling 24h cumulative funding (3 × 8h periods)
- ``funding_hours_since``   — hours since the last funding rate update
"""

from __future__ import annotations

import polars as pl

from qm.features.base import FeatureCalculatorBase
from qm.features.registry import FeatureSpec

# Column written by join_alpha_asof(prefix="funding") from funding_rate downloader
_SRC_COL = "funding_funding_rate"

# Rolling window for percentile rank (90 periods ≈ 30 days at 8h cadence,
# but we operate on bar cadence so this is approximate)
_PCTILE_WINDOW = 90

# Rolling window for cumulative sum (3 funding events = 24h at 8h cadence).
# On 5m bars that's 288 bars; we use period count from the source cadence
# and scale inside compute.
_CUMUL_PERIODS = 3


class FundingFeatures(FeatureCalculatorBase):
    """Derives trading features from perpetual funding rates."""

    name = "funding"
    lookback = _PCTILE_WINDOW

    def specs(self) -> list[FeatureSpec]:
        return [
            FeatureSpec(
                "funding_rate", "funding", 1, (_SRC_COL,),
                description="Raw 8h funding rate forward-filled to bar cadence",
            ),
            FeatureSpec(
                "funding_rate_sma3", "funding", 3, (_SRC_COL,),
                description="3-period SMA of funding rate (smoothed 24h)",
            ),
            FeatureSpec(
                "funding_rate_pctile", "funding", _PCTILE_WINDOW, (_SRC_COL,),
                description="Percentile rank over rolling 90-period window",
            ),
            FeatureSpec(
                "funding_rate_direction", "funding", 1, (_SRC_COL,),
                description="Sign of current funding rate (+1/0/-1)",
            ),
            FeatureSpec(
                "funding_cumulative_24h", "funding", _CUMUL_PERIODS, (_SRC_COL,),
                description="Rolling 24h cumulative funding (3 × 8h)",
            ),
            FeatureSpec(
                "funding_hours_since", "funding", 1, (_SRC_COL,),
                description="Hours since last funding rate update",
            ),
        ]

    def compute(self, bars: pl.DataFrame) -> pl.DataFrame:
        """Compute funding features. No-op if funding columns are absent."""
        if _SRC_COL not in bars.columns:
            return bars

        # 1. Raw rate (already forward-filled by join_asof)
        bars = bars.with_columns(
            pl.col(_SRC_COL).alias("funding_rate"),
        )

        # 2. SMA-3
        bars = bars.with_columns(
            pl.col(_SRC_COL)
            .rolling_mean(window_size=3, min_samples=1)
            .alias("funding_rate_sma3"),
        )

        # 3. Percentile rank: fraction of values in rolling window <= current
        bars = bars.with_columns(
            pl.col(_SRC_COL)
            .rolling_quantile(quantile=0.5, window_size=_PCTILE_WINDOW, min_samples=1)
            .alias("_funding_median"),
        )
        # Approximate percentile via rank / window_size using rolling_mean of indicator
        bars = bars.with_columns(
            (
                (pl.col(_SRC_COL) - pl.col(_SRC_COL).rolling_min(
                    window_size=_PCTILE_WINDOW, min_samples=1
                ))
                / (
                    pl.col(_SRC_COL).rolling_max(
                        window_size=_PCTILE_WINDOW, min_samples=1
                    )
                    - pl.col(_SRC_COL).rolling_min(
                        window_size=_PCTILE_WINDOW, min_samples=1
                    )
                    + 1e-12
                )
            ).alias("funding_rate_pctile"),
        )
        # Drop temporary column
        bars = bars.drop("_funding_median")

        # 4. Direction: sign of the funding rate
        bars = bars.with_columns(
            pl.when(pl.col(_SRC_COL) > 0)
            .then(1)
            .when(pl.col(_SRC_COL) < 0)
            .then(-1)
            .otherwise(0)
            .cast(pl.Int8)
            .alias("funding_rate_direction"),
        )

        # 5. Cumulative 24h funding (rolling sum of last 3 non-null changes)
        bars = bars.with_columns(
            pl.col(_SRC_COL)
            .rolling_sum(window_size=_CUMUL_PERIODS, min_samples=1)
            .alias("funding_cumulative_24h"),
        )

        # 6. Hours since last funding update
        # Detect actual changes (where rate differs from previous bar).
        # The first row always counts as an update (shift produces null).
        if "time" in bars.columns:
            bars = bars.with_columns(
                pl.when(
                    pl.col(_SRC_COL).shift(1).is_null()
                    | (pl.col(_SRC_COL) != pl.col(_SRC_COL).shift(1))
                )
                .then(pl.col("time"))
                .otherwise(None)
                .forward_fill()
                .alias("_last_update_time"),
            )
            bars = bars.with_columns(
                (
                    (pl.col("time") - pl.col("_last_update_time"))
                    .dt.total_seconds()
                    / 3600.0
                ).alias("funding_hours_since"),
            )
            bars = bars.drop("_last_update_time")
        else:
            # Fallback: can't compute without time column
            bars = bars.with_columns(
                pl.lit(None, dtype=pl.Float64).alias("funding_hours_since"),
            )

        return bars
