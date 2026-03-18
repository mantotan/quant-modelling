"""Tests for IntraBarBacktester with realistic friction."""

import numpy as np
import pytest

from qm.backtest.intrabar_backtest import IntraBarBacktester


@pytest.fixture
def backtester() -> IntraBarBacktester:
    return IntraBarBacktester(
        fee_bps=200, spread=0.02, min_edge=0.02,
        max_trades_per_bar=3, kelly_fraction=0.25,
        impact_bps=50, avg_daily_volume=50_000,
        max_daily_trades=100,
    )


def _make_data(n_bars: int = 100, samples_per_bar: int = 10, seed: int = 42):
    rng = np.random.default_rng(seed)
    n = n_bars * samples_per_bar
    targets = np.repeat(rng.integers(0, 2, n_bars).astype(float), samples_per_bar)
    time_pcts = np.tile(np.linspace(0.003, 0.95, samples_per_bar), n_bars)
    bar_indices = np.repeat(np.arange(n_bars), samples_per_bar)
    market_probs = np.full(n, 0.5)
    return targets, time_pcts, bar_indices, market_probs


class TestFastEvaluation:
    def test_perfect_model_positive_pnl(self, backtester: IntraBarBacktester):
        targets, time_pcts, bar_indices, market_probs = _make_data(200)
        model_probs = targets * 0.85 + (1 - targets) * 0.15
        metrics = backtester.evaluate_fast(
            model_probs, targets, market_probs, time_pcts, bar_indices
        )
        assert metrics["total_pnl"] > 0
        assert metrics["n_trades"] > 0

    def test_random_model_near_zero_pnl(self, backtester: IntraBarBacktester):
        np.random.seed(42)
        targets, time_pcts, bar_indices, market_probs = _make_data(500)
        model_probs = np.random.uniform(0.3, 0.7, len(targets))
        metrics = backtester.evaluate_fast(
            model_probs, targets, market_probs, time_pcts, bar_indices
        )
        assert abs(metrics["accuracy"] - 0.5) < 0.05

    def test_no_trades_when_no_edge(self, backtester: IntraBarBacktester):
        targets, time_pcts, bar_indices, market_probs = _make_data(50)
        model_probs = market_probs.copy()
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
        targets, time_pcts, bar_indices, market_probs = _make_data(200)
        model_probs = targets * 0.85 + (1 - targets) * 0.15
        metrics = backtester.evaluate_fast(
            model_probs, targets, market_probs, time_pcts, bar_indices
        )
        assert "time_buckets" in metrics


class TestFeeOnWinningsOnly:
    def test_no_fee_on_losing_trade(self):
        """Fees should only apply to winning trades (Polymarket model)."""
        bt = IntraBarBacktester(
            fee_bps=200, spread=0.0, min_edge=0.01,
            impact_bps=0, max_trades_per_bar=10, max_daily_trades=10_000,
        )
        # One trade, model says Up (0.90), market at 0.50, target=0 (wrong)
        result = bt.run_full(
            model_probs=np.array([0.90]),
            targets=np.array([0.0]),
            market_probs=np.array([0.50]),
            time_pcts=np.array([0.20]),
            bar_indices=np.array([0]),
            initial_bankroll=10_000.0,
        )
        if result.trade_log:
            trade = result.trade_log[0]
            # Losing trade: PnL = -shares * fill_price, NO fee deducted
            assert trade["pnl"] < 0
            # Verify no fee was charged (loss is exactly -shares * fill_price)
            shares = trade["bet_usd"] / trade["fill_price"]
            expected_loss = -shares * trade["fill_price"]
            assert abs(trade["pnl"] - expected_loss) < 0.01

    def test_fee_on_winning_trade(self):
        """Winning trades should have 2% fee deducted from gross winnings."""
        bt = IntraBarBacktester(
            fee_bps=200, spread=0.0, min_edge=0.01,
            impact_bps=0, max_trades_per_bar=10, max_daily_trades=10_000,
        )
        result = bt.run_full(
            model_probs=np.array([0.90]),
            targets=np.array([1.0]),
            market_probs=np.array([0.50]),
            time_pcts=np.array([0.20]),
            bar_indices=np.array([0]),
            initial_bankroll=10_000.0,
        )
        if result.trade_log:
            trade = result.trade_log[0]
            assert trade["pnl"] > 0
            # Gross win = shares * (1 - fill_price), net = gross - 2% of gross
            shares = trade["bet_usd"] / trade["fill_price"]
            gross = shares * (1 - trade["fill_price"])
            expected_net = gross * (1 - 200 / 10_000)
            assert abs(trade["pnl"] - expected_net) < 0.01


