"""Polymarket microstructure features from orderbook snapshots.

After join_asof via CrossAssetPipeline, the bars DataFrame will
contain columns prefixed with ``polymarket_`` (the alpha store name):
``polymarket_mid_up``, ``polymarket_mid_down``, ``polymarket_spread_up``,
``polymarket_volume``.

Graceful no-op: if ``polymarket_mid_up`` is absent the compute()
method returns the input unchanged.

Feature list
------------
- ``pm_bid_ask_spread``  — effective spread (|1 - mid_up - mid_down|)
- ``pm_order_imbalance`` — mid_up - 0.5 (directional pressure)
- ``pm_trade_flow``      — volume pct_change (activity momentum)
- ``pm_mid_momentum``    — rolling change in mid_up price
"""

from __future__ import annotations

import polars as pl

from qm.features.base import FeatureCalculatorBase
from qm.features.registry import FeatureSpec

# Columns from join_alpha_asof(prefix="polymarket")
_MID_UP = "polymarket_mid_up"
_MID_DOWN = "polymarket_mid_down"
_SPREAD = "polymarket_spread_up"
_VOLUME = "polymarket_volume"

# Rolling window for momentum
_MOM_WINDOW = 6  # ~30min at 5m cadence


class PolymarketMicroFeatures(FeatureCalculatorBase):
    """Derives microstructure features from Polymarket snapshots."""

    name = "polymarket"
    lookback = _MOM_WINDOW

    def specs(self) -> list[FeatureSpec]:
        return [
            FeatureSpec(
                "pm_bid_ask_spread", "polymarket", 1, (_MID_UP, _MID_DOWN),
                description="Effective spread: |1 - mid_up - mid_down|",
            ),
            FeatureSpec(
                "pm_order_imbalance", "polymarket", 1, (_MID_UP,),
                description="Directional pressure: mid_up - 0.5",
            ),
            FeatureSpec(
                "pm_trade_flow", "polymarket", 2, (_VOLUME,),
                description="Volume pct_change — activity momentum",
            ),
            FeatureSpec(
                "pm_mid_momentum", "polymarket", _MOM_WINDOW + 1, (_MID_UP,),
                description="Rolling change in mid_up over 6-bar window",
            ),
        ]

    def compute(self, bars: pl.DataFrame) -> pl.DataFrame:
        """Compute Polymarket micro features. No-op if mid_up absent."""
        if _MID_UP not in bars.columns:
            return bars

        # 1. Bid-ask spread: |1 - mid_up - mid_down|
        if _MID_DOWN in bars.columns:
            bars = bars.with_columns(
                (1.0 - pl.col(_MID_UP) - pl.col(_MID_DOWN))
                .abs()
                .alias("pm_bid_ask_spread"),
            )
        elif _SPREAD in bars.columns:
            # Use pre-computed spread if available
            bars = bars.with_columns(
                pl.col(_SPREAD).alias("pm_bid_ask_spread"),
            )
        else:
            bars = bars.with_columns(
                pl.lit(None, dtype=pl.Float64).alias("pm_bid_ask_spread"),
            )

        # 2. Order imbalance: mid_up - 0.5 (positive = market leans Up)
        bars = bars.with_columns(
            (pl.col(_MID_UP) - 0.5).alias("pm_order_imbalance"),
        )

        # 3. Trade flow: volume pct_change
        if _VOLUME in bars.columns:
            bars = bars.with_columns(
                pl.col(_VOLUME).pct_change().alias("pm_trade_flow"),
            )
        else:
            bars = bars.with_columns(
                pl.lit(None, dtype=pl.Float64).alias("pm_trade_flow"),
            )

        # 4. Mid momentum: rolling change in mid_up
        bars = bars.with_columns(
            pl.col(_MID_UP).pct_change(n=_MOM_WINDOW)
            .alias("pm_mid_momentum"),
        )

        return bars
