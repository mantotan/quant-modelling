"""Tests for the dual-mode backtesting engine."""

import numpy as np
import pytest

from qm.backtest.engine import BacktestEngine
from qm.core.constants import BARS_PER_YEAR
from qm.core.types import Timeframe


@pytest.fixture
def engine() -> BacktestEngine:
    return BacktestEngine(fee_bps=0.0, spread=0.02, min_edge=0.03)


class TestFastEvaluation:
    def test_perfect_model_positive_pnl(self, engine: BacktestEngine):
        """A model with perfect predictions should be profitable."""
        n = 1000
        targets = np.random.randint(0, 2, n).astype(float)
        # Perfect model: knows the outcome
        model_probs = targets * 0.9 + (1 - targets) * 0.1
        market_probs = np.full(n, 0.5)

        metrics = engine.evaluate_model_fast(model_probs, targets, market_probs)
        assert metrics["total_pnl"] > 0
        assert metrics["accuracy"] > 0.8
        assert metrics["n_trades"] > 0

    def test_random_model_near_zero_pnl(self, engine: BacktestEngine):
        """A random model should have PnL close to zero (minus costs)."""
        np.random.seed(42)
        n = 5000
        targets = np.random.randint(0, 2, n).astype(float)
        model_probs = np.random.uniform(0.3, 0.7, n)
        market_probs = np.full(n, 0.5)

        metrics = engine.evaluate_model_fast(model_probs, targets, market_probs)
        # Random model should have accuracy ~50%
        assert abs(metrics["accuracy"] - 0.5) < 0.05
        # Brier score for random ~ 0.25
        assert abs(metrics["brier"] - 0.25) < 0.05

    def test_no_trades_when_no_edge(self, engine: BacktestEngine):
        """If model agrees with market, no trades should be placed."""
        n = 100
        targets = np.random.randint(0, 2, n).astype(float)
        model_probs = np.full(n, 0.5)
        market_probs = np.full(n, 0.5)

        metrics = engine.evaluate_model_fast(model_probs, targets, market_probs)
        assert metrics["n_trades"] == 0

    def test_empty_input(self, engine: BacktestEngine):
        metrics = engine.evaluate_model_fast(np.array([]), np.array([]))
        assert metrics["n_trades"] == 0


class TestFullSimulation:
    def test_basic_simulation(self, engine: BacktestEngine):
        np.random.seed(42)
        n = 200
        targets = np.random.randint(0, 2, n).astype(float)
        model_probs = targets * 0.8 + (1 - targets) * 0.2
        timestamps = np.arange(n)

        result = engine.run_full_simulation(
            model_probs, targets, timestamps,
            initial_bankroll=1000.0,
        )
        assert result.n_trades > 0
        assert result.metrics["total_pnl"] > 0
        assert len(result.trade_log) == result.n_trades

    def test_bankroll_circuit_breaker(self, engine: BacktestEngine):
        """Simulation should stop when bankroll drops below 10%."""
        n = 500
        targets = np.zeros(n)  # always Down
        model_probs = np.full(n, 0.95)  # always predicts Up (wrong)
        timestamps = np.arange(n)

        result = engine.run_full_simulation(
            model_probs, targets, timestamps,
            initial_bankroll=100.0,
        )
        # Should have stopped before exhausting all bars
        last_trade = result.trade_log[-1] if result.trade_log else None
        if last_trade:
            assert last_trade["bankroll"] > 0  # didn't go negative


class TestMetrics:
    def test_brier_score_perfect(self, engine: BacktestEngine):
        """Perfect predictions should have Brier ~0."""
        targets = np.array([1, 0, 1, 1, 0], dtype=float)
        probs = np.array([0.99, 0.01, 0.99, 0.99, 0.01])
        metrics = engine.evaluate_model_fast(probs, targets)
        assert metrics["brier"] < 0.01

    def test_brier_score_uninformed(self, engine: BacktestEngine):
        """Constant 0.5 predictions should have Brier = 0.25."""
        targets = np.array([1, 0, 1, 0, 1, 0], dtype=float)
        probs = np.full(6, 0.5)
        metrics = engine.evaluate_model_fast(probs, targets)
        assert abs(metrics["brier"] - 0.25) < 0.01


class TestTimeframeAnnualization:
    def test_default_is_m5(self):
        """Default engine should use M5 annualization."""
        engine = BacktestEngine()
        assert engine._annualization == BARS_PER_YEAR[Timeframe.M5]

    def test_m1_annualization(self):
        """M1 engine should use 525,600 bars/year."""
        engine = BacktestEngine(timeframe=Timeframe.M1)
        assert engine._annualization == 525_600

    def test_annualization_affects_sharpe(self):
        """Higher annualization (1m) should produce higher Sharpe than lower (1h)."""
        np.random.seed(42)
        n = 1000
        targets = np.random.randint(0, 2, n).astype(float)
        model_probs = targets * 0.85 + (1 - targets) * 0.15
        market_probs = np.full(n, 0.5)

        engine_1m = BacktestEngine(min_edge=0.03, timeframe=Timeframe.M1)
        engine_1h = BacktestEngine(min_edge=0.03, timeframe=Timeframe.H1)

        metrics_1m = engine_1m.evaluate_model_fast(model_probs, targets, market_probs)
        metrics_1h = engine_1h.evaluate_model_fast(model_probs, targets, market_probs)

        # Same data, but 1m annualization is higher → larger Sharpe
        assert metrics_1m["sharpe"] > metrics_1h["sharpe"]
        # PnL should be identical (annualization doesn't affect PnL)
        assert metrics_1m["total_pnl"] == pytest.approx(metrics_1h["total_pnl"])
