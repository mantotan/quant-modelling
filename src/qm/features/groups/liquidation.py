"""Liquidation-cascade-related features from open interest and price data.

Derives alpha signals that detect when the market is approaching
liquidation cascades — situations where concentrated leverage unwinds
rapidly, causing predictable directional moves.

Graceful no-op: if ``sum_open_interest`` is absent the compute()
method returns the input unchanged — existing code without metrics
data still works.

Feature list
------------
- ``liquidation_proximity``  — z-score of price vs rolling mean, proxy for
                               distance to leveraged-position liquidation zones
- ``oi_price_divergence``    — divergence between OI change and price change;
                               rising OI + falling price → bearish pressure
- ``oi_momentum``            — acceleration of OI (second derivative),
                               detects rapid position build-up
- ``leverage_proxy``         — OI / volume ratio, estimates market-wide leverage
"""

from __future__ import annotations

import polars as pl

from qm.features.base import FeatureCalculatorBase
from qm.features.registry import FeatureSpec

# Source column from metrics join
_OI_COL = "sum_open_interest"

# Rolling windows
_PROX_WINDOW = 20  # bars for z-score (proximity)
_MOM_WINDOW = 5    # bars for OI momentum (acceleration)
_LEV_WINDOW = 10   # bars for leverage smoothing


class LiquidationFeatures(FeatureCalculatorBase):
    """Derives features signalling liquidation cascade risk."""

    name = "liquidation"
    lookback = _PROX_WINDOW

    def specs(self) -> list[FeatureSpec]:
        return [
            FeatureSpec(
                "liquidation_proximity", "liquidation", _PROX_WINDOW,
                ("close", _OI_COL),
                description="Z-score of price vs rolling mean — proxy for "
                            "distance to leveraged liquidation zones",
            ),
            FeatureSpec(
                "oi_price_divergence", "liquidation", 2,
                ("close", _OI_COL),
                description="OI change minus price change — rising OI with "
                            "falling price signals bearish pressure",
            ),
            FeatureSpec(
                "oi_momentum", "liquidation", _MOM_WINDOW + 1,
                (_OI_COL,),
                description="Acceleration of OI (second derivative of "
                            "pct_change) — detects rapid position build-up",
            ),
            FeatureSpec(
                "leverage_proxy", "liquidation", _LEV_WINDOW,
                (_OI_COL, "volume"),
                description="Smoothed OI / volume ratio — estimates "
                            "market-wide leverage",
            ),
        ]

    def compute(self, bars: pl.DataFrame) -> pl.DataFrame:
        """Compute liquidation features. No-op if OI column is absent."""
        if _OI_COL not in bars.columns:
            return bars

        # 1. Liquidation proximity: z-score of close price over rolling window.
        #    When price deviates far from its recent mean while OI is high,
        #    leveraged positions are under stress.
        if "close" in bars.columns:
            bars = bars.with_columns(
                (
                    (pl.col("close") - pl.col("close").rolling_mean(
                        window_size=_PROX_WINDOW, min_samples=1
                    ))
                    / (pl.col("close").rolling_std(
                        window_size=_PROX_WINDOW, min_samples=2
                    ) + 1e-10)
                ).alias("liquidation_proximity"),
            )

        # 2. OI–price divergence: difference between OI pct_change and
        #    price pct_change. Positive = OI rising faster than price
        #    (new shorts entering or longs adding at tops).
        if "close" in bars.columns:
            bars = bars.with_columns(
                (
                    pl.col(_OI_COL).pct_change()
                    - pl.col("close").pct_change()
                ).alias("oi_price_divergence"),
            )

        # 3. OI momentum: diff of OI pct_change (acceleration).
        #    Positive acceleration = OI growth speeding up.
        bars = bars.with_columns(
            pl.col(_OI_COL)
            .pct_change()
            .rolling_mean(window_size=_MOM_WINDOW, min_samples=1)
            .diff()
            .alias("oi_momentum"),
        )

        # 4. Leverage proxy: smoothed ratio of OI to volume.
        #    High values indicate over-leveraged market.
        if "volume" in bars.columns:
            bars = bars.with_columns(
                (
                    pl.col(_OI_COL) / (pl.col("volume") + 1e-10)
                ).rolling_mean(
                    window_size=_LEV_WINDOW, min_samples=1
                ).alias("leverage_proxy"),
            )

        return bars
