"""Interaction features: explicit alpha × TA cross-products.

LightGBM can discover interactions via tree splits, but explicit
cross-product features guide it toward the most valuable alpha × TA
combinations, improving sample efficiency and interpretability.

Graceful no-op per pair: each interaction checks that BOTH input
columns exist before computing. Missing columns (e.g., options IV
not yet joined) are silently skipped.

Feature list
------------
- ``funding_x_rsi``         — funding_rate_pctile × rsi_14
- ``funding_x_vol``         — funding_rate × realized_vol_10
- ``oi_div_x_momentum``     — oi_price_divergence × roc_5
- ``iv_skew_x_return``      — iv_skew × return_5 (requires options IV)
- ``leverage_x_proximity``  — leverage_proxy × liquidation_proximity
- ``regime_x_funding``      — regime_vol_state × funding_rate
- ``btc_lead_x_funding``    — btc_return_1 × funding_rate (cross-asset)
- ``pm_imbalance_x_vol``    — pm_order_imbalance × realized_vol_10 (Polymarket)
"""

from __future__ import annotations

import polars as pl

from qm.features.base import FeatureCalculatorBase
from qm.features.registry import FeatureSpec

# Interaction pair definitions: (output_name, col_a, col_b)
INTERACTION_PAIRS: list[tuple[str, str, str]] = [
    ("funding_x_rsi", "funding_rate_pctile", "rsi_14"),
    ("funding_x_vol", "funding_rate", "realized_vol_10"),
    ("oi_div_x_momentum", "oi_price_divergence", "roc_5"),
    ("iv_skew_x_return", "iv_skew", "return_5"),
    ("leverage_x_proximity", "leverage_proxy", "liquidation_proximity"),
    ("regime_x_funding", "regime_vol_state", "funding_rate"),
    ("btc_lead_x_funding", "btc_return_1", "funding_rate"),
    ("pm_imbalance_x_vol", "pm_order_imbalance", "realized_vol_10"),
]


class InteractionFeatures(FeatureCalculatorBase):
    """Computes explicit alpha × TA cross-product features."""

    name = "interactions"
    lookback = 1  # inputs already computed by upstream groups

    def specs(self) -> list[FeatureSpec]:
        return [
            FeatureSpec(
                name, "interactions", 1, (col_a, col_b),
                dependencies=(col_a, col_b),
                description=f"Interaction: {col_a} × {col_b}",
            )
            for name, col_a, col_b in INTERACTION_PAIRS
        ]

    def compute(self, bars: pl.DataFrame) -> pl.DataFrame:
        """Compute interaction features. Each pair is an independent no-op."""
        for feat_name, col_a, col_b in INTERACTION_PAIRS:
            if col_a in bars.columns and col_b in bars.columns:
                bars = bars.with_columns(
                    (pl.col(col_a) * pl.col(col_b)).alias(feat_name),
                )
        return bars
