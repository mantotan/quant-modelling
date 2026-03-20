"""Tests for unified bet sizing between paper executor and replay backtest.

Verifies that replay_paper_pnl() produces PnL in real USD that matches
the Portfolio shares-based accounting model used by paper trading.
"""

from __future__ import annotations

# Import the replay function directly from the script module
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent / "scripts"))

from replay_backtest import replay_paper_pnl


def _make_replay_arrays(
    n: int = 5,
    size_usd: float = 25.0,
    fill_price: float = 0.50,
    model_prob: float = 0.85,
    market_prob: float = 0.50,
    spread: float = 0.02,
    target: float = 1.0,
) -> dict[str, np.ndarray]:
    """Create replay arrays simulating paper trade data."""
    side = "UP" if model_prob > market_prob else "DOWN"
    return {
        "model_probs": np.full(n, model_prob),
        "market_probs": np.full(n, market_prob),
        "targets": np.full(n, target),
        "time_pcts": np.linspace(0.10, 0.80, n),
        "bar_indices": np.arange(n),
        "paper_pnls": np.zeros(n),  # not used by replay_paper_pnl
        "fill_statuses": ["filled"] * n,
        "fill_prices": np.full(n, fill_price),
        "sizes": np.full(n, size_usd),
        "spreads": np.full(n, spread),
        "signal_sides": [side] * n,
    }


class TestReplayPaperPnlMatchesPortfolio:
    """Verify replay PnL uses the same shares-based model as Portfolio."""

    def test_winning_trade_pnl_matches_portfolio(self):
        """A single winning trade should produce shares * (1 - fill_price)."""
        arrays = _make_replay_arrays(
            n=1, size_usd=25.0, fill_price=0.50,
            model_prob=0.85, market_prob=0.50, target=1.0,
        )
        result = replay_paper_pnl(arrays, fee_bps=0)

        # Portfolio model: shares = 25/0.50 = 50, pnl = 50 * (1-0.50) = 25
        shares = 25.0 / 0.50
        expected_pnl = shares * (1 - 0.50)
        assert result["total_pnl"] == pytest.approx(expected_pnl, abs=0.01)
        assert result["n_trades"] == 1

    def test_losing_trade_pnl_matches_portfolio(self):
        """A single losing trade should produce -size_usd."""
        arrays = _make_replay_arrays(
            n=1, size_usd=25.0, fill_price=0.50,
            model_prob=0.85, market_prob=0.50, target=0.0,
        )
        result = replay_paper_pnl(arrays, fee_bps=0)

        # Portfolio model: loss = -size_usd = -25.0
        assert result["total_pnl"] == pytest.approx(-25.0, abs=0.01)
        assert result["n_trades"] == 1

    def test_fee_on_winnings_only(self):
        """Fees should only apply to winning trades, matching Polymarket model."""
        arrays = _make_replay_arrays(
            n=1, size_usd=25.0, fill_price=0.50,
            model_prob=0.85, market_prob=0.50, target=1.0,
        )
        result_no_fee = replay_paper_pnl(arrays, fee_bps=0)
        result_with_fee = replay_paper_pnl(arrays, fee_bps=200)

        # Fee reduces winning PnL
        assert result_with_fee["total_pnl"] < result_no_fee["total_pnl"]

        # Fee = 2% of gross winnings
        shares = 25.0 / 0.50
        gross = shares * (1 - 0.50)
        expected_net = gross - gross * 0.02
        assert result_with_fee["total_pnl"] == pytest.approx(expected_net, abs=0.01)

    def test_no_fee_on_losing_trade(self):
        """Losing trades should NOT have fees, matching Polymarket model."""
        arrays = _make_replay_arrays(
            n=1, size_usd=25.0, fill_price=0.50,
            model_prob=0.85, market_prob=0.50, target=0.0,
        )
        result_no_fee = replay_paper_pnl(arrays, fee_bps=0)
        result_with_fee = replay_paper_pnl(arrays, fee_bps=200)

        # Loss should be identical regardless of fee setting
        assert result_with_fee["total_pnl"] == pytest.approx(
            result_no_fee["total_pnl"], abs=0.001
        )


