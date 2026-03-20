"""Tests for BarEdgeAccumulator — one-bet-per-bar selection."""

import pytest

from qm.strategy.bar_accumulator import BarEdgeAccumulator, TradeDecision


class TestFirstConfident:
    def test_executes_when_edge_exceeds_threshold(self):
        acc = BarEdgeAccumulator(strategy="first_confident", confidence_threshold=0.05)
        result = acc.on_prediction(
            bar_id=1000, time_pct=0.30,
            model_prob=0.70, market_prob=0.50, spread=0.02,
        )
        # edge_up = 0.70 - 0.50 - 0.01 = 0.19 > 0.05
        assert result is not None
        assert result.side == "UP"
        assert result.edge == pytest.approx(0.19)
        assert result.time_pct == 0.30

    def test_skips_when_edge_below_threshold(self):
        acc = BarEdgeAccumulator(strategy="first_confident", confidence_threshold=0.10)
        result = acc.on_prediction(
            bar_id=1000, time_pct=0.30,
            model_prob=0.55, market_prob=0.50, spread=0.02,
        )
        # edge_up = 0.55 - 0.50 - 0.01 = 0.04 < 0.10
        assert result is None

    def test_locks_out_after_first_trade(self):
        acc = BarEdgeAccumulator(strategy="first_confident", confidence_threshold=0.05)
        # First prediction: triggers trade
        r1 = acc.on_prediction(1000, 0.30, 0.70, 0.50, 0.02)
        assert r1 is not None
        # Second prediction: locked out
        r2 = acc.on_prediction(1000, 0.80, 0.80, 0.50, 0.02)
        assert r2 is None

    def test_different_bars_independent(self):
        acc = BarEdgeAccumulator(strategy="first_confident", confidence_threshold=0.05)
        r1 = acc.on_prediction(1000, 0.30, 0.70, 0.50, 0.02)
        r2 = acc.on_prediction(1300, 0.30, 0.70, 0.50, 0.02)
        assert r1 is not None
        assert r2 is not None
        assert r1.bar_id == 1000
        assert r2.bar_id == 1300

    def test_on_bar_end_returns_best_sub_threshold(self):
        """If no prediction exceeded threshold, bar_end returns the best one."""
        acc = BarEdgeAccumulator(strategy="first_confident", confidence_threshold=0.20)
        # All below 0.20 threshold
        acc.on_prediction(1000, 0.30, 0.55, 0.50, 0.02)  # edge=0.04
        acc.on_prediction(1000, 0.50, 0.60, 0.50, 0.02)  # edge=0.09
        acc.on_prediction(1000, 0.80, 0.58, 0.50, 0.02)  # edge=0.07

        result = acc.on_bar_end(1000)
        assert result is not None
        assert result.edge == pytest.approx(0.09)  # best of the three
        assert result.time_pct == 0.50

    def test_on_bar_end_none_if_already_committed(self):
        acc = BarEdgeAccumulator(strategy="first_confident", confidence_threshold=0.05)
        acc.on_prediction(1000, 0.30, 0.70, 0.50, 0.02)  # triggers trade
        result = acc.on_bar_end(1000)
        assert result is None


class TestBestEdge:
    def test_never_executes_immediately(self):
        acc = BarEdgeAccumulator(strategy="best_edge")
        r = acc.on_prediction(1000, 0.30, 0.90, 0.50, 0.02)
        assert r is None  # even with huge edge

    def test_on_bar_end_returns_best(self):
        acc = BarEdgeAccumulator(strategy="best_edge")
        acc.on_prediction(1000, 0.10, 0.55, 0.50, 0.02)  # edge=0.04
        acc.on_prediction(1000, 0.40, 0.70, 0.50, 0.02)  # edge=0.19
        acc.on_prediction(1000, 0.80, 0.60, 0.50, 0.02)  # edge=0.09

        result = acc.on_bar_end(1000)
        assert result is not None
        assert result.edge == pytest.approx(0.19)
        assert result.time_pct == 0.40

    def test_no_side_flipping(self):
        """Even if model flips side, accumulator picks the best single trade."""
        acc = BarEdgeAccumulator(strategy="best_edge")
        acc.on_prediction(1000, 0.30, 0.40, 0.50, 0.02)  # DOWN, edge=0.09
        acc.on_prediction(1000, 0.80, 0.70, 0.50, 0.02)  # UP, edge=0.19

        result = acc.on_bar_end(1000)
        assert result is not None
        assert result.side == "UP"  # picks the higher edge regardless of previous side
        assert result.edge == pytest.approx(0.19)

    def test_on_bar_end_empty(self):
        acc = BarEdgeAccumulator(strategy="best_edge")
        result = acc.on_bar_end(9999)
        assert result is None


class TestEdgeCases:
    def test_zero_edge_ignored(self):
        acc = BarEdgeAccumulator(strategy="first_confident", confidence_threshold=0.01)
        r = acc.on_prediction(1000, 0.80, 0.50, 0.50, 0.02)
        # edge_up = 0.50 - 0.50 - 0.01 = -0.01, edge_down same → both ≤ 0
        assert r is None

    def test_negative_edge_ignored(self):
        acc = BarEdgeAccumulator(strategy="best_edge")
        acc.on_prediction(1000, 0.80, 0.50, 0.50, 0.10)  # big spread kills edge
        result = acc.on_bar_end(1000)
        assert result is None

    def test_cleanup_old_bars(self):
        acc = BarEdgeAccumulator(strategy="best_edge")
        acc.on_prediction(1000, 0.30, 0.70, 0.50, 0.02)
        acc.on_prediction(5000, 0.30, 0.70, 0.50, 0.02)
        assert acc.pending_bars == 2

        acc.cleanup_old_bars(current_bar_id=5000, max_age=5)
        assert acc.pending_bars == 1  # bar 1000 cleaned up

    def test_down_side_selected(self):
        acc = BarEdgeAccumulator(strategy="first_confident", confidence_threshold=0.01)
        r = acc.on_prediction(1000, 0.80, 0.30, 0.50, 0.02)
        # edge_down = (1-0.30) - (1-0.50) - 0.01 = 0.70 - 0.50 - 0.01 = 0.19
        assert r is not None
        assert r.side == "DOWN"
        assert r.edge == pytest.approx(0.19)
