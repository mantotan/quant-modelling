"""Tests for IntraBarTrainingDataGenerator."""

import numpy as np
import polars as pl
import pytest

from qm.backtest.market_sim import MarketOddsSimulator
from qm.core.types import Timeframe
from qm.features.intrabar import ALL_FEATURE_NAMES
from qm.model.targets.intrabar import (
    DEFAULT_TIME_PCTS,
    IntraBarTrainingDataGenerator,
    _simulate_ohlc_path,
)


def _make_bars(n: int = 100, seed: int = 42) -> tuple[pl.DataFrame, pl.DataFrame]:
    """Create synthetic bars and history features."""
    rng = np.random.default_rng(seed)
    opens = 70000 + rng.normal(0, 100, n)
    closes = opens + rng.normal(0, 50, n)
    highs = np.maximum(opens, closes) + rng.uniform(10, 100, n)
    lows = np.minimum(opens, closes) - rng.uniform(10, 100, n)
    volumes = rng.uniform(50, 500, n)

    bars_df = pl.DataFrame({
        "open": opens, "high": highs, "low": lows, "close": closes,
        "volume": volumes, "trade_count": rng.integers(100, 1000, n),
    })

    # Simulate history features
    history = pl.DataFrame({
        "rsi_14": rng.uniform(20, 80, n),
        "rsi_7": rng.uniform(15, 85, n),
        "stoch_k": rng.uniform(10, 90, n),
        "macd_histogram": rng.normal(0, 0.005, n),
        "williams_r": rng.uniform(-95, -5, n),
        "roc_5": rng.normal(0, 0.02, n),
        "realized_vol_10": rng.uniform(0.003, 0.015, n),
        "vol_ratio": rng.uniform(0.5, 2.0, n),
        "parkinson_vol_10": rng.uniform(0.003, 0.015, n),
        "bar_position": rng.uniform(0, 1, n),
        "body_ratio": rng.uniform(0, 1, n),
        "return_5": rng.normal(0, 0.01, n),
        "volume_sma_10": rng.uniform(100, 500, n),
        "hour_sin": rng.uniform(-1, 1, n),
        "hour_cos": rng.uniform(-1, 1, n),
    })
    return bars_df, history


class TestOHLCPathSimulation:
    def test_up_bar_starts_at_open(self):
        price, h, l = _simulate_ohlc_path(100.0, 105.0, 95.0, 103.0, 0.0)
        assert price == pytest.approx(100.0)

    def test_up_bar_ends_at_close(self):
        price, h, l = _simulate_ohlc_path(100.0, 105.0, 95.0, 103.0, 1.0)
        assert price == pytest.approx(103.0)

    def test_down_bar_starts_at_open(self):
        price, h, l = _simulate_ohlc_path(100.0, 105.0, 95.0, 97.0, 0.0)
        assert price == pytest.approx(100.0)

    def test_down_bar_ends_at_close(self):
        price, h, l = _simulate_ohlc_path(100.0, 105.0, 95.0, 97.0, 1.0)
        assert price == pytest.approx(97.0)

    def test_up_bar_hits_low_before_high(self):
        """At 25% through an up-bar, price should be near low."""
        price, h, l = _simulate_ohlc_path(100.0, 110.0, 90.0, 105.0, 0.25)
        assert price == pytest.approx(90.0)

    def test_up_bar_hits_high_at_75pct(self):
        """At 75% through an up-bar, price should be near high."""
        price, h, l = _simulate_ohlc_path(100.0, 110.0, 90.0, 105.0, 0.75)
        assert price == pytest.approx(110.0)

    def test_high_so_far_monotonically_increases(self):
        """high_so_far should never decrease as time progresses."""
        highs = []
        for t in np.linspace(0, 1, 50):
            _, h, _ = _simulate_ohlc_path(100.0, 110.0, 90.0, 105.0, t)
            highs.append(h)
        for i in range(1, len(highs)):
            assert highs[i] >= highs[i - 1] - 1e-10

    def test_noise_changes_price(self):
        rng = np.random.default_rng(42)
        p1, _, _ = _simulate_ohlc_path(100.0, 110.0, 90.0, 105.0, 0.5, rng, 0.5, 0.01)
        rng2 = np.random.default_rng(99)
        p2, _, _ = _simulate_ohlc_path(100.0, 110.0, 90.0, 105.0, 0.5, rng2, 0.5, 0.01)
        assert p1 != p2  # noise makes them different


