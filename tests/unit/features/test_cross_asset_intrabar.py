"""Tests for cross-asset intra-bar feature augmentation."""

import numpy as np
import pytest

from qm.features.cross_asset_intrabar import (
    CROSS_ASSET_TICK_MAP,
    augment_cross_asset,
)
from qm.model.targets.intrabar import IntraBarDataset


def _make_dataset(n_bars: int, n_tp: int = 3, n_features: int = 10, seed: int = 0):
    """Create a minimal IntraBarDataset for testing."""
    rng = np.random.default_rng(seed)
    n_samples = n_bars * n_tp
    X = rng.standard_normal((n_samples, n_features))
    y = rng.integers(0, 2, n_samples).astype(np.float64)
    market_probs = rng.uniform(0.3, 0.7, n_samples)
    bar_indices = np.repeat(np.arange(n_bars), n_tp)
    time_pcts = np.tile([0.10, 0.40, 0.80], n_bars)
    feature_names = [f"feat_{i}" for i in range(n_features)]
    # Set first 8 as "tick features" with recognizable values
    feature_names[:8] = [
        "distance_from_open", "vol_norm_distance", "elapsed_pct",
        "time_remaining_pct", "partial_range", "partial_bar_position",
        "volume_ratio_partial", "trade_intensity",
    ]
    return IntraBarDataset(
        X=X, y=y, market_probs=market_probs,
        bar_indices=bar_indices, time_pcts=time_pcts,
        feature_names=feature_names,
    )


class TestAugmentCrossAsset:
    def test_full_overlap(self):
        """ETH/BTC pattern: identical bar_indices, 100% match."""
        target = _make_dataset(100, seed=0)
        btc = _make_dataset(100, seed=1)
        features = ["btc_distance_from_open", "btc_vol_norm_distance"]

        result = augment_cross_asset(target, btc, features)

        assert result.X.shape == (300, 12)  # 10 + 2 cross-asset
        assert len(result.feature_names) == 12
        assert result.feature_names[-2:] == features
        # All samples should have non-zero BTC features (since BTC dataset
        # has standard_normal values, extremely unlikely to be exactly 0)
        cross_cols = result.X[:, -2:]
        assert (cross_cols != 0).any(axis=1).sum() == 300  # all matched

    def test_partial_overlap(self):
        """SOL/BTC pattern: target has fewer bars than BTC."""
        target = _make_dataset(80, seed=0)
        btc = _make_dataset(100, seed=1)
        features = ["btc_distance_from_open"]

        result = augment_cross_asset(target, btc, features)

        assert result.X.shape == (240, 11)  # 80 bars × 3 tp × (10+1) feats
        # All 80 target bars are in BTC's 0..99 range, so 100% match
        cross_col = result.X[:, -1]
        assert (cross_col != 0).sum() == 240

    def test_no_overlap(self):
        """Target bars start at 200, BTC only has 0..99."""
        target = _make_dataset(50, seed=0)
        btc = _make_dataset(50, seed=1)
        # Shift target bar_indices beyond BTC range
        target = IntraBarDataset(
            X=target.X, y=target.y, market_probs=target.market_probs,
            bar_indices=target.bar_indices + 1000,
            time_pcts=target.time_pcts,
            feature_names=target.feature_names,
        )
        features = ["btc_distance_from_open"]

        result = augment_cross_asset(target, btc, features)

        assert result.X.shape == (150, 11)
        # All zeros since no bars overlap
        cross_col = result.X[:, -1]
        assert (cross_col != 0).sum() == 0

    def test_unknown_feature_raises(self):
        target = _make_dataset(10, seed=0)
        btc = _make_dataset(10, seed=1)

        with pytest.raises(ValueError, match="Unknown cross-asset feature"):
            augment_cross_asset(target, btc, ["btc_nonexistent_feature"])

    def test_all_four_default_features(self):
        """Test with the actual 4 features used in production."""
        target = _make_dataset(50, seed=0)
        btc = _make_dataset(50, seed=1)
        features = [
            "btc_distance_from_open", "btc_vol_norm_distance",
            "btc_partial_range", "btc_partial_bar_position",
        ]

        result = augment_cross_asset(target, btc, features)

        assert result.X.shape == (150, 14)
        assert result.feature_names[-4:] == features
        # BTC values should differ from target values
        target_dist = target.X[:, 0]  # distance_from_open
        btc_dist = result.X[:, -4]  # btc_distance_from_open
        assert not np.allclose(target_dist, btc_dist)

    def test_preserves_target_data(self):
        """Augmentation must not modify original target data."""
        target = _make_dataset(20, seed=0)
        btc = _make_dataset(20, seed=1)
        original_X = target.X.copy()

        result = augment_cross_asset(target, btc, ["btc_distance_from_open"])

        # Original columns unchanged
        np.testing.assert_array_equal(result.X[:, :10], original_X)
        np.testing.assert_array_equal(result.y, target.y)
        np.testing.assert_array_equal(result.bar_indices, target.bar_indices)
        np.testing.assert_array_equal(result.time_pcts, target.time_pcts)

    def test_empty_feature_list(self):
        """Empty feature list returns unchanged dataset."""
        target = _make_dataset(10, seed=0)
        btc = _make_dataset(10, seed=1)

        result = augment_cross_asset(target, btc, [])

        assert result.X.shape == target.X.shape
        np.testing.assert_array_equal(result.X, target.X)

    def test_all_available_features(self):
        """All 8 possible cross-asset features."""
        target = _make_dataset(10, seed=0)
        btc = _make_dataset(10, seed=1)
        features = list(CROSS_ASSET_TICK_MAP.keys())

        result = augment_cross_asset(target, btc, features)

        assert result.X.shape == (30, 10 + 8)
        assert len(result.feature_names) == 18
