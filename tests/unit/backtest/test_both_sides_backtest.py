"""Tests for the both-sides limit order backtester."""
import numpy as np
import pytest

from qm.backtest.both_sides_backtest import BothSidesBacktester
from qm.core.types import Timeframe


@pytest.fixture
def bt():
    return BothSidesBacktester(margin=0.03, fixed_bet_usd=100, max_trades_per_bar=26)


def _make_data(n_bars: int, samples_per_bar: int, model_probs, market_probs, targets):
    """Helper to build aligned arrays for backtester."""
    n = n_bars * samples_per_bar
    mp = np.full(n, model_probs) if isinstance(model_probs, (int, float)) else np.tile(model_probs, n_bars)[:n]
    mkt = np.full(n, market_probs) if isinstance(market_probs, (int, float)) else np.tile(market_probs, n_bars)[:n]
    tgt = np.full(n, targets) if isinstance(targets, (int, float)) else np.repeat(targets, samples_per_bar)[:n]
    tp = np.tile(np.linspace(0.1, 0.9, samples_per_bar), n_bars)[:n]
    bi = np.repeat(np.arange(n_bars), samples_per_bar)[:n]
    return mp, tgt, mkt, tp, bi


class TestBothSidesBacktester:
    def test_empty_input(self, bt):
        r = bt.evaluate_fast(
            np.array([]), np.array([]), np.array([]),
            np.array([]), np.array([]),
        )
        assert r["n_trades"] == 0
        assert r["total_pnl"] == 0.0

    def test_perfect_model_up_bars(self, bt):
        """Model correctly predicts Up → buys Up cheap, wins."""
        # Model says 0.70 Up, market offers at 0.40 (cheap for Up)
        # Up limit = 0.70 - 0.03 = 0.67, market 0.40 <= 0.67 → fills
        mp, tgt, mkt, tp, bi = _make_data(
            n_bars=10, samples_per_bar=5,
            model_probs=0.70, market_probs=0.40, targets=1,
        )
        r = bt.evaluate_fast(mp, tgt, mkt, tp, bi)
        assert r["n_trades"] > 0
        assert r["total_pnl"] > 0, "Perfect model should profit"

    def test_perfect_model_down_bars(self, bt):
        """Model correctly predicts Down → buys Down cheap, wins."""
        # Model says 0.30 Up (i.e., 0.70 Down), market at 0.60
        # Down limit = (1-0.30) - 0.03 = 0.67, down_market = 1-0.60=0.40 <= 0.67 → fills
        mp, tgt, mkt, tp, bi = _make_data(
            n_bars=10, samples_per_bar=5,
            model_probs=0.30, market_probs=0.60, targets=0,
        )
        r = bt.evaluate_fast(mp, tgt, mkt, tp, bi)
        assert r["n_trades"] > 0
        assert r["total_pnl"] > 0, "Perfect model should profit on Down bars"

    def test_random_model_lower_sharpe(self):
        """Random model should have much lower Sharpe than perfect model."""
        rng = np.random.default_rng(42)
        n_bars, samp = 100, 5
        n = n_bars * samp

        # Random model
        bt = BothSidesBacktester(margin=0.03, fixed_bet_usd=100, max_trades_per_bar=26)
        mp_rand = rng.uniform(0.3, 0.7, n)
        tgt = rng.integers(0, 2, n_bars)
        tgt_expanded = np.repeat(tgt, samp)
        mkt = rng.uniform(0.3, 0.7, n)
        tp = np.tile(np.linspace(0.1, 0.9, samp), n_bars)
        bi = np.repeat(np.arange(n_bars), samp)
        r_rand = bt.evaluate_fast(mp_rand, tgt_expanded, mkt, tp, bi)

        # Perfect model: model_prob = 0.8 when target=1, 0.2 when target=0
        mp_perf = np.where(tgt_expanded == 1, 0.80, 0.20)
        r_perf = bt.evaluate_fast(mp_perf, tgt_expanded, mkt, tp, bi)

        assert r_perf["sharpe"] > r_rand["sharpe"], (
            f"Perfect sharpe {r_perf['sharpe']:.1f} should beat random {r_rand['sharpe']:.1f}"
        )

    def test_max_trades_per_bar_enforced(self):
        """Per-bar trade limit prevents excessive fills."""
        bt = BothSidesBacktester(margin=0.01, max_trades_per_bar=2)
        # 20 samples per bar, all should fill but limit is 2
        mp, tgt, mkt, tp, bi = _make_data(
            n_bars=1, samples_per_bar=20,
            model_probs=0.70, market_probs=0.30, targets=1,
        )
        r = bt.evaluate_fast(mp, tgt, mkt, tp, bi)
        assert r["n_trades"] == 2

    def test_no_fill_when_market_above_limit(self, bt):
        """No fills when market price exceeds limit price."""
        # Model says 0.50, margin=0.03 → Up limit=0.47
        # Market at 0.60 → Up costs 0.60 > 0.47 → no Up fill
        # Down limit = 0.50-0.03=0.47, Down costs 0.40 <= 0.47 → Down fills
        mp, tgt, mkt, tp, bi = _make_data(
            n_bars=5, samples_per_bar=3,
            model_probs=0.50, market_probs=0.60, targets=0,
        )
        r = bt.evaluate_fast(mp, tgt, mkt, tp, bi)
        # Down should fill (0.40 <= 0.47), Up should not (0.60 > 0.47)
        assert r["n_trades"] > 0

    def test_safety_check_combined_cost(self):
        """Both sides cannot fill when combined cost >= 1.0."""
        bt = BothSidesBacktester(margin=0.01)
        # Model at 0.50, market at 0.50
        # Up limit = 0.49, Down limit = 0.49
        # Up price=0.50, Down price=0.50 → combined = 1.0 → should NOT fill
        mp, tgt, mkt, tp, bi = _make_data(
            n_bars=5, samples_per_bar=3,
            model_probs=0.50, market_probs=0.50, targets=1,
        )
        r = bt.evaluate_fast(mp, tgt, mkt, tp, bi)
        # Market at 0.50: Up=0.50 > limit 0.49, Down=0.50 > limit 0.49
        # Neither fills individually. No trades.
        assert r["n_trades"] == 0

    def test_large_margin_never_fills(self):
        """Very large margin means limit prices are too aggressive → no fills."""
        bt = BothSidesBacktester(margin=0.49)
        mp, tgt, mkt, tp, bi = _make_data(
            n_bars=10, samples_per_bar=5,
            model_probs=0.50, market_probs=0.50, targets=1,
        )
        r = bt.evaluate_fast(mp, tgt, mkt, tp, bi)
        assert r["n_trades"] == 0

    def test_zero_margin_aggressive(self):
        """Zero margin = buy at exactly model's estimate."""
        bt = BothSidesBacktester(margin=0.0, max_trades_per_bar=50)
        # Model 0.60, market 0.40. Up limit=0.60, market 0.40<=0.60 → fills
        mp, tgt, mkt, tp, bi = _make_data(
            n_bars=5, samples_per_bar=5,
            model_probs=0.60, market_probs=0.40, targets=1,
        )
        r = bt.evaluate_fast(mp, tgt, mkt, tp, bi)
        assert r["n_trades"] > 0

    def test_settlement_correct_target_1(self, bt):
        """Target=1: Up shares pay $1, Down shares pay $0."""
        # Force only Up fills: model 0.80, market 0.30 → Up fills
        mp, tgt, mkt, tp, bi = _make_data(
            n_bars=1, samples_per_bar=1,
            model_probs=0.80, market_probs=0.30, targets=1,
        )
        r = bt.evaluate_fast(mp, tgt, mkt, tp, bi)
        # Up bought at 0.30, pays $1 on target=1 → profit
        assert r["total_pnl"] > 0

    def test_settlement_correct_target_0(self, bt):
        """Target=0: Down shares pay $1, Up shares pay $0."""
        mp, tgt, mkt, tp, bi = _make_data(
            n_bars=1, samples_per_bar=1,
            model_probs=0.20, market_probs=0.70, targets=0,
        )
        r = bt.evaluate_fast(mp, tgt, mkt, tp, bi)
        # Down limit = 0.80-0.03=0.77, down_market=0.30 <= 0.77 → fills
        # Down bought at 0.30, pays $1 on target=0 → profit
        assert r["total_pnl"] > 0

    def test_metrics_dict_keys(self, bt):
        """Return dict has all required keys."""
        mp, tgt, mkt, tp, bi = _make_data(
            n_bars=5, samples_per_bar=3,
            model_probs=0.60, market_probs=0.40, targets=1,
        )
        r = bt.evaluate_fast(mp, tgt, mkt, tp, bi)
        required = {"sharpe", "brier", "accuracy", "total_pnl", "max_dd",
                     "n_trades", "win_rate", "avg_pnl_per_trade", "time_buckets"}
        assert required.issubset(r.keys()), f"Missing keys: {required - r.keys()}"

    def test_fee_on_winnings(self):
        """Fee reduces profit but doesn't create false losses."""
        bt_no_fee = BothSidesBacktester(margin=0.03, fee_bps=0)
        bt_fee = BothSidesBacktester(margin=0.03, fee_bps=200)  # 2% fee
        mp, tgt, mkt, tp, bi = _make_data(
            n_bars=10, samples_per_bar=5,
            model_probs=0.70, market_probs=0.40, targets=1,
        )
        r_no = bt_no_fee.evaluate_fast(mp, tgt, mkt, tp, bi)
        r_fee = bt_fee.evaluate_fast(mp, tgt, mkt, tp, bi)
        assert r_fee["total_pnl"] < r_no["total_pnl"], "Fee should reduce PnL"
        assert r_fee["total_pnl"] > 0, "Fee should not eliminate all profit"

    def test_empty_metrics_values(self, bt):
        """Empty metrics have sane defaults."""
        r = bt._empty_metrics()
        assert r["n_trades"] == 0
        assert r["total_pnl"] == 0.0
        assert r["sharpe"] == 0.0
