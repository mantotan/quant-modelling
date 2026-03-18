"""Tests for the feature pipeline and individual feature groups."""

from datetime import datetime, timedelta, timezone

import numpy as np
import polars as pl
import pytest

from qm.features.pipeline import FeaturePipeline
from qm.features.registry import GLOBAL_REGISTRY


def _make_ohlcv(n: int = 100, seed: int = 42) -> pl.DataFrame:
    """Generate synthetic OHLCV data for testing."""
    rng = np.random.RandomState(seed)
    base_price = 84000.0
    prices = base_price + np.cumsum(rng.randn(n) * 50)

    base_time = datetime(2026, 3, 18, 0, 0, 0, tzinfo=timezone.utc)
    times = [base_time + timedelta(minutes=5 * i) for i in range(n)]

    return pl.DataFrame({
        "time": times,
        "open": prices + rng.randn(n) * 10,
        "high": prices + abs(rng.randn(n) * 30) + 10,
        "low": prices - abs(rng.randn(n) * 30) - 10,
        "close": prices + rng.randn(n) * 10,
        "volume": abs(rng.randn(n) * 100) + 50,
        "trade_count": rng.randint(100, 2000, n),
        "vwap": prices + rng.randn(n) * 5,
    })


class TestFeatureRegistry:
    def test_features_auto_registered(self):
        """Importing pipeline should auto-register all feature groups."""
        # Import triggers registration
        from qm.features.pipeline import FeaturePipeline  # noqa
        assert len(GLOBAL_REGISTRY) > 20, f"Only {len(GLOBAL_REGISTRY)} features registered"

    def test_compute_order_has_no_cycles(self):
        order = GLOBAL_REGISTRY.compute_order()
        seen: set[str] = set()
        for spec in order:
            for dep in spec.dependencies:
                assert dep in seen or dep not in {s.name for s in order}, \
                    f"Feature '{spec.name}' depends on '{dep}' which hasn't been computed yet"
            seen.add(spec.name)


class TestFeaturePipeline:
    def test_pipeline_runs_without_error(self):
        df = _make_ohlcv(100)
        pipeline = FeaturePipeline()
        result = pipeline.compute(df)
        assert len(result.columns) > len(df.columns)

    def test_pipeline_adds_expected_features(self):
        df = _make_ohlcv(100)
        pipeline = FeaturePipeline()
        result = pipeline.compute(df)

        # Check key features exist
        expected = ["return_1", "rsi_14", "realized_vol_10", "volume_ratio", "hour_sin"]
        for feat in expected:
            assert feat in result.columns, f"Missing feature: {feat}"

    def test_pipeline_preserves_original_columns(self):
        df = _make_ohlcv(50)
        original_cols = set(df.columns)
        pipeline = FeaturePipeline()
        result = pipeline.compute(df)
        assert original_cols.issubset(set(result.columns))

    def test_pipeline_row_count_unchanged(self):
        df = _make_ohlcv(80)
        pipeline = FeaturePipeline()
        result = pipeline.compute(df)
        assert len(result) == len(df)

    def test_no_all_null_features(self):
        """No feature should be entirely null (after lookback warmup)."""
        df = _make_ohlcv(200)
        pipeline = FeaturePipeline()
        result = pipeline.compute(df)

        lookback = pipeline.max_lookback
        after_warmup = result.slice(lookback)

        for col in result.columns:
            if col in df.columns:
                continue
            null_count = after_warmup[col].null_count()
            total = len(after_warmup)
            assert null_count < total, f"Feature '{col}' is all null after warmup"

    def test_group_filtering(self):
        df = _make_ohlcv(100)
        pipeline = FeaturePipeline(groups=["price"])
        result = pipeline.compute(df)

        assert "return_1" in result.columns
        assert "rsi_14" not in result.columns  # momentum not included

    def test_feature_names_property(self):
        pipeline = FeaturePipeline()
        names = pipeline.feature_names
        assert len(names) > 20
        assert "return_1" in names
