"""Cross-asset feature computation for Sentinel models.

Adds context-asset features (e.g., BTC returns/momentum/volatility) to
the target asset's feature set. BTC leads alts by minutes, so BTC-derived
features are strong predictors for ETH/SOL/XRP direction.

Uses left join on timestamp — LightGBM handles nulls natively (sends them
down the best split direction), so missing context bars produce null
features rather than dropped rows.
"""

from __future__ import annotations

import logging

import polars as pl

from qm.core.types import Asset, Timeframe
from qm.data.storage.parquet import ParquetStore
from qm.features.pipeline import FeaturePipeline

logger = logging.getLogger(__name__)

# Context features to pull from the reference asset
CONTEXT_FEATURES = ["return_1", "return_5", "rsi_14", "realized_vol_10", "volume_ratio"]

# Default context mapping: which asset provides context for which
DEFAULT_CONTEXT_MAP: dict[Asset, Asset] = {
    Asset.ETH: Asset.BTC,
    Asset.SOL: Asset.BTC,
    Asset.XRP: Asset.BTC,
    Asset.BTC: Asset.ETH,
}


def compute_cross_asset_features(
    target_df: pl.DataFrame,
    context_df: pl.DataFrame,
    context_prefix: str,
) -> pl.DataFrame:
    """Add cross-asset features from context asset to target asset DataFrame.

    Args:
        target_df: Target asset's bars with base features computed.
        context_df: Context asset's bars with base features computed.
        context_prefix: Prefix for context feature names (e.g., "btc", "eth").

    Returns:
        Target DataFrame with 9 additional cross-asset feature columns.
        Nulls where context has gaps (LightGBM handles nulls natively).
    """
    # Select and rename context features
    context_cols = [pl.col("time")]
    for feat in CONTEXT_FEATURES:
        if feat in context_df.columns:
            context_cols.append(pl.col(feat).alias(f"{context_prefix}_{feat}"))

    # Also bring context return_1 unaliased for derived features
    if "return_1" in context_df.columns:
        context_cols.append(pl.col("return_1").alias(f"_ctx_return_1"))

    context_subset = context_df.select(context_cols)

    # Left join: preserve all target rows, nulls where context has gaps
    joined = target_df.join(context_subset, on="time", how="left")

    # Derived features
    ctx_r1 = f"{context_prefix}_return_1"
    ctx_r5 = f"{context_prefix}_return_5"

    expressions = []

    # Spread features: target minus context returns
    if "return_1" in joined.columns and ctx_r1 in joined.columns:
        expressions.append(
            (pl.col("return_1") - pl.col(ctx_r1)).alias("spread_return_1")
        )
    if "return_5" in joined.columns and ctx_r5 in joined.columns:
        expressions.append(
            (pl.col("return_5") - pl.col(ctx_r5)).alias("spread_return_5")
        )

    # Relative strength: rolling 20-bar cumulative return ratio
    if "return_1" in joined.columns and "_ctx_return_1" in joined.columns:
        expressions.append(
            (
                pl.col("return_1").rolling_sum(window_size=20, min_samples=5)
                / (pl.col("_ctx_return_1").rolling_sum(window_size=20, min_samples=5) + 1e-10)
            ).alias("relative_strength")
        )

        # Rolling correlation between target and context returns
        expressions.append(
            pl.rolling_corr(
                pl.col("return_1"),
                pl.col("_ctx_return_1"),
                window_size=30,
                min_samples=10,
            ).alias("correlation_30")
        )

    if expressions:
        joined = joined.with_columns(expressions)

    # Drop temporary column
    if "_ctx_return_1" in joined.columns:
        joined = joined.drop("_ctx_return_1")

    return joined


class CrossAssetPipeline:
    """Wraps FeaturePipeline to add cross-asset features.

    Computes base features per asset (cached), then joins cross-asset
    features from the context asset. BTC features are computed once
    and reused for ETH/SOL/XRP.

    Usage:
        cross = CrossAssetPipeline(store, Timeframe.M5)
        featured_eth = cross.compute(Asset.ETH)  # includes btc_* features
    """

    def __init__(
        self,
        store: ParquetStore,
        timeframe: Timeframe,
        pipeline: FeaturePipeline | None = None,
        context_map: dict[Asset, Asset] | None = None,
        metrics_store: ParquetStore | None = None,
    ) -> None:
        self._store = store
        self._timeframe = timeframe
        self._pipeline = pipeline or FeaturePipeline()
        self._context_map = context_map or DEFAULT_CONTEXT_MAP
        self._metrics_store = metrics_store
        self._featured_cache: dict[Asset, pl.DataFrame] = {}

    def _get_featured(self, asset: Asset) -> pl.DataFrame:
        """Load bars, join metrics if available, compute base features, with caching."""
        if asset not in self._featured_cache:
            bars = self._store.read_bars(asset, self._timeframe)
            if bars.is_empty():
                self._featured_cache[asset] = bars
            else:
                # Join metrics data before feature computation (so derivatives group can use it)
                if self._metrics_store is not None:
                    metrics = self._metrics_store.read_metrics(asset)
                    if not metrics.is_empty():
                        bars = bars.join(metrics, on="time", how="left")
                        logger.debug("Joined %d metrics rows for %s", len(metrics), asset.value)
                self._featured_cache[asset] = self._pipeline.compute(bars)
                logger.debug("Computed features for %s (%d bars)", asset.value, len(bars))
        return self._featured_cache[asset]

    def compute(self, asset: Asset) -> pl.DataFrame:
        """Compute features for asset including cross-asset context."""
        featured = self._get_featured(asset)
        if featured.is_empty():
            return featured

        context_asset = self._context_map.get(asset)
        if context_asset is None:
            return featured

        context_featured = self._get_featured(context_asset)
        if context_featured.is_empty():
            logger.warning("No context data for %s (context: %s)", asset.value, context_asset.value)
            return featured

        prefix = context_asset.value.lower()
        result = compute_cross_asset_features(featured, context_featured, prefix)
        logger.debug(
            "Added %d cross-asset features (%s) to %s",
            len(result.columns) - len(featured.columns),
            prefix,
            asset.value,
        )
        return result

    def feature_names(self, asset: Asset) -> list[str]:
        """Base pipeline feature names + cross-asset feature names.

        Derivatives features (oi_change, ls_ratio, etc.) are already included
        in base pipeline feature_names via the DerivativesFeatures group registry.
        """
        base = list(self._pipeline.feature_names)
        context_asset = self._context_map.get(asset)
        if context_asset is None:
            return base
        prefix = context_asset.value.lower()
        cross = [f"{prefix}_{f}" for f in CONTEXT_FEATURES]
        derived = ["spread_return_1", "spread_return_5", "relative_strength", "correlation_30"]
        return base + cross + derived

    @property
    def max_lookback(self) -> int:
        """Max lookback across base features and cross-asset features."""
        return max(self._pipeline.max_lookback, 30)
