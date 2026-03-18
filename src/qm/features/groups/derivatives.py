"""Derivatives-based features: OI, long/short ratios, taker volume.

Graceful no-op: only computes features for columns that exist in the
input DataFrame. If metrics data wasn't joined, these features are
silently skipped — existing code without metrics data still works.
"""

from __future__ import annotations

import polars as pl

from qm.features.base import FeatureCalculatorBase
from qm.features.registry import FeatureSpec


class DerivativesFeatures(FeatureCalculatorBase):
    name = "derivatives"
    lookback = 5

    def specs(self) -> list[FeatureSpec]:
        return [
            FeatureSpec("taker_buy_ratio", "derivatives", 1, ("volume", "taker_buy_volume"),
                        description="Taker buy volume / total volume"),
            FeatureSpec("oi_change", "derivatives", 2, ("sum_open_interest",),
                        description="5m open interest pct change"),
            FeatureSpec("oi_change_5", "derivatives", 6, ("sum_open_interest",),
                        description="5-bar open interest pct change"),
            FeatureSpec("ls_ratio", "derivatives", 1, ("count_long_short_ratio",),
                        description="Long/short account ratio"),
            FeatureSpec("ls_ratio_change", "derivatives", 2, ("count_long_short_ratio",),
                        description="L/S ratio 1-bar change"),
            FeatureSpec("top_ls_ratio", "derivatives", 1, ("sum_toptrader_long_short_ratio",),
                        description="Top trader long/short ratio"),
            FeatureSpec("top_ls_divergence", "derivatives", 1,
                        ("sum_toptrader_long_short_ratio", "count_long_short_ratio"),
                        description="Top trader vs retail L/S divergence"),
            FeatureSpec("taker_ls_vol_ratio", "derivatives", 1,
                        ("sum_taker_long_short_vol_ratio",),
                        description="Taker long/short volume ratio"),
        ]

    def compute(self, bars: pl.DataFrame) -> pl.DataFrame:
        # Taker buy ratio from klines (if column exists)
        if "taker_buy_volume" in bars.columns and "volume" in bars.columns:
            bars = bars.with_columns(
                (pl.col("taker_buy_volume") / (pl.col("volume") + 1e-10))
                .alias("taker_buy_ratio")
            )

        # Metrics features (if columns exist from metrics join)
        if "sum_open_interest" in bars.columns:
            bars = bars.with_columns([
                pl.col("sum_open_interest").pct_change().alias("oi_change"),
                pl.col("sum_open_interest").pct_change(n=5).alias("oi_change_5"),
            ])

        if "count_long_short_ratio" in bars.columns:
            bars = bars.with_columns([
                pl.col("count_long_short_ratio").alias("ls_ratio"),
                pl.col("count_long_short_ratio").diff().alias("ls_ratio_change"),
            ])

        if "sum_toptrader_long_short_ratio" in bars.columns:
            bars = bars.with_columns(
                pl.col("sum_toptrader_long_short_ratio").alias("top_ls_ratio")
            )

        if ("sum_toptrader_long_short_ratio" in bars.columns
                and "count_long_short_ratio" in bars.columns):
            bars = bars.with_columns(
                (pl.col("sum_toptrader_long_short_ratio")
                 - pl.col("count_long_short_ratio")).alias("top_ls_divergence")
            )

        if "sum_taker_long_short_vol_ratio" in bars.columns:
            bars = bars.with_columns(
                pl.col("sum_taker_long_short_vol_ratio").alias("taker_ls_vol_ratio")
            )

        return bars
