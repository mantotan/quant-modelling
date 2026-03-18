"""Tests for Portfolio and edge calculation."""

import pytest
from datetime import datetime, timezone

from qm.core.types import Asset, Outcome
from qm.risk.bankroll import Bankroll
from qm.strategy.edge import compute_edge
from qm.strategy.portfolio import Portfolio


class TestEdgeCalculation:
    def test_up_edge(self):
        edge, side = compute_edge(model_prob_up=0.65, market_prob_up=0.50, spread=0.02)
        assert side == Outcome.UP
        assert edge == pytest.approx(0.14)  # 0.65 - 0.50 - 0.01

    def test_down_edge(self):
        edge, side = compute_edge(model_prob_up=0.35, market_prob_up=0.50, spread=0.02)
        assert side == Outcome.DOWN
        assert edge == pytest.approx(0.14)  # 0.65 - 0.50 - 0.01 (symmetric)

    def test_no_edge_with_spread(self):
        edge, _ = compute_edge(model_prob_up=0.52, market_prob_up=0.50, spread=0.06)
        assert edge < 0  # spread eats the edge

    def test_exact_50_50(self):
        edge, _ = compute_edge(0.50, 0.50, 0.02)
        assert edge < 0  # spread makes both sides negative


class TestPortfolio:
    def test_initial_state(self):
        br = Bankroll(initial=10000)
        p = Portfolio(bankroll=br)
        assert p.open_position_count == 0
        assert p.available_cash == 10000

    def test_fill_creates_position(self):
        br = Bankroll(initial=10000)
        p = Portfolio(bankroll=br)
        pos = p.on_fill(Asset.BTC, Outcome.UP, 100.0, 0.55)
        assert p.open_position_count == 1
        assert pos.shares == pytest.approx(100 / 0.55)
        assert p.available_cash == pytest.approx(9900)

    def test_resolution_win(self):
        br = Bankroll(initial=10000)
        p = Portfolio(bankroll=br)
        pos = p.on_fill(Asset.BTC, Outcome.UP, 100.0, 0.50, condition_id="cond1")

        pnl = p.on_resolution("cond1", Outcome.UP)  # correct!
        assert pnl > 0  # won: receive $1/share, profit = shares * (1 - 0.50)
        assert p.open_position_count == 0
        assert br.current > 10000

    def test_resolution_loss(self):
        br = Bankroll(initial=10000)
        p = Portfolio(bankroll=br)
        p.on_fill(Asset.ETH, Outcome.UP, 200.0, 0.60, condition_id="cond2")

        pnl = p.on_resolution("cond2", Outcome.DOWN)  # wrong!
        assert pnl < 0  # lost: shares worth zero
        assert p.open_position_count == 0
        assert br.current < 10000

    def test_multiple_positions_same_market(self):
        br = Bankroll(initial=10000)
        p = Portfolio(bankroll=br)
        p.on_fill(Asset.BTC, Outcome.UP, 100.0, 0.50, condition_id="cond3")
        p.on_fill(Asset.BTC, Outcome.UP, 50.0, 0.55, condition_id="cond3")

        assert p.open_position_count == 2
        pnl = p.on_resolution("cond3", Outcome.UP)
        assert p.open_position_count == 0
        assert pnl > 0

    def test_asset_exposures(self):
        br = Bankroll(initial=10000)
        p = Portfolio(bankroll=br)
        p.on_fill(Asset.BTC, Outcome.UP, 300.0, 0.50)
        p.on_fill(Asset.ETH, Outcome.DOWN, 200.0, 0.40)

        exposures = p.asset_exposures()
        assert exposures[Asset.BTC] == 300.0
        assert exposures[Asset.ETH] == 200.0

    def test_serialization_roundtrip(self):
        br = Bankroll(initial=10000)
        p = Portfolio(bankroll=br)
        p.on_fill(Asset.BTC, Outcome.UP, 100.0, 0.50, condition_id="c1")

        data = p.to_dict()
        p2 = Portfolio.from_dict(data)

        assert p2.open_position_count == 1
        assert p2.bankroll.current == p.bankroll.current
        assert p2.open_positions[0].asset == Asset.BTC