class TestDatasetGeneration:
    def test_output_shape(self):
        bars_df, hist = _make_bars(50)
        sim = MarketOddsSimulator(efficiency=0.3)
        gen = IntraBarTrainingDataGenerator()
        ds = gen.generate(bars_df, hist, sim)

        expected_samples = 50 * len(DEFAULT_TIME_PCTS)
        assert ds.X.shape == (expected_samples, 23)
        assert ds.y.shape == (expected_samples,)
        assert ds.market_probs.shape == (expected_samples,)
        assert ds.bar_indices.shape == (expected_samples,)
        assert ds.time_pcts.shape == (expected_samples,)

    def test_16_samples_per_bar(self):
        bars_df, hist = _make_bars(10)
        sim = MarketOddsSimulator(efficiency=0.3)
        gen = IntraBarTrainingDataGenerator()
        ds = gen.generate(bars_df, hist, sim)
        assert len(ds.y) == 10 * 16

    def test_bar_indices_correct(self):
        bars_df, hist = _make_bars(20)
        sim = MarketOddsSimulator(efficiency=0.3)
        gen = IntraBarTrainingDataGenerator()
        ds = gen.generate(bars_df, hist, sim)

        # Each bar should have exactly 16 samples
        unique, counts = np.unique(ds.bar_indices, return_counts=True)
        assert len(unique) == 20
        assert np.all(counts == 16)

    def test_targets_binary(self):
        bars_df, hist = _make_bars(50)
        sim = MarketOddsSimulator(efficiency=0.3)
        gen = IntraBarTrainingDataGenerator()
        ds = gen.generate(bars_df, hist, sim)
        assert set(np.unique(ds.y)).issubset({0.0, 1.0})

    def test_targets_shared_within_bar(self):
        """All samples from the same bar should have the same target."""
        bars_df, hist = _make_bars(30)
        sim = MarketOddsSimulator(efficiency=0.3)
        gen = IntraBarTrainingDataGenerator()
        ds = gen.generate(bars_df, hist, sim)

        for bar_i in range(30):
            mask = ds.bar_indices == bar_i
            targets = ds.y[mask]
            assert len(set(targets)) == 1  # all same target

    def test_market_probs_valid_range(self):
        bars_df, hist = _make_bars(50)
        sim = MarketOddsSimulator(efficiency=0.3)
        gen = IntraBarTrainingDataGenerator()
        ds = gen.generate(bars_df, hist, sim)
        assert np.all(ds.market_probs >= 0.02)
        assert np.all(ds.market_probs <= 0.98)

    def test_time_pcts_match_default(self):
        bars_df, hist = _make_bars(5)
        sim = MarketOddsSimulator(efficiency=0.3)
        gen = IntraBarTrainingDataGenerator()
        ds = gen.generate(bars_df, hist, sim)

        # Each bar should have the same time_pcts
        for bar_i in range(5):
            mask = ds.bar_indices == bar_i
            np.testing.assert_allclose(
                ds.time_pcts[mask], DEFAULT_TIME_PCTS, atol=1e-10
            )

    def test_feature_names(self):
        bars_df, hist = _make_bars(5)
        sim = MarketOddsSimulator(efficiency=0.3)
        gen = IntraBarTrainingDataGenerator()
        ds = gen.generate(bars_df, hist, sim)
        assert ds.feature_names == ALL_FEATURE_NAMES

    def test_empty_bars(self):
        bars_df = pl.DataFrame({
            "open": [], "high": [], "low": [], "close": [],
            "volume": [], "trade_count": [],
        }).cast({"trade_count": pl.Int64})
        hist = pl.DataFrame({name: [] for name in [
            "rsi_14", "rsi_7", "stoch_k", "macd_histogram", "williams_r",
            "roc_5", "realized_vol_10", "vol_ratio", "parkinson_vol_10",
            "bar_position", "body_ratio", "return_5", "volume_sma_10",
            "hour_sin", "hour_cos",
        ]})
        sim = MarketOddsSimulator(efficiency=0.3)
        gen = IntraBarTrainingDataGenerator()
        ds = gen.generate(bars_df, hist, sim)
        assert ds.X.shape == (0, 23)

    def test_no_nan_in_features(self):
        bars_df, hist = _make_bars(50)
        sim = MarketOddsSimulator(efficiency=0.3)
        gen = IntraBarTrainingDataGenerator()
        ds = gen.generate(bars_df, hist, sim)
        assert not np.any(np.isnan(ds.X))

    def test_chunked_same_as_single(self):
        """Chunked processing should produce identical results to single-pass."""
        bars_df, hist = _make_bars(100)
        sim = MarketOddsSimulator(efficiency=0.3)

        gen1 = IntraBarTrainingDataGenerator(seed=42)
        ds1 = gen1.generate(bars_df, hist, sim, chunk_size=100_000)  # single pass

        gen2 = IntraBarTrainingDataGenerator(seed=42)
        ds2 = gen2.generate(bars_df, hist, sim, chunk_size=30)  # chunked

        np.testing.assert_allclose(ds1.X, ds2.X, atol=1e-10)
        np.testing.assert_array_equal(ds1.y, ds2.y)
        np.testing.assert_array_equal(ds1.bar_indices, ds2.bar_indices)
