"""Tests for Alpha158-inspired feature groups."""

from datetime import UTC, datetime, timedelta

import numpy as np
import polars as pl

from qm.features.pipeline import FeaturePipeline
from qm.features.registry import GLOBAL_REGISTRY


def _make_ohlcv(n: int = 200, seed: int = 42) -> pl.DataFrame:
    """Generate synthetic OHLCV data for testing."""
    rng = np.random.RandomState(seed)
    base_price = 84000.0
    prices = base_price + np.cumsum(rng.randn(n) * 50)

    base_time = datetime(2026, 3, 18, 0, 0, 0, tzinfo=UTC)
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


# ── Autocorrelation ──────────────────────────────────────────────────


class TestAutocorrelationFeatures:
    def test_computes_expected_columns(self):
        from qm.features.groups.autocorrelation import AutocorrelationFeatures

        calc = AutocorrelationFeatures()
        df = calc.compute(_make_ohlcv(200))
        expected = {"autocorr_1", "autocorr_2", "autocorr_3", "autocorr_5", "autocorr_sum"}
        assert expected.issubset(set(df.columns))

    def test_no_all_null_after_warmup(self):
        from qm.features.groups.autocorrelation import AutocorrelationFeatures

        calc = AutocorrelationFeatures()
        df = calc.compute(_make_ohlcv(200))
        # After warmup (lookback=25), values should not all be null
        tail = df.slice(30)
        for col in ["autocorr_1", "autocorr_5", "autocorr_sum"]:
            assert tail[col].null_count() < len(tail), f"{col} is all null after warmup"

    def test_autocorr_values_in_range(self):
        from qm.features.groups.autocorrelation import AutocorrelationFeatures

        calc = AutocorrelationFeatures()
        df = calc.compute(_make_ohlcv(200))
        tail = df.slice(30)
        for col in ["autocorr_1", "autocorr_2", "autocorr_3", "autocorr_5"]:
            vals = tail[col].drop_nulls().to_numpy()
            if len(vals) > 0:
                assert vals.min() >= -1.01, f"{col} has value below -1"
                assert vals.max() <= 1.01, f"{col} has value above 1"


# ── Volume-Price Divergence ──────────────────────────────────────────


class TestVolumePriceDivergenceFeatures:
    def test_computes_expected_columns(self):
        from qm.features.groups.volume_price_divergence import VolumePriceDivergenceFeatures

        calc = VolumePriceDivergenceFeatures()
        df = calc.compute(_make_ohlcv(200))
        expected = {"vp_corr_10", "vp_corr_20", "vp_divergence", "vp_corr_change"}
        assert expected.issubset(set(df.columns))

    def test_no_all_null_after_warmup(self):
        from qm.features.groups.volume_price_divergence import VolumePriceDivergenceFeatures

        calc = VolumePriceDivergenceFeatures()
        df = calc.compute(_make_ohlcv(200))
        tail = df.slice(30)
        for col in ["vp_corr_10", "vp_corr_20", "vp_divergence", "vp_corr_change"]:
            assert tail[col].null_count() < len(tail), f"{col} is all null after warmup"


# ── Range Stats ──────────────────────────────────────────────────────


class TestRangeStatsFeatures:
    def test_computes_expected_columns(self):
        from qm.features.groups.range_stats import RangeStatsFeatures

        calc = RangeStatsFeatures()
        df = calc.compute(_make_ohlcv(200))
        expected = {"range_pct_10", "range_pct_20", "range_std_10", "range_ratio"}
        assert expected.issubset(set(df.columns))

    def test_range_pct_positive(self):
        from qm.features.groups.range_stats import RangeStatsFeatures

        calc = RangeStatsFeatures()
        df = calc.compute(_make_ohlcv(200))
        tail = df.slice(30)
        vals = tail["range_pct_10"].drop_nulls().to_numpy()
        assert (vals >= 0).all(), "range_pct_10 should be non-negative"

    def test_no_all_null_after_warmup(self):
        from qm.features.groups.range_stats import RangeStatsFeatures

        calc = RangeStatsFeatures()
        df = calc.compute(_make_ohlcv(200))
        tail = df.slice(30)
        for col in ["range_pct_10", "range_pct_20", "range_std_10", "range_ratio"]:
            assert tail[col].null_count() < len(tail), f"{col} is all null after warmup"


# ── VWAP Z-Score ─────────────────────────────────────────────────────


