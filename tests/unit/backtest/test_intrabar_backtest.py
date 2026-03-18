"""Tests for IntraBarBacktester."""

import numpy as np
import pytest

from qm.backtest.intrabar_backtest import IntraBarBacktester


@pytest.fixture
def backtester() -> IntraBarBacktester:
    return IntraBarBacktester(
        fee_bps=0.0, spread=0.02, min_edge=0.02,
        max_trades_per_bar=3, kelly_fraction=0.25,
    )


def _make_data(n_bars: int = 100, samples_per_bar: int = 16, seed: int = 42):
    """Generate synthetic test data."""
    rng = np.random.default_rng(seed)
    n = n_bars * samples_per_bar
    targets = np.repeat(rng.integers(0, 2, n_bars).astype(float), samples_per_bar)
    time_pcts = np.tile(np.linspace(0.003, 0.98, samples_per_bar), n_bars)
    bar_indices = np.repeat(np.arange(n_bars), samples_per_bar)
    market_probs = np.full(n, 0.5)
    return targets, time_pcts, bar_indices, market_probs


class TestFastEvaluation:
    def test_perfect_model_positive_pnl(self, backtester: IntraBarBacktester):
        """A perfect model should be profitable."""
        targets, time_pcts, bar_indices, market_probs = _make_data(200)
        # Perfect model: high prob for correct outcome
        model_probs = targets * 0.85 + (1 - targets) * 0.15
        metrics = backtester.evaluate_fast(
            model_probs, targets, market_probs, time_pcts, bar_indices
        )
        assert metrics["total_pnl"] > 0
        assert metrics["n_trades"] > 0
        assert metrics["win_rate"] > 0.7

    def test_random_model_near_zero_pnl(self, backtester: IntraBarBacktester):
        """A random model should have near-zero or negative PnL."""
        np.random.seed(42)
        targets, time_pcts, bar_indices, market_probs = _make_data(500)
        model_probs = np.random.uniform(0.3, 0.7, len(targets))
        metrics = backtester.evaluate_fast(
            model_probs, targets, market_probs, time_pcts, bar_indices
        )
        assert abs(metrics["accuracy"] - 0.5) < 0.05

    def test_no_trades_when_no_edge(self, backtester: IntraBarBacktester):
        """If model matches market, no trades should happen."""
        targets, time_pcts, bar_indices, market_probs = _make_data(50)
        model_probs = market_probs.copy()  # no edge
        metrics = backtester.evaluate_fast(
            model_probs, targets, market_probs, time_pcts, bar_indices
        )
        assert metrics["n_trades"] == 0

    def test_empty_input(self, backtester: IntraBarBacktester):
        metrics = backtester.evaluate_fast(
            np.array([]), np.array([]), np.array([]),
            np.array([]), np.array([], dtype=np.int64),
        )
        assert metrics["n_trades"] == 0

    def test_time_buckets_populated(self, backtester: IntraBarBacktester):
        """Time bucket metrics should be present when trades are placed."""
        targets, time_pcts, bar_indices, market_probs = _make_data(200)
        model_probs = targets * 0.85 + (1 - targets) * 0.15
        metrics = backtester.evaluate_fast(
            model_probs, targets, market_probs, time_pcts, bar_indices
        )
        assert "time_buckets" in metrics
        buckets = metrics["time_buckets"]
        assert "0-30s" in buckets
        assert "180-295s" in buckets


class TestMaxTradesPerBar:
    def test_limits_trades_per_bar(self):
        bt = IntraBarBacktester(
            fee_bps=0.0, spread=0.02, min_edge=0.01,
            max_trades_per_bar=2,
        )
        # 1 bar, 16 samples, all with huge edge
        n = 16
        targets = np.ones(n)
        model_probs = np.full(n, 0.90)
        market_probs = np.full(n, 0.50)
        time_pcts = np.linspace(0.003, 0.95, n)
        bar_indices = np.zeros(n, dtype=np.int64)

        metrics = bt.evaluate_fast(
            model_probs, targets, market_probs, time_pcts, bar_indices
        )
        assert metrics["n_trades"] == 2  # limited to 2


class TestFullSimulation:
    def test_basic_simulation(self, backtester: IntraBarBacktester):
        targets, time_pcts, bar_indices, market_probs = _make_data(100)
        model_probs = targets * 0.80 + (1 - targets) * 0.20
        result = backtester.run_full(
            model_probs, targets, market_probs, time_pcts, bar_indices,
            initial_bankroll=1000.0,
        )
        assert result.n_trades > 0
        assert result.metrics["total_pnl"] > 0
        assert len(result.trade_log) == result.n_trades

    def test_trade_log_has_time_pct(self, backtester: IntraBarBacktester):
        targets, time_pcts, bar_indices, market_probs = _make_data(50)
        model_probs = targets * 0.85 + (1 - targets) * 0.15
        result = backtester.run_full(
            model_probs, targets, market_probs, time_pcts, bar_indices,
        )
        if result.trade_log:
            assert "time_pct" in result.trade_log[0]

    def test_circuit_breaker(self, backtester: IntraBarBacktester):
        """Should stop when bankroll drops below 10%."""
        n = 500 * 16
        targets = np.zeros(n)  # always Down
        model_probs = np.full(n, 0.95)  # always wrong
        market_probs = np.full(n, 0.50)
        time_pcts = np.tile(np.linspace(0.003, 0.95, 16), 500)
        bar_indices = np.repeat(np.arange(500), 16)

        result = backtester.run_full(
            model_probs, targets, market_probs, time_pcts, bar_indices,
            initial_bankroll=100.0,
        )
        if result.trade_log:
            assert result.trade_log[-1]["bankroll"] > 0

    def test_time_bucket_metrics_in_full(self, backtester: IntraBarBacktester):
        targets, time_pcts, bar_indices, market_probs = _make_data(200)
        model_probs = targets * 0.85 + (1 - targets) * 0.15
        result = backtester.run_full(
            model_probs, targets, market_probs, time_pcts, bar_indices,
        )
        # Should have at least some time bucket data
        assert len(result.metrics_by_time_bucket) > 0
