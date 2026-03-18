"""Momentum features: RSI, MACD, ROC, Stochastic."""

from __future__ import annotations

import polars as pl

from qm.features.base import FeatureCalculatorBase
from qm.features.registry import FeatureSpec


class MomentumFeatures(FeatureCalculatorBase):
    name = "momentum"
    lookback = 30

    def specs(self) -> list[FeatureSpec]:
        base = ("open", "high", "low", "close")
        return [
            FeatureSpec("rsi_14", "momentum", 15, base, description="14-period RSI"),
            FeatureSpec("rsi_7", "momentum", 8, base, description="7-period RSI"),
            FeatureSpec("macd_line", "momentum", 27, ("close",), description="MACD line (12-26 EMA)"),
            FeatureSpec("macd_signal", "momentum", 30, ("close",),
                        dependencies=("macd_line",), description="MACD signal (9-period EMA of MACD)"),
            FeatureSpec("macd_histogram", "momentum", 30, ("close",),
                        dependencies=("macd_line", "macd_signal"), description="MACD - Signal"),
            FeatureSpec("roc_5", "momentum", 6, ("close",), description="5-bar rate of change"),
            FeatureSpec("roc_10", "momentum", 11, ("close",), description="10-bar rate of change"),
            FeatureSpec("stoch_k", "momentum", 15, base, description="Stochastic %K (14)"),
            FeatureSpec("stoch_d", "momentum", 18, base,
                        dependencies=("stoch_k",), description="Stochastic %D (3-period SMA of %K)"),
            FeatureSpec("williams_r", "momentum", 15, base, description="Williams %R (14)"),
        ]

    def compute(self, bars: pl.DataFrame) -> pl.DataFrame:
        eps = 1e-10

        # RSI helper
        def _rsi(period: int, alias: str) -> list[pl.Expr]:
            delta = pl.col("close").diff()
            gain = delta.clip(lower_bound=0.0).ewm_mean(span=period, adjust=False)
            loss = (-delta.clip(upper_bound=0.0)).ewm_mean(span=period, adjust=False)
            rs = gain / (loss + eps)
            return [(100 - 100 / (1 + rs)).alias(alias)]

        # EMA helper
        def _ema(col: str, span: int) -> pl.Expr:
            return pl.col(col).ewm_mean(span=span, adjust=False)

        # Stochastic: %K = (C - L14) / (H14 - L14) * 100
        lowest_14 = pl.col("low").rolling_min(window_size=14, min_samples=7)
        highest_14 = pl.col("high").rolling_max(window_size=14, min_samples=7)
        stoch_k_expr = ((pl.col("close") - lowest_14) / (highest_14 - lowest_14 + eps) * 100)

        bars = bars.with_columns(
            # RSI
            *_rsi(14, "rsi_14"),
            *_rsi(7, "rsi_7"),
            # MACD
            (_ema("close", 12) - _ema("close", 26)).alias("macd_line"),
            # ROC
            (pl.col("close") / pl.col("close").shift(5) - 1).alias("roc_5"),
            (pl.col("close") / pl.col("close").shift(10) - 1).alias("roc_10"),
            # Stochastic %K
            stoch_k_expr.alias("stoch_k"),
            # Williams %R
            ((highest_14 - pl.col("close")) / (highest_14 - lowest_14 + eps) * -100).alias("williams_r"),
        )

        # MACD signal and histogram (depend on macd_line)
        bars = bars.with_columns(
            pl.col("macd_line").ewm_mean(span=9, adjust=False).alias("macd_signal"),
        )
        bars = bars.with_columns(
            (pl.col("macd_line") - pl.col("macd_signal")).alias("macd_histogram"),
            # Stochastic %D (3-period SMA of %K)
            pl.col("stoch_k").rolling_mean(window_size=3, min_samples=1).alias("stoch_d"),
        )

        return bars