class TestVwapZscoreFeatures:
    def test_computes_expected_columns(self):
        from qm.features.groups.vwap_zscore import VwapZscoreFeatures

        calc = VwapZscoreFeatures()
        df = calc.compute(_make_ohlcv(200))
        expected = {"vwap_zscore_10", "vwap_zscore_20", "vwap_zscore_cross"}
        assert expected.issubset(set(df.columns))

    def test_graceful_noop_without_vwap(self):
        from qm.features.groups.vwap_zscore import VwapZscoreFeatures

        calc = VwapZscoreFeatures()
        df = _make_ohlcv(200).drop("vwap")
        result = calc.compute(df)
        assert "vwap_zscore_10" not in result.columns

    def test_no_all_null_after_warmup(self):
        from qm.features.groups.vwap_zscore import VwapZscoreFeatures

        calc = VwapZscoreFeatures()
        df = calc.compute(_make_ohlcv(200))
        tail = df.slice(30)
        for col in ["vwap_zscore_10", "vwap_zscore_20", "vwap_zscore_cross"]:
            assert tail[col].null_count() < len(tail), f"{col} is all null after warmup"


# ── Rank Features ────────────────────────────────────────────────────


class TestRankFeatures:
    def test_computes_expected_columns(self):
        from qm.features.groups.rank_features import RankFeatures

        calc = RankFeatures()
        df = calc.compute(_make_ohlcv(200))
        expected = {"return_rank_20", "volume_rank_20", "range_rank_20"}
        assert expected.issubset(set(df.columns))

    def test_rank_values_in_unit_interval(self):
        from qm.features.groups.rank_features import RankFeatures

        calc = RankFeatures()
        df = calc.compute(_make_ohlcv(200))
        tail = df.slice(30)
        for col in ["volume_rank_20", "range_rank_20"]:
            vals = tail[col].drop_nulls().to_numpy()
            if len(vals) > 0:
                assert vals.min() >= -0.01, f"{col} has value below 0"
                assert vals.max() <= 1.01, f"{col} has value above 1"

    def test_no_all_null_after_warmup(self):
        from qm.features.groups.rank_features import RankFeatures

        calc = RankFeatures()
        df = calc.compute(_make_ohlcv(200))
        tail = df.slice(25)
        for col in ["return_rank_20", "volume_rank_20", "range_rank_20"]:
            assert tail[col].null_count() < len(tail), f"{col} is all null after warmup"


# ── Turnover ─────────────────────────────────────────────────────────


class TestTurnoverFeatures:
    def test_computes_expected_columns(self):
        from qm.features.groups.turnover import TurnoverFeatures

        calc = TurnoverFeatures()
        df = calc.compute(_make_ohlcv(200))
        expected = {"turnover_ratio", "turnover_trend", "turnover_accel"}
        assert expected.issubset(set(df.columns))

    def test_turnover_ratio_positive(self):
        from qm.features.groups.turnover import TurnoverFeatures

        calc = TurnoverFeatures()
        df = calc.compute(_make_ohlcv(200))
        tail = df.slice(25)
        vals = tail["turnover_ratio"].drop_nulls().to_numpy()
        assert (vals >= 0).all(), "turnover_ratio should be non-negative"

    def test_no_all_null_after_warmup(self):
        from qm.features.groups.turnover import TurnoverFeatures

        calc = TurnoverFeatures()
        df = calc.compute(_make_ohlcv(200))
        tail = df.slice(25)
        for col in ["turnover_ratio", "turnover_trend", "turnover_accel"]:
            assert tail[col].null_count() < len(tail), f"{col} is all null after warmup"


# ── Pipeline Integration ─────────────────────────────────────────────


class TestAlpha158PipelineIntegration:
    def test_pipeline_includes_new_groups(self):
        pipeline = FeaturePipeline()
        calc_names = set(pipeline._calculators.keys())
        new_groups = {
            "autocorrelation", "volume_price_divergence", "range_stats",
            "vwap_zscore", "rank_features", "turnover",
        }
        assert new_groups.issubset(calc_names), (
            f"Missing groups: {new_groups - calc_names}"
        )

    def test_feature_count_increased(self):
        """Pipeline should now have more features than before."""
        pipeline = FeaturePipeline()
        # Original ~37 features + 22 new = ~59
        assert len(pipeline.feature_names) >= 50, (
            f"Expected >=50 features, got {len(pipeline.feature_names)}"
        )

    def test_full_pipeline_computes(self):
        """All feature groups including new ones should compute without error."""
        pipeline = FeaturePipeline()
        df = pipeline.compute(_make_ohlcv(200))
        new_features = [
            "autocorr_1", "vp_corr_10", "range_pct_10",
            "vwap_zscore_10", "return_rank_20", "turnover_ratio",
        ]
        for feat in new_features:
            assert feat in df.columns, f"Missing feature {feat} in pipeline output"

    def test_registry_has_new_features(self):
        new_features = [
            "autocorr_1", "autocorr_sum",
            "vp_corr_10", "vp_divergence",
            "range_pct_10", "range_ratio",
            "vwap_zscore_10", "vwap_zscore_cross",
            "return_rank_20", "volume_rank_20",
            "turnover_ratio", "turnover_accel",
        ]
        all_names = GLOBAL_REGISTRY.all_names()
        for feat in new_features:
            assert feat in all_names, f"Feature {feat} not registered"