class TestMarketImpact:
    def test_impact_increases_fill_price(self):
        bt_no_impact = IntraBarBacktester(
            fee_bps=0, spread=0.02, min_edge=0.01,
            impact_bps=0, max_trades_per_bar=10, max_daily_trades=10_000,
        )
        bt_with_impact = IntraBarBacktester(
            fee_bps=0, spread=0.02, min_edge=0.01,
            impact_bps=100, avg_daily_volume=10_000,
            max_trades_per_bar=10, max_daily_trades=10_000,
        )
        data = dict(
            model_probs=np.array([0.85]),
            targets=np.array([1.0]),
            market_probs=np.array([0.50]),
            time_pcts=np.array([0.20]),
            bar_indices=np.array([0]),
            initial_bankroll=10_000.0,
        )
        r1 = bt_no_impact.run_full(**data)
        r2 = bt_with_impact.run_full(**data)
        if r1.trade_log and r2.trade_log:
            assert r2.trade_log[0]["fill_price"] > r1.trade_log[0]["fill_price"]
            assert r2.trade_log[0]["impact"] > 0


class TestMaxTradesPerBar:
    def test_limits_trades_per_bar(self):
        bt = IntraBarBacktester(
            fee_bps=0, spread=0.02, min_edge=0.01,
            max_trades_per_bar=2, impact_bps=0, max_daily_trades=10_000,
        )
        n = 10
        targets = np.ones(n)
        model_probs = np.full(n, 0.90)
        market_probs = np.full(n, 0.50)
        time_pcts = np.linspace(0.003, 0.95, n)
        bar_indices = np.zeros(n, dtype=np.int64)

        metrics = bt.evaluate_fast(
            model_probs, targets, market_probs, time_pcts, bar_indices
        )
        assert metrics["n_trades"] == 2


class TestMaxDailyTrades:
    def test_daily_cap(self):
        bt = IntraBarBacktester(
            fee_bps=0, spread=0.02, min_edge=0.01,
            max_trades_per_bar=10, impact_bps=0,
            max_daily_trades=5,
        )
        # 288 bars per day for 5m, create 2 bars with 3 samples each
        # All in the same day (bar_indices 0-5)
        n = 30
        targets = np.ones(n)
        model_probs = np.full(n, 0.85)
        market_probs = np.full(n, 0.50)
        time_pcts = np.tile(np.linspace(0.003, 0.95, 3), 10)
        bar_indices = np.repeat(np.arange(10), 3)

        metrics = bt.evaluate_fast(
            model_probs, targets, market_probs, time_pcts, bar_indices
        )
        assert metrics["n_trades"] <= 5


class TestFullSimulation:
    def test_basic_simulation(self, backtester: IntraBarBacktester):
        targets, time_pcts, bar_indices, market_probs = _make_data(100)
        model_probs = targets * 0.80 + (1 - targets) * 0.20
        result = backtester.run_full(
            model_probs, targets, market_probs, time_pcts, bar_indices,
            initial_bankroll=1000.0,
        )
        assert result.n_trades > 0
        assert len(result.trade_log) == result.n_trades

    def test_trade_log_has_impact(self, backtester: IntraBarBacktester):
        targets, time_pcts, bar_indices, market_probs = _make_data(50)
        model_probs = targets * 0.85 + (1 - targets) * 0.15
        result = backtester.run_full(
            model_probs, targets, market_probs, time_pcts, bar_indices,
        )
        if result.trade_log:
            assert "impact" in result.trade_log[0]
            assert result.trade_log[0]["impact"] >= 0


class TestFixedBetMode:
    def test_fixed_bet_uses_exact_amount(self):
        bt = IntraBarBacktester(
            fee_bps=0, spread=0.0, min_edge=0.01,
            impact_bps=0, max_trades_per_bar=10,
            max_daily_trades=10_000,
            fixed_bet_usd=50.0,
        )
        result = bt.run_full(
            model_probs=np.array([0.85, 0.85, 0.85]),
            targets=np.array([1.0, 1.0, 1.0]),
            market_probs=np.array([0.50, 0.50, 0.50]),
            time_pcts=np.array([0.20, 0.40, 0.60]),
            bar_indices=np.array([0, 1, 2]),
            initial_bankroll=10_000.0,
        )
        for trade in result.trade_log:
            assert trade["bet_usd"] == pytest.approx(50.0)

    def test_fixed_bet_no_compounding(self):
        """PnL should grow linearly, not exponentially, with fixed bets."""
        bt = IntraBarBacktester(
            fee_bps=0, spread=0.0, min_edge=0.01,
            impact_bps=0, max_trades_per_bar=10,
            max_daily_trades=10_000,
            fixed_bet_usd=50.0,
        )
        # 10 identical winning trades
        n = 10
        result = bt.run_full(
            model_probs=np.full(n, 0.85),
            targets=np.ones(n),
            market_probs=np.full(n, 0.50),
            time_pcts=np.linspace(0.10, 0.80, n),
            bar_indices=np.arange(n),
            initial_bankroll=10_000.0,
        )
        if len(result.trade_log) >= 2:
            pnls = [t["pnl"] for t in result.trade_log]
            # All trades should have roughly equal PnL (linear, not exponential)
            assert max(pnls) / (min(pnls) + 1e-10) < 1.5