class TestReplayPaperPnlRealUSD:
    """Verify replay PnL is in real USD, not fractional units."""

    def test_pnl_scale_matches_bet_size(self):
        """PnL magnitude should be proportional to bet size in USD."""
        arrays_small = _make_replay_arrays(n=1, size_usd=10.0, fill_price=0.50, target=1.0)
        arrays_large = _make_replay_arrays(n=1, size_usd=100.0, fill_price=0.50, target=1.0)

        small = replay_paper_pnl(arrays_small)
        large = replay_paper_pnl(arrays_large)

        # PnL should scale linearly with bet size
        ratio = large["total_pnl"] / small["total_pnl"]
        assert ratio == pytest.approx(10.0, abs=0.01)

    def test_pnl_not_fractional(self):
        """PnL for a $25 bet should be in dollar range, not sub-cent fractions."""
        arrays = _make_replay_arrays(
            n=1, size_usd=25.0, fill_price=0.50,
            model_prob=0.85, market_prob=0.50, target=1.0,
        )
        result = replay_paper_pnl(arrays)

        # For a $25 bet at 0.50 fill, winning PnL = $25, NOT 0.0025
        assert abs(result["total_pnl"]) > 1.0  # Real USD, not fractional


class TestReplayPaperPnlEdgeCases:
    """Edge cases for replay_paper_pnl."""

    def test_unfilled_trades_skipped(self):
        """Trades with fill_status != 'filled' should contribute zero PnL."""
        arrays = _make_replay_arrays(n=3, size_usd=25.0, target=1.0)
        arrays["fill_statuses"] = ["filled", "no_trade", "rejected"]
        result = replay_paper_pnl(arrays)
        assert result["n_trades"] == 1

    def test_zero_size_skipped(self):
        """Trades with size_usd=0 should be skipped."""
        arrays = _make_replay_arrays(n=2, size_usd=25.0, target=1.0)
        arrays["sizes"] = np.array([25.0, 0.0])
        result = replay_paper_pnl(arrays)
        assert result["n_trades"] == 1

    def test_empty_arrays(self):
        """Empty input should produce zero PnL."""
        arrays = _make_replay_arrays(n=0)
        arrays["fill_statuses"] = []
        result = replay_paper_pnl(arrays)
        assert result["total_pnl"] == 0.0
        assert result["n_trades"] == 0

    def test_mixed_wins_and_losses(self):
        """Mixed outcomes should net out correctly."""
        arrays = _make_replay_arrays(n=4, size_usd=20.0, fill_price=0.50)
        arrays["targets"] = np.array([1.0, 0.0, 1.0, 0.0])  # 2 wins, 2 losses
        result = replay_paper_pnl(arrays, fee_bps=0)

        # Each win: shares=40, pnl=+20. Each loss: pnl=-20.
        # Net = 2*20 - 2*20 = 0
        assert result["total_pnl"] == pytest.approx(0.0, abs=0.01)
        assert result["n_trades"] == 4
        assert result["win_rate"] == pytest.approx(0.5, abs=0.01)

    def test_bet_down_correct(self):
        """Betting DOWN when model < market should be handled correctly."""
        arrays = _make_replay_arrays(
            n=1, size_usd=25.0, fill_price=0.50,
            model_prob=0.15, market_prob=0.50, target=0.0,  # DOWN is correct
        )
        result = replay_paper_pnl(arrays, fee_bps=0)

        # Betting DOWN: edge_down > edge_up, correct since target=0
        # shares = 25/0.50 = 50, pnl = 50*(1-0.50) = 25
        assert result["total_pnl"] == pytest.approx(25.0, abs=0.01)
        assert result["n_trades"] == 1
