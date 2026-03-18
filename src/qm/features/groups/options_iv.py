"""Options implied volatility features from Deribit IV index.

After join_asof via CrossAssetPipeline, the bars DataFrame will
contain ``options_iv_iv_index`` (the ``options_iv_`` prefix comes
from the alpha store name).

Graceful no-op: if ``options_iv_iv_index`` is absent the compute()
method returns the input unchanged.

Feature list
------------
- ``iv_atm``           — ATM implied volatility (raw IV index)
- ``iv_skew``          — proxy for skew via IV vs realised vol spread
- ``iv_term_spread``   — IV change rate (short vs long window SMA)
- ``iv_change_1h``     — 1-hour IV change (12 bars at 5m cadence)
- ``iv_percentile_30d``— percentile rank of IV over rolling 30-day window

Note: Deribit only supports BTC and ETH. For SOL/XRP, this group
is a graceful no-op.
"""

from __future__ import annotations

import polars as pl

from qm.features.base import FeatureCalculatorBase
from qm.features.registry import FeatureSpec

# Column from join_alpha_asof(prefix="options_iv")
_SRC_COL = "options_iv_iv_index"

# Window sizes
_SHORT_SMA = 6    # ~30min at 5m cadence
_LONG_SMA = 24    # ~2h at 5m cadence
_CHANGE_BARS = 12  # ~1h at 5m cadence
_PCTILE_WINDOW = 8640  # ~30 days at 5m cadence


class OptionsIVFeatures(FeatureCalculatorBase):
    """Derives trading features from options implied volatility."""

    name = "options_iv"
    lookback = _LONG_SMA

    def specs(self) -> list[FeatureSpec]:
        return [
            FeatureSpec(
                "iv_atm", "options_iv", 1, (_SRC_COL,),
                description="ATM implied volatility from Deribit IV index",
            ),
            FeatureSpec(
                "iv_skew", "options_iv", 1,
                (_SRC_COL, "realized_vol_10"),
                description="IV minus realised vol — skew proxy",
            ),
            FeatureSpec(
                "iv_term_spread", "options_iv", _LONG_SMA, (_SRC_COL,),
                description="Short SMA minus long SMA of IV — term structure",
            ),
            FeatureSpec(
                "iv_change_1h", "options_iv", _CHANGE_BARS + 1, (_SRC_COL,),
                description="IV change over last 1 hour (12 bars)",
            ),
            FeatureSpec(
                "iv_percentile_30d", "options_iv", _PCTILE_WINDOW, (_SRC_COL,),
                description="Percentile rank of IV over 30-day rolling window",
            ),
        ]

    def compute(self, bars: pl.DataFrame) -> pl.DataFrame:
        """Compute IV features. No-op if IV column is absent."""
        if _SRC_COL not in bars.columns:
            return bars

        # 1. ATM IV (raw, forward-filled by join_asof)
        bars = bars.with_columns(
            pl.col(_SRC_COL).alias("iv_atm"),
        )

        # 2. IV skew proxy: IV - realised vol
        if "realized_vol_10" in bars.columns:
            bars = bars.with_columns(
                (pl.col(_SRC_COL) - pl.col("realized_vol_10"))
                .alias("iv_skew"),
            )
        else:
            bars = bars.with_columns(
                pl.lit(None, dtype=pl.Float64).alias("iv_skew"),
            )

        # 3. Term spread: short SMA - long SMA
        bars = bars.with_columns(
            (
                pl.col(_SRC_COL).rolling_mean(
                    window_size=_SHORT_SMA, min_samples=1
                )
                - pl.col(_SRC_COL).rolling_mean(
                    window_size=_LONG_SMA, min_samples=1
                )
            ).alias("iv_term_spread"),
        )

        # 4. 1-hour IV change
        bars = bars.with_columns(
            pl.col(_SRC_COL).pct_change(n=_CHANGE_BARS)
            .alias("iv_change_1h"),
        )

        # 5. 30-day percentile (min-max normalisation over rolling window)
        iv_min = pl.col(_SRC_COL).rolling_min(
            window_size=_PCTILE_WINDOW, min_samples=1
        )
        iv_max = pl.col(_SRC_COL).rolling_max(
            window_size=_PCTILE_WINDOW, min_samples=1
        )
        bars = bars.with_columns(
            (
                (pl.col(_SRC_COL) - iv_min) / (iv_max - iv_min + 1e-12)
            ).alias("iv_percentile_30d"),
        )

        return bars
