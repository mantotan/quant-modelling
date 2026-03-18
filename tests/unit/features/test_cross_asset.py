"""Tests for cross-asset feature computation."""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import numpy as np
import polars as pl
import pytest

from qm.core.types import Asset, Timeframe
from qm.features.cross_asset import (
    CrossAssetPipeline,
    compute_cross_asset_features,
)


def _make_featured_df(n: int, start: datetime, seed: int = 42) -> pl.DataFrame:
    """Create a synthetic featured DataFrame with required columns."""
    rng = np.random.RandomState(seed)
    times = [start + timedelta(minutes=5 * i) for i in range(n)]
    close = 100.0 + np.cumsum(rng.randn(n) * 0.5)
    open_ = close + rng.randn(n) * 0.1

    return pl.DataFrame({
        "time": times,
        "open": open_,
        "high": close + abs(rng.randn(n) * 0.3),
        "low": close - abs(rng.randn(n) * 0.3),
        "close": close,
        "volume": rng.uniform(100, 1000, n),
        "return_1": np.diff(close, prepend=close[0]) / close,
        "return_5": rng.randn(n) * 0.01,
        "rsi_14": rng.uniform(20, 80, n),
        "realized_vol_10": rng.uniform(0.01, 0.05, n),
        "volume_ratio": rng.uniform(0.5, 2.0, n),
    })


class TestComputeCrossAssetFeatures:
    def test_columns_exist(self):
        """All 9 cross-asset feature columns should be present."""
        base = datetime(2026, 1, 1, tzinfo=timezone.utc)
        target = _make_featured_df(100, base, seed=1)
        context = _make_featured_df(100, base, seed=2)

        result = compute_cross_asset_features(target, context, "btc")

        expected_cols = [
            "btc_return_1", "btc_return_5", "btc_rsi_14",
            "btc_realized_vol_10", "btc_volume_ratio",
            "spread_return_1", "spread_return_5",
            "relative_strength", "correlation_30",
        ]
        for col in expected_cols:
            assert col in result.columns, f"Missing column: {col}"

    def test_left_join_preserves_target_rows(self):
        """Left join should keep all target rows even when context has gaps."""
        base = datetime(2026, 1, 1, tzinfo=timezone.utc)
        target = _make_featured_df(100, base, seed=1)

        # Context missing bars 40-59 (20-bar gap)
        context_full = _make_featured_df(100, base, seed=2)
        context_with_gap = pl.concat([
            context_full.slice(0, 40),
            context_full.slice(60, 40),
        ])

        result = compute_cross_asset_features(target, context_with_gap, "btc")

        # All 100 target rows preserved
        assert len(result) == 100

        # Context features are null in the gap
        gap_rows = result.slice(40, 20)
        assert gap_rows["btc_return_1"].null_count() == 20

    def test_no_lookahead_bias(self):
        """Cross-asset features at time t should only use data at or before t."""
        base = datetime(2026, 1, 1, tzinfo=timezone.utc)
        target = _make_featured_df(50, base, seed=1)
        context = _make_featured_df(50, base, seed=2)

        result = compute_cross_asset_features(target, context, "btc")

        # btc_return_1 at row i should equal context's return_1 at the same timestamp
        # (return_1 is computed from close[t]/close[t-1], which is backward-looking)
        for i in range(1, 50):
            ctx_val = context["return_1"][i]
            result_val = result["btc_return_1"][i]
            assert result_val == pytest.approx(ctx_val, abs=1e-10)

    def test_spread_arithmetic(self):
        """spread_return_1 should equal return_1 - btc_return_1."""
        base = datetime(2026, 1, 1, tzinfo=timezone.utc)
        target = _make_featured_df(50, base, seed=1)
        context = _make_featured_df(50, base, seed=2)

        result = compute_cross_asset_features(target, context, "btc")

        spread = result["spread_return_1"]
        expected = result["return_1"] - result["btc_return_1"]

        for i in range(50):
            if spread[i] is not None and expected[i] is not None:
                assert spread[i] == pytest.approx(expected[i], abs=1e-10)

    def test_null_handling_no_crash(self):
        """Nulls from left join shouldn't crash downstream operations."""
        base = datetime(2026, 1, 1, tzinfo=timezone.utc)
        target = _make_featured_df(50, base, seed=1)
        # Context with only 30 bars (target has 50)
        context = _make_featured_df(30, base, seed=2)

        result = compute_cross_asset_features(target, context, "btc")

        # Should not crash
        assert len(result) == 50
        # fill_null should work (used in training)
        filled = result.fill_null(0)
        assert filled["btc_return_1"].null_count() == 0


class TestCrossAssetPipeline:
    def _make_mock_store(self) -> MagicMock:
        """Create a mock ParquetStore that returns synthetic data."""
        base = datetime(2026, 1, 1, tzinfo=timezone.utc)
        store = MagicMock()

        def read_bars(asset, timeframe, **kwargs):
            seed = {Asset.BTC: 1, Asset.ETH: 2, Asset.SOL: 3, Asset.XRP: 4}.get(asset, 0)
            n = 200
            rng = np.random.RandomState(seed)
            times = [base + timedelta(minutes=5 * i) for i in range(n)]
            close = 100.0 + np.cumsum(rng.randn(n) * 0.5)
            return pl.DataFrame({
                "time": times,
                "open": close + rng.randn(n) * 0.1,
                "high": close + abs(rng.randn(n) * 0.3),
                "low": close - abs(rng.randn(n) * 0.3),
                "close": close,
                "volume": rng.uniform(100, 1000, n),
                "trade_count": rng.randint(10, 100, n),
                "vwap": close + rng.randn(n) * 0.05,
            })

        store.read_bars = read_bars
        return store

    def test_caching(self):
        """BTC features should be computed only once across multiple calls."""
        store = self._make_mock_store()
        cross = CrossAssetPipeline(store, Timeframe.M5)

        cross.compute(Asset.ETH)
        cross.compute(Asset.SOL)

        # BTC should be in cache (used as context for both)
        assert Asset.BTC in cross._featured_cache
        assert Asset.ETH in cross._featured_cache
        assert Asset.SOL in cross._featured_cache

    def test_btc_gets_eth_context(self):
        """BTC model should use ETH-prefixed features."""
        store = self._make_mock_store()
        cross = CrossAssetPipeline(store, Timeframe.M5)

        names = cross.feature_names(Asset.BTC)
        assert "eth_return_1" in names
        assert "btc_return_1" not in names  # BTC shouldn't reference itself

    def test_feature_names_include_cross_asset(self):
        """Feature names for ETH should include btc_* and spread_* features."""
        store = self._make_mock_store()
        cross = CrossAssetPipeline(store, Timeframe.M5)

        names = cross.feature_names(Asset.ETH)
        assert "btc_return_1" in names
        assert "btc_rsi_14" in names
        assert "spread_return_1" in names
        assert "correlation_30" in names

    def test_compute_returns_enriched_df(self):
        """compute() should return DataFrame with more columns than base pipeline."""
        store = self._make_mock_store()
        cross = CrossAssetPipeline(store, Timeframe.M5)

        result = cross.compute(Asset.ETH)

        # Should have base OHLCV + base features + cross-asset features
        assert "btc_return_1" in result.columns
        assert "spread_return_1" in result.columns
        assert len(result) > 0

    def test_max_lookback(self):
        """max_lookback should be at least 30 (for correlation_30)."""
        store = self._make_mock_store()
        cross = CrossAssetPipeline(store, Timeframe.M5)
        assert cross.max_lookback >= 30
