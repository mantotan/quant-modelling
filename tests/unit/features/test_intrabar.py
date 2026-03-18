"""Tests for IntraBarFeatureCalculator (23 features: 8 tick + 15 historical)."""

from datetime import datetime, timezone

import numpy as np
import pytest

from qm.core.types import Asset, PartialBar, Timeframe
from qm.features.intrabar import (
    ALL_FEATURE_NAMES,
    CACHED_DEFAULTS,
    CACHED_FEATURE_NAMES,
    IntraBarFeatureCalculator,
)


def _make_partial(
    elapsed: float = 150.0,
    remaining: float = 150.0,
    open_price: float = 70000.0,
    current: float = 70200.0,
    high: float = 70300.0,
    low: float = 69900.0,
    volume: float = 50.0,
    trade_count: int = 200,
) -> PartialBar:
    base = datetime(2026, 3, 18, 12, 0, 0, tzinfo=timezone.utc)
    return PartialBar(
        window_start=base,
        window_end=base,  # not used in compute, elapsed/remaining used directly
        asset=Asset.BTC,
        timeframe=Timeframe.M5,
        open=open_price,
        high_so_far=high,
        low_so_far=low,
        current_price=current,
        volume_so_far=volume,
        trade_count=trade_count,
        elapsed_seconds=elapsed,
        remaining_seconds=remaining,
    )


@pytest.fixture
def calc() -> IntraBarFeatureCalculator:
    return IntraBarFeatureCalculator()


class TestFeatureCount:
    def test_feature_names_length(self, calc: IntraBarFeatureCalculator):
        assert len(calc.feature_names) == 23

    def test_n_features(self, calc: IntraBarFeatureCalculator):
        assert calc.n_features == 23

    def test_compute_output_shape(self, calc: IntraBarFeatureCalculator):
        partial = _make_partial()
        result = calc.compute(partial)
        assert result.shape == (23,)
        assert result.dtype == np.float64

    def test_feature_names_match_all_names(self, calc: IntraBarFeatureCalculator):
        assert calc.feature_names == ALL_FEATURE_NAMES


class TestTickFeaturesAtT0:
    """At t=0 (first tick), tick features should be ~0 or degenerate."""

    def test_distance_from_open_zero(self, calc: IntraBarFeatureCalculator):
        partial = _make_partial(
            elapsed=0.001, remaining=299.999,
            current=70000.0, high=70000.0, low=70000.0,
        )
        result = calc.compute(partial)
        # distance_from_open = (current - open) / open = 0
        assert result[0] == pytest.approx(0.0, abs=1e-8)

    def test_vol_norm_distance_zero(self, calc: IntraBarFeatureCalculator):
        partial = _make_partial(
            elapsed=0.001, remaining=299.999,
            current=70000.0, high=70000.0, low=70000.0,
        )
        result = calc.compute(partial)
        assert result[1] == pytest.approx(0.0, abs=1e-6)

    def test_elapsed_pct_near_zero(self, calc: IntraBarFeatureCalculator):
        partial = _make_partial(elapsed=0.9, remaining=299.1)
        result = calc.compute(partial)
        assert result[2] == pytest.approx(0.003, abs=0.001)

    def test_time_remaining_pct_near_one(self, calc: IntraBarFeatureCalculator):
        partial = _make_partial(elapsed=0.9, remaining=299.1)
        result = calc.compute(partial)
        assert result[3] == pytest.approx(0.997, abs=0.001)

    def test_partial_bar_position_05_when_range_zero(self, calc: IntraBarFeatureCalculator):
        """When range=0 (first tick), partial_bar_position should be 0.5."""
        partial = _make_partial(
            elapsed=0.001, remaining=299.999,
            current=70000.0, high=70000.0, low=70000.0,
        )
        result = calc.compute(partial)
        assert result[5] == pytest.approx(0.5)

    def test_volume_ratio_partial_zero_at_early(self, calc: IntraBarFeatureCalculator):
        """volume_ratio_partial = 0 when elapsed_pct < 0.001."""
        partial = _make_partial(elapsed=0.0001, remaining=299.9999, volume=0.0)
        result = calc.compute(partial)
        assert result[6] == pytest.approx(0.0)


