"""Tests for feature selection with protected_prefixes support."""

from __future__ import annotations

import numpy as np
import polars as pl

from qm.features.selection import _is_protected, select_features


def _make_data(
    n: int = 200, n_features: int = 10, seed: int = 42
) -> tuple[pl.DataFrame, pl.Series]:
    """Create random features + binary target."""
    rng = np.random.RandomState(seed)
    target = rng.randint(0, 2, n).astype(np.float64)
    cols = {}
    for i in range(n_features):
        # Features 0-4 correlate with target, 5-9 are noise
        if i < 5:
            cols[f"feat_{i}"] = target * rng.uniform(0.1, 0.5) + rng.randn(n) * 0.5
        else:
            cols[f"feat_{i}"] = rng.randn(n)
    return pl.DataFrame(cols), pl.Series("target", target)


class TestIsProtected:
    """Test the _is_protected helper."""

    def test_match(self) -> None:
        assert _is_protected("funding_rate", ["funding_"]) is True

    def test_no_match(self) -> None:
        assert _is_protected("rsi_14", ["funding_"]) is False

    def test_multiple_prefixes(self) -> None:
        assert _is_protected("regime_vol_state", ["funding_", "regime_"]) is True

    def test_empty_prefixes(self) -> None:
        assert _is_protected("anything", []) is False

    def test_exact_prefix(self) -> None:
        assert _is_protected("funding_rate", ["funding_rate"]) is True


class TestSelectFeaturesBasic:
    """Test basic select_features without protected prefixes."""

    def test_returns_list(self) -> None:
        features, target = _make_data()
        result = select_features(features, target)
        assert isinstance(result, list)

    def test_removes_noisy_features(self) -> None:
        """Features uncorrelated with target should be dropped."""
        features, target = _make_data()
        result = select_features(features, target, min_target_corr=0.05)
        # Correlated features should survive, noise should be dropped
        assert len(result) < 10
        assert len(result) > 0

    def test_removes_high_missing(self) -> None:
        """Features with >50% nulls should be dropped."""
        features, target = _make_data(n=100)
        # Make feat_0 mostly null (60 out of 100 rows)
        idx = pl.arange(0, 100, eager=True)
        features = features.with_columns(
            pl.when(idx < 60)
            .then(None)
            .otherwise(pl.col("feat_0"))
            .alias("feat_0"),
        )
        result = select_features(features, target, missing_threshold=0.5)
        assert "feat_0" not in result

    def test_removes_collinear(self) -> None:
        """Highly correlated feature pairs should be pruned."""
        rng = np.random.RandomState(42)
        n = 200
        target = rng.randint(0, 2, n).astype(np.float64)
        base = target * 0.3 + rng.randn(n) * 0.5
        features = pl.DataFrame({
            "a": base,
            "b": base + rng.randn(n) * 0.01,  # near-identical to a
            "c": rng.randn(n) * 0.3 + target * 0.2,  # independent
        })
        result = select_features(
            features, pl.Series("t", target),
            min_target_corr=0.01, max_pairwise_corr=0.95,
        )
        # a and b are collinear — one should be removed
        assert not ("a" in result and "b" in result)
        assert "c" in result

    def test_single_feature(self) -> None:
        """Should handle single-feature case."""
        rng = np.random.RandomState(42)
        n = 100
        target = rng.randint(0, 2, n).astype(np.float64)
        features = pl.DataFrame({
            "feat_a": target * 0.3 + rng.randn(n) * 0.5,
        })
        result = select_features(features, pl.Series("t", target))
        assert "feat_a" in result


