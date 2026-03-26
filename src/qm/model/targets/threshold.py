"""Threshold direction target: predict direction only for large moves.

Drops bars where |return| < threshold from training (null target),
keeping only clear directional signals. This increases signal density
at the cost of reduced training data.
"""

from __future__ import annotations

import polars as pl


class ThresholdDirectionTarget:
    """Target: 1 if large up move, 0 if large down move, null if small move.

    Rows with null targets should be dropped from training. The model
    only learns to predict direction when the move is large enough
    to be distinguishable from noise.

    Args:
        min_percentile: Minimum percentile of |return| to keep.
            0.30 means drop the smallest 30% of moves.
        lookback: Rolling window for computing the percentile threshold.
    """

    def __init__(
        self, min_percentile: float = 0.30, lookback: int = 500,
    ) -> None:
        if not 0.0 < min_percentile < 1.0:
            msg = f"min_percentile must be in (0, 1), got {min_percentile}"
            raise ValueError(msg)
        self.min_percentile = min_percentile
        self.lookback = lookback

    def compute(self, bars: pl.DataFrame) -> pl.Series:
        """Compute threshold direction target.

        Returns: Series with 1 (up), 0 (down), or null (small move / no data).
        """
        # Use with_columns + select to evaluate pl.when in DataFrame context
        result = bars.with_columns(
            ((pl.col("close").shift(-1) - pl.col("open").shift(-1))
             / pl.col("open").shift(-1)).alias("_thr_ret"),
        ).with_columns(
            pl.col("_thr_ret").abs().rolling_quantile(
                quantile=self.min_percentile,
                window_size=self.lookback,
                min_samples=self.lookback // 2,
            ).alias("_thr_threshold"),
        ).select(
            pl.when(pl.col("_thr_ret") > pl.col("_thr_threshold")).then(1)
            .when(pl.col("_thr_ret") < -pl.col("_thr_threshold")).then(0)
            .otherwise(None)
            .cast(pl.Int8)
            .alias("target"),
        )
        return result["target"]

    def compute_with_meta(self, bars: pl.DataFrame) -> pl.DataFrame:
        """Compute target with metadata for analysis."""
        target = self.compute(bars)
        ret = (bars["close"].shift(-1) - bars["open"].shift(-1)) / bars["open"].shift(-1)
        return bars.with_columns(target, ret.alias("target_return"))
