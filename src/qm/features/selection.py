"""Feature selection: remove noise, collinear, and unstable features.

Three-stage filter:
1. Remove features with >50% missing values
2. Remove features with <0.01 absolute correlation with target
3. Remove features with >0.95 pairwise correlation (keep higher target corr)
"""

from __future__ import annotations

import logging

import numpy as np
import polars as pl

logger = logging.getLogger(__name__)


def select_features(
    features: pl.DataFrame,
    target: pl.Series,
    missing_threshold: float = 0.5,
    min_target_corr: float = 0.01,
    max_pairwise_corr: float = 0.95,
) -> list[str]:
    """Select features using a three-stage filter.

    Args:
        features: DataFrame of feature columns (no target, no time).
        target: Target series aligned with features.
        missing_threshold: Max fraction of nulls allowed.
        min_target_corr: Minimum absolute correlation with target.
        max_pairwise_corr: Maximum pairwise correlation between features.

    Returns:
        List of selected feature column names.
    """
    feature_cols = features.columns
    logger.info(f"Starting feature selection with {len(feature_cols)} features")

    # Stage 1: Remove high-missing features
    null_fracs = {
        col: features[col].null_count() / len(features)
        for col in feature_cols
    }
    stage1 = [col for col in feature_cols if null_fracs[col] <= missing_threshold]
    dropped_1 = len(feature_cols) - len(stage1)
    logger.info(f"Stage 1: dropped {dropped_1} features (>{missing_threshold*100}% missing)")

    if not stage1:
        return []

    # Stage 2: Remove features with low target correlation
    target_np = target.to_numpy().astype(np.float64)
    target_corrs: dict[str, float] = {}
    for col in stage1:
        col_np = features[col].to_numpy().astype(np.float64)
        mask = ~(np.isnan(col_np) | np.isnan(target_np))
        if mask.sum() < 20:
            target_corrs[col] = 0.0
            continue
        corr = np.corrcoef(col_np[mask], target_np[mask])[0, 1]
        target_corrs[col] = abs(corr) if not np.isnan(corr) else 0.0

    stage2 = [col for col in stage1 if target_corrs[col] >= min_target_corr]
    dropped_2 = len(stage1) - len(stage2)
    logger.info(f"Stage 2: dropped {dropped_2} features (target corr < {min_target_corr})")

    if len(stage2) <= 1:
        return stage2

    # Stage 3: Remove collinear features (keep the one with higher target corr)
    # Build pairwise correlation matrix
    # Fill nulls with column mean (not 0) to avoid biasing correlations
    filled = features.select(stage2)
    for col in filled.columns:
        col_mean = filled[col].mean()
        filled = filled.with_columns(pl.col(col).fill_null(col_mean if col_mean is not None else 0.0))
    feature_matrix = filled.to_numpy().astype(np.float64)
    corr_matrix = np.corrcoef(feature_matrix, rowvar=False)
    np.fill_diagonal(corr_matrix, 0)

    to_remove: set[str] = set()
    n = len(stage2)
    for i in range(n):
        if stage2[i] in to_remove:
            continue
        for j in range(i + 1, n):
            if stage2[j] in to_remove:
                continue
            if abs(corr_matrix[i, j]) > max_pairwise_corr:
                # Remove the one with lower target correlation
                if target_corrs[stage2[i]] >= target_corrs[stage2[j]]:
                    to_remove.add(stage2[j])
                else:
                    to_remove.add(stage2[i])

    stage3 = [col for col in stage2 if col not in to_remove]
    dropped_3 = len(stage2) - len(stage3)
    logger.info(f"Stage 3: dropped {dropped_3} features (pairwise corr > {max_pairwise_corr})")
    logger.info(f"Selected {len(stage3)} features from {len(feature_cols)} original")

    return stage3
