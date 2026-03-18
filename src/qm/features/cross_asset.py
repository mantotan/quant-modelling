"""Cross-asset feature computation for Sentinel models.

Adds context-asset features (e.g., BTC returns/momentum/volatility) to
the target asset's feature set. BTC leads alts by minutes, so BTC-derived
features are strong predictors for ETH/SOL/XRP direction.

Uses left join on timestamp — LightGBM handles nulls natively (sends them
down the best split direction), so missing context bars produce null
features rather than dropped rows.

Alpha stores (funding, liquidation, options IV, etc.) are joined via
``join_asof`` so data with different cadences (e.g., 8h funding rates)
aligns correctly to bar timestamps without introducing look-ahead bias.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

import polars as pl

from qm.core.types import Asset, Timeframe
from qm.data.storage.parquet import ParquetStore
from qm.features.pipeline import FeaturePipeline

logger = logging.getLogger(__name__)

# Type alias for alpha store reader callables.
# Each callable takes (asset,) and returns a DataFrame with a "time" column.
AlphaReader = Callable[[Asset], pl.DataFrame]

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
        context_cols.append(pl.col("return_1").alias("_ctx_return_1"))

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


def join_alpha_asof(
    bars: pl.DataFrame,
    alpha_df: pl.DataFrame,
    prefix: str,
    *,
    tolerance: str | None = None,
    strategy: str = "backward",
) -> pl.DataFrame:
    """Join alpha-source data to bar timestamps via ``join_asof``.

    Alpha data (funding rates, liquidation snapshots, options IV, etc.)
    often arrives at a different cadence than OHLCV bars. ``join_asof``
    picks the most recent alpha row at-or-before each bar's timestamp,
    preventing look-ahead bias.

    Args:
        bars: Target OHLCV DataFrame with a ``time`` column (sorted).
        alpha_df: Alpha-source DataFrame with a ``time`` column (sorted).
            All non-``time`` columns will be prefixed with *prefix*.
        prefix: String prepended to every alpha column name
            (e.g., ``"funding"`` → ``funding_rate``, ``funding_predicted``).
        tolerance: Optional maximum time gap (e.g., ``"8h"``).
            Rows in *bars* farther than this from any alpha row get nulls.
        strategy: Join strategy — ``"backward"`` (default, no look-ahead)
            or ``"forward"``.

    Returns:
        *bars* with alpha columns appended. Rows without a matching alpha
        observation within *tolerance* contain nulls (LightGBM-safe).
    """
    if alpha_df.is_empty() or "time" not in alpha_df.columns:
        return bars

    # Rename alpha columns with prefix (skip "time")
    rename_map: dict[str, str] = {}
    for col in alpha_df.columns:
        if col != "time":
            rename_map[col] = f"{prefix}_{col}"
    alpha_renamed = alpha_df.rename(rename_map)

    # Both sides must be sorted on the join key
    bars_sorted = bars.sort("time") if not bars["time"].is_sorted() else bars
    alpha_sorted = (
        alpha_renamed.sort("time")
        if not alpha_renamed["time"].is_sorted()
        else alpha_renamed
    )

    kwargs: dict[str, object] = {
        "on": "time",
        "strategy": strategy,
    }
    if tolerance is not None:
        kwargs["tolerance"] = tolerance

    result = bars_sorted.join_asof(alpha_sorted, **kwargs)  # type: ignore[arg-type]
    return result


class CrossAssetPipeline:
    """Wraps FeaturePipeline to add cross-asset and alpha-source features.

    Computes base features per asset (cached), then joins cross-asset
    features from the context asset. BTC features are computed once
    and reused for ETH/SOL/XRP.

    Alpha stores supply auxiliary time-series (funding rates, liquidation
    snapshots, options IV, Polymarket microstructure) that are joined via
    ``join_asof`` before feature computation so that feature groups can
    consume the new columns.

    Usage:
        cross = CrossAssetPipeline(
            store, Timeframe.M5,
            alpha_stores={"funding": funding_store},
        )
        featured_eth = cross.compute(Asset.ETH)  # includes funding + btc_* features
    """

    def __init__(
        self,
        store: ParquetStore,
        timeframe: Timeframe,
        pipeline: FeaturePipeline | None = None,
        context_map: dict[Asset, Asset] | None = None,
        metrics_store: ParquetStore | None = None,
        alpha_stores: dict[str, ParquetStore] | None = None,
        alpha_tolerances: dict[str, str] | None = None,
    ) -> None:
        """Initialise the cross-asset pipeline.

        Args:
            store: Primary OHLCV ParquetStore.
            timeframe: Bar timeframe being processed.
            pipeline: Feature computation pipeline (default: all groups).
            context_map: Asset → context-asset mapping.
            metrics_store: Legacy metrics ParquetStore (OI, L/S ratios).
            alpha_stores: Mapping of alpha source name → ParquetStore.
                Each store must implement ``read_metrics(asset)`` returning
                a DataFrame with a ``time`` column.
            alpha_tolerances: Optional per-source tolerance for ``join_asof``
                (e.g., ``{"funding": "9h"}``). Sources without an entry
                use no tolerance (nearest backward match).
        """
        self._store = store
        self._timeframe = timeframe
        self._pipeline = pipeline or FeaturePipeline()
        self._context_map = context_map or DEFAULT_CONTEXT_MAP
        self._metrics_store = metrics_store
        self._alpha_stores: dict[str, ParquetStore] = alpha_stores or {}
        self._alpha_tolerances: dict[str, str] = alpha_tolerances or {}
        self._featured_cache: dict[Asset, pl.DataFrame] = {}

    def _join_alpha_stores(self, bars: pl.DataFrame, asset: Asset) -> pl.DataFrame:
        """Join all registered alpha stores to bars via join_asof."""
        for name, alpha_store in self._alpha_stores.items():
            try:
                alpha_df = alpha_store.read_metrics(asset)
            except Exception:
                logger.warning(
                    "Failed to read alpha store '%s' for %s, skipping",
                    name, asset.value,
                    exc_info=True,
                )
                continue

            if alpha_df.is_empty():
                logger.debug(
                    "Alpha store '%s' empty for %s, skipping", name, asset.value
                )
                continue

            tolerance = self._alpha_tolerances.get(name)
            bars = join_alpha_asof(
                bars, alpha_df, prefix=name, tolerance=tolerance
            )
            n_new = sum(
                1 for c in bars.columns if c.startswith(f"{name}_")
            )
            logger.debug(
                "Joined %d cols from alpha store '%s' for %s",
                n_new, name, asset.value,
            )
        return bars

    def _get_featured(self, asset: Asset) -> pl.DataFrame:
        """Load bars, join metrics + alpha stores, compute base features, with caching."""
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

                # Join alpha stores via join_asof (funding, liquidation, IV, etc.)
                bars = self._join_alpha_stores(bars, asset)

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