class TestTickFeaturesAtMid:
    """At t=150s (50%), tick features should reflect the price movement."""

    def test_distance_from_open(self, calc: IntraBarFeatureCalculator):
        partial = _make_partial(current=70200.0, open_price=70000.0)
        result = calc.compute(partial)
        expected = (70200.0 - 70000.0) / 70000.0
        assert result[0] == pytest.approx(expected, rel=1e-6)

    def test_elapsed_pct_050(self, calc: IntraBarFeatureCalculator):
        partial = _make_partial(elapsed=150.0, remaining=150.0)
        result = calc.compute(partial)
        assert result[2] == pytest.approx(0.50)

    def test_partial_range(self, calc: IntraBarFeatureCalculator):
        partial = _make_partial(high=70300.0, low=69900.0, open_price=70000.0)
        result = calc.compute(partial)
        expected = (70300.0 - 69900.0) / 70000.0
        assert result[4] == pytest.approx(expected, rel=1e-6)

    def test_trade_intensity(self, calc: IntraBarFeatureCalculator):
        partial = _make_partial(elapsed=150.0, trade_count=300)
        result = calc.compute(partial)
        assert result[7] == pytest.approx(2.0)  # 300 / 150


class TestHistoricalFeatures:
    def test_defaults_when_cache_empty(self, calc: IntraBarFeatureCalculator):
        """Without cache, historical features should use sensible defaults."""
        partial = _make_partial()
        result = calc.compute(partial)
        # rsi_14 default = 50.0 (feature index 8)
        assert result[8] == pytest.approx(50.0)
        # hour_cos default = 1.0 (last feature, index 22)
        assert result[22] == pytest.approx(1.0)

    def test_cached_values_used(self, calc: IntraBarFeatureCalculator):
        calc.update_cache(Asset.BTC, {
            "rsi_14": 28.5,
            "rsi_7": 22.0,
            "stoch_k": 15.3,
            "macd_histogram": -0.005,
            "williams_r": -85.0,
            "roc_5": -0.02,
            "realized_vol_10": 0.008,
            "vol_ratio": 1.5,
            "parkinson_vol_10": 0.009,
            "bar_position": 0.2,
            "body_ratio": 0.8,
            "return_5": -0.01,
            "volume_sma_10": 200.0,
            "hour_sin": 0.5,
            "hour_cos": 0.866,
        })
        partial = _make_partial()
        result = calc.compute(partial)
        assert result[8] == pytest.approx(28.5)  # rsi_14
        assert result[9] == pytest.approx(22.0)  # rsi_7
        assert result[10] == pytest.approx(15.3)  # stoch_k
        assert result[22] == pytest.approx(0.866)  # hour_cos

    def test_partial_cache_uses_defaults_for_missing(self, calc: IntraBarFeatureCalculator):
        """If cache has only some features, missing ones use defaults."""
        calc.update_cache(Asset.BTC, {"rsi_14": 30.0})
        partial = _make_partial()
        result = calc.compute(partial)
        assert result[8] == pytest.approx(30.0)  # rsi_14 from cache
        assert result[9] == pytest.approx(50.0)  # rsi_7 from defaults


class TestIsReady:
    def test_not_ready_initially(self, calc: IntraBarFeatureCalculator):
        assert not calc.is_ready(Asset.BTC)

    def test_ready_after_update(self, calc: IntraBarFeatureCalculator):
        calc.update_cache(Asset.BTC, {"rsi_14": 50.0})
        assert calc.is_ready(Asset.BTC)

    def test_per_asset(self, calc: IntraBarFeatureCalculator):
        calc.update_cache(Asset.BTC, {"rsi_14": 50.0})
        assert calc.is_ready(Asset.BTC)
        assert not calc.is_ready(Asset.ETH)


class TestFeatureNamesConsistency:
    def test_cached_feature_names_in_defaults(self):
        for name in CACHED_FEATURE_NAMES:
            assert name in CACHED_DEFAULTS, f"{name} missing from CACHED_DEFAULTS"

    def test_all_features_23(self):
        assert len(ALL_FEATURE_NAMES) == 23
        assert len(set(ALL_FEATURE_NAMES)) == 23  # no duplicates
