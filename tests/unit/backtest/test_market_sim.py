"""Tests for MarketOddsSimulator (Black-Scholes binary pricing)."""

import numpy as np
import pytest

from qm.backtest.market_sim import MarketOddsSimulator
from qm.core.types import Timeframe


@pytest.fixture
def sim() -> MarketOddsSimulator:
    return MarketOddsSimulator(efficiency=0.3, timeframe=Timeframe.M5)


class TestMarketOddsSimulator:
    def test_at_t0_returns_050(self, sim: MarketOddsSimulator):
        """At t=0, distance=0, z=0, Phi(0)=0.5 -> output = 0.50."""
        prob = sim.market_prob(
            open_price=70000.0, current_price=70000.0,
            realized_vol=0.005, elapsed_seconds=0.0,
        )
        assert prob == pytest.approx(0.50, abs=0.001)

    def test_price_above_open_gives_gt_050(self, sim: MarketOddsSimulator):
        """Price above open -> market_prob > 0.5."""
        prob = sim.market_prob(
            open_price=70000.0, current_price=70500.0,
            realized_vol=0.005, elapsed_seconds=150.0,
        )
        assert prob > 0.50

    def test_price_below_open_gives_lt_050(self, sim: MarketOddsSimulator):
        """Price below open -> market_prob < 0.5."""
        prob = sim.market_prob(
            open_price=70000.0, current_price=69500.0,
            realized_vol=0.005, elapsed_seconds=150.0,
        )
        assert prob < 0.50

    def test_convergence_near_bar_end(self, sim: MarketOddsSimulator):
        """With price above open and little time remaining, prob > 0.50.
        At efficiency=0.3, output is blended 70% toward 0.50."""
        prob = sim.market_prob(
            open_price=70000.0, current_price=70500.0,
            realized_vol=0.005, elapsed_seconds=299.0,
        )
        assert prob > 0.60  # efficiency=0.3 dampens convergence

    def test_convergence_below_open_near_end(self, sim: MarketOddsSimulator):
        """Price below open near end -> prob < 0.50."""
        prob = sim.market_prob(
            open_price=70000.0, current_price=69500.0,
            realized_vol=0.005, elapsed_seconds=299.0,
        )
        assert prob < 0.40  # efficiency=0.3 dampens convergence

    def test_full_efficiency_convergence_near_end(self):
        """At efficiency=1.0, convergence is strong near bar end."""
        sim = MarketOddsSimulator(efficiency=1.0)
        prob_up = sim.market_prob(70000.0, 70500.0, 0.005, 299.0)
        prob_down = sim.market_prob(70000.0, 69500.0, 0.005, 299.0)
        assert prob_up > 0.90
        assert prob_down < 0.10

    def test_output_clamped_to_range(self, sim: MarketOddsSimulator):
        """Output should always be in [0.02, 0.98]."""
        # Extreme case: huge move with tiny time remaining
        prob = sim.market_prob(
            open_price=70000.0, current_price=75000.0,
            realized_vol=0.001, elapsed_seconds=299.9,
        )
        assert 0.02 <= prob <= 0.98

    def test_efficiency_zero_always_050(self):
        """With efficiency=0, market always returns 0.50."""
        sim = MarketOddsSimulator(efficiency=0.0)
        prob = sim.market_prob(
            open_price=70000.0, current_price=75000.0,
            realized_vol=0.005, elapsed_seconds=200.0,
        )
        assert prob == pytest.approx(0.50, abs=0.001)

    def test_efficiency_one_tracks_theory(self):
        """With efficiency=1.0, market fully tracks theoretical fair value."""
        sim = MarketOddsSimulator(efficiency=1.0)
        # Large move above open -> should be well above 0.5
        prob = sim.market_prob(
            open_price=70000.0, current_price=70500.0,
            realized_vol=0.005, elapsed_seconds=200.0,
        )
        assert prob > 0.70

    def test_high_vol_more_uncertain(self, sim: MarketOddsSimulator):
        """Higher volatility -> wider sigma -> market stays closer to 0.5."""
        prob_low_vol = sim.market_prob(
            open_price=70000.0, current_price=70200.0,
            realized_vol=0.002, elapsed_seconds=150.0,
        )
        prob_high_vol = sim.market_prob(
            open_price=70000.0, current_price=70200.0,
            realized_vol=0.02, elapsed_seconds=150.0,
        )
        # High vol -> closer to 0.5
        assert abs(prob_high_vol - 0.5) < abs(prob_low_vol - 0.5)

    def test_monotonicity_with_time(self, sim: MarketOddsSimulator):
        """As time increases (price above open), prob should increase."""
        probs = [
            sim.market_prob(
                open_price=70000.0, current_price=70200.0,
                realized_vol=0.005, elapsed_seconds=t,
            )
            for t in [30, 60, 120, 180, 240, 290]
        ]
        for i in range(1, len(probs)):
            assert probs[i] >= probs[i - 1] - 1e-6

    def test_invalid_efficiency_raises(self):
        with pytest.raises(ValueError, match="efficiency"):
            MarketOddsSimulator(efficiency=1.5)
        with pytest.raises(ValueError, match="efficiency"):
            MarketOddsSimulator(efficiency=-0.1)

    def test_timeframe_aware(self):
        """M1 timeframe uses 60 seconds, M5 uses 300."""
        sim_1m = MarketOddsSimulator(efficiency=0.3, timeframe=Timeframe.M1)
        sim_5m = MarketOddsSimulator(efficiency=0.3, timeframe=Timeframe.M5)
        assert sim_1m.total_seconds == 60.0
        assert sim_5m.total_seconds == 300.0

        # Same elapsed_seconds=30 means 50% for M1, 10% for M5
        # M1 should be MORE converged (more time elapsed as fraction)
        prob_1m = sim_1m.market_prob(70000.0, 70100.0, 0.005, 30.0)
        prob_5m = sim_5m.market_prob(70000.0, 70100.0, 0.005, 30.0)
        assert prob_1m > prob_5m  # M1 has less time remaining -> more converged


class TestBatchMethod:
    def test_batch_matches_scalar(self, sim: MarketOddsSimulator):
        """Batch method should produce same results as scalar."""
        opens = np.array([70000.0, 70000.0, 70000.0])
        currents = np.array([70200.0, 69800.0, 70000.0])
        vols = np.array([0.005, 0.005, 0.005])
        elapsed = np.array([60.0, 150.0, 0.0])

        batch_result = sim.market_prob_batch(opens, currents, vols, elapsed)
        scalar_results = np.array([
            sim.market_prob(opens[i], currents[i], vols[i], elapsed[i])
            for i in range(3)
        ])

        np.testing.assert_allclose(batch_result, scalar_results, atol=1e-6)

    def test_batch_empty(self, sim: MarketOddsSimulator):
        result = sim.market_prob_batch(
            np.array([]), np.array([]), np.array([]), np.array([])
        )
        assert len(result) == 0

    def test_batch_output_clamped(self, sim: MarketOddsSimulator):
        """All batch outputs in [0.02, 0.98]."""
        opens = np.full(100, 70000.0)
        currents = np.linspace(65000.0, 75000.0, 100)
        vols = np.full(100, 0.005)
        elapsed = np.full(100, 299.0)

        result = sim.market_prob_batch(opens, currents, vols, elapsed)
        assert np.all(result >= 0.02)
        assert np.all(result <= 0.98)