class TestProtectedPrefixes:
    """Test protected_prefixes behavior in select_features."""

    def test_protected_survives_low_correlation(self) -> None:
        """Protected features should survive Stage 2 even with low corr."""
        rng = np.random.RandomState(42)
        n = 500
        target = rng.randint(0, 2, n).astype(np.float64)
        features = pl.DataFrame({
            "rsi_14": target * 0.5 + rng.randn(n) * 0.3,  # strongly correlated
            "funding_rate": rng.randn(n),  # pure noise
            "noise_feat": rng.randn(n),  # also pure noise
        })

        # With protection: funding_rate survives despite low corr
        result_protected = select_features(
            features, pl.Series("t", target),
            min_target_corr=0.10,
            protected_prefixes=["funding_"],
        )
        assert "funding_rate" in result_protected
        assert "rsi_14" in result_protected

    def test_protected_survives_collinearity(self) -> None:
        """Protected features should survive Stage 3 collinearity pruning."""
        rng = np.random.RandomState(42)
        n = 200
        target = rng.randint(0, 2, n).astype(np.float64)
        base = target * 0.3 + rng.randn(n) * 0.5
        features = pl.DataFrame({
            "ta_feat": base,
            "funding_signal": base + rng.randn(n) * 0.01,  # collinear
        })

        # Without protection: one dropped
        result_unprotected = select_features(
            features, pl.Series("t", target),
            min_target_corr=0.01, max_pairwise_corr=0.95,
        )
        assert len(result_unprotected) == 1

        # With protection: funding_signal kept, ta_feat dropped
        result_protected = select_features(
            features, pl.Series("t", target),
            min_target_corr=0.01, max_pairwise_corr=0.95,
            protected_prefixes=["funding_"],
        )
        assert "funding_signal" in result_protected

    def test_both_protected_collinear_kept(self) -> None:
        """Two collinear protected features should both be kept."""
        rng = np.random.RandomState(42)
        n = 200
        target = rng.randint(0, 2, n).astype(np.float64)
        base = target * 0.3 + rng.randn(n) * 0.5
        features = pl.DataFrame({
            "funding_rate": base,
            "funding_sma": base + rng.randn(n) * 0.01,
        })

        result = select_features(
            features, pl.Series("t", target),
            min_target_corr=0.01, max_pairwise_corr=0.95,
            protected_prefixes=["funding_"],
        )
        assert "funding_rate" in result
        assert "funding_sma" in result

    def test_multiple_prefixes(self) -> None:
        """Multiple protected prefixes should all be respected."""
        rng = np.random.RandomState(42)
        n = 500
        target = rng.randint(0, 2, n).astype(np.float64)
        features = pl.DataFrame({
            "rsi_14": target * 0.5 + rng.randn(n) * 0.3,  # correlated
            "funding_rate": rng.randn(n),  # noise but protected
            "regime_vol_state": rng.randn(n),  # noise but protected
            "leverage_proxy": rng.randn(n),  # noise but protected
        })

        result = select_features(
            features, pl.Series("t", target),
            min_target_corr=0.10,
            protected_prefixes=["funding_", "regime_", "leverage_"],
        )
        assert "funding_rate" in result
        assert "regime_vol_state" in result
        assert "leverage_proxy" in result
        assert "rsi_14" in result

    def test_protected_still_removed_by_missing(self) -> None:
        """Protected features should still be removed if >50% missing."""
        rng = np.random.RandomState(42)
        n = 100
        target = rng.randint(0, 2, n).astype(np.float64)
        funding_vals = [None] * 60 + list(rng.randn(40))
        features = pl.DataFrame({
            "rsi_14": target * 0.3 + rng.randn(n) * 0.5,
            "funding_rate": pl.Series(funding_vals, dtype=pl.Float64),
        })

        result = select_features(
            features, pl.Series("t", target),
            missing_threshold=0.5,
            protected_prefixes=["funding_"],
        )
        # 60% missing > 50% threshold — should still be dropped
        assert "funding_rate" not in result

    def test_none_prefixes_same_as_empty(self) -> None:
        """Passing None for protected_prefixes should behave like []."""
        features, target = _make_data()
        result_none = select_features(features, target, protected_prefixes=None)
        result_empty = select_features(features, target, protected_prefixes=[])
        assert result_none == result_empty
