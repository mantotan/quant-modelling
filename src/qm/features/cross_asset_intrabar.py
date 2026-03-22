"""Cross-asset intra-bar feature augmentation for Pulse training.

Adds BTC tick features to non-BTC datasets using direct bar_index
alignment. Verified: ETH bar_indices have 100% overlap with BTC;
SOL/XRP are proper subsets (288/96/24 fewer bars for 5m/15m/1h).

Direct ``bar_index=N → btc_bar_index=N`` lookup works for all assets.
No raw bar loading or timestamp join needed.
"""

from __future__ import annotations

import logging

import numpy as np

from qm.features.intrabar import TICK_FEATURE_NAMES
from qm.model.targets.intrabar import IntraBarDataset

logger = logging.getLogger(__name__)

# Map cross-asset feature name → source tick feature name in BTC calculator.
# Autoresearch iterates by selecting subsets from knobs.json.
CROSS_ASSET_TICK_MAP: dict[str, str] = {
    "btc_distance_from_open": "distance_from_open",
    "btc_vol_norm_distance": "vol_norm_distance",
    "btc_partial_range": "partial_range",
    "btc_partial_bar_position": "partial_bar_position",
    "btc_elapsed_pct": "elapsed_pct",
    "btc_time_remaining_pct": "time_remaining_pct",
    "btc_volume_ratio_partial": "volume_ratio_partial",
    "btc_trade_intensity": "trade_intensity",
}


def augment_cross_asset(
    target_ds: IntraBarDataset,
    btc_ds: IntraBarDataset,
    cross_feature_names: list[str],
) -> IntraBarDataset:
    """Augment target dataset with BTC intra-bar tick features.

    Uses direct bar_index + time_pct lookup (no timestamp join needed).
    Verified: all non-BTC bar_indices are subsets of BTC bar_indices.
    Unmatched samples get zero-filled (LightGBM handles natively).

    Args:
        target_ds: Non-BTC IntraBarDataset.
        btc_ds: BTC IntraBarDataset (same timeframe).
        cross_feature_names: Which ``btc_*`` features to add
            (must be keys of ``CROSS_ASSET_TICK_MAP``).

    Returns:
        New IntraBarDataset with X column-stacked, feature_names extended.

    Raises:
        ValueError: If a feature name is not in ``CROSS_ASSET_TICK_MAP``.
    """
    # Resolve source tick indices by name
    source_indices: list[int] = []
    for name in cross_feature_names:
        source_name = CROSS_ASSET_TICK_MAP.get(name)
        if source_name is None:
            msg = (
                f"Unknown cross-asset feature: {name!r}. "
                f"Must be one of {sorted(CROSS_ASSET_TICK_MAP)}"
            )
            raise ValueError(msg)
        source_indices.append(TICK_FEATURE_NAMES.index(source_name))

    n_cross = len(cross_feature_names)
    n_samples = len(target_ds.y)

    # Build BTC lookup: (bar_idx, round(time_pct, 4)) → BTC tick features
    btc_lookup: dict[tuple[int, float], np.ndarray] = {}
    for i in range(len(btc_ds.y)):
        key = (int(btc_ds.bar_indices[i]), round(float(btc_ds.time_pcts[i]), 4))
        btc_lookup[key] = btc_ds.X[i, source_indices]

    # Augment each target sample
    cross_feats = np.zeros((n_samples, n_cross), dtype=np.float64)
    matched = 0
    for i in range(n_samples):
        key = (
            int(target_ds.bar_indices[i]),
            round(float(target_ds.time_pcts[i]), 4),
        )
        btc_tick = btc_lookup.get(key)
        if btc_tick is not None:
            cross_feats[i] = btc_tick
            matched += 1

    match_pct = 100.0 * matched / n_samples if n_samples > 0 else 0.0
    logger.info(
        "Cross-asset: matched %d/%d samples (%.1f%%), %d features added",
        matched,
        n_samples,
        match_pct,
        n_cross,
    )

    if match_pct < 80:
        logger.warning(
            "Low cross-asset match rate (%.1f%%). Check dataset alignment.",
            match_pct,
        )

    return IntraBarDataset(
        X=np.column_stack([target_ds.X, cross_feats]),
        y=target_ds.y,
        market_probs=target_ds.market_probs,
        bar_indices=target_ds.bar_indices,
        time_pcts=target_ds.time_pcts,
        feature_names=target_ds.feature_names + list(cross_feature_names),
    )
