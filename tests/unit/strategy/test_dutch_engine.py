"""Tests for DutchAccumulationEngine."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from qm.data.connectors.polymarket_ws import TokenBook
from qm.strategy.dutch.engine import (
    DutchAccumulationEngine,
    DutchBarSummary,
    DutchConfig,
    DutchInventory,
)


def make_book(best_bid: float, best_ask: float, depth: float = 100.0) -> TokenBook:
    """Create a TokenBook with a single level on each side."""
    book = TokenBook(token_id="test")
    book.bids = {best_bid: depth}
    book.asks = {best_ask: depth}
    book._update_bbo()
    return book


class TestDutchInventory:
    def test_matched_equal_shares(self):
        inv = DutchInventory(shares_up=20, shares_dn=20, cost_up=10, cost_dn=9)
        assert inv.matched == 20

    def test_matched_asymmetric(self):
        inv = DutchInventory(shares_up=30, shares_dn=20, cost_up=15, cost_dn=9)
        assert inv.matched == 20

    def test_avg_pair_cost_symmetric(self):
        inv = DutchInventory(shares_up=20, shares_dn=20, cost_up=10, cost_dn=9)
        assert inv.avg_pair_cost == pytest.approx(0.95, abs=0.001)

    def test_avg_pair_cost_asymmetric(self):
        # 30 UP at avg 0.50, 20 DN at avg 0.45
        inv = DutchInventory(shares_up=30, shares_dn=20, cost_up=15, cost_dn=9)
        # matched=20, frac_up=20/30=0.667, frac_dn=20/20=1.0
        # pair_cost = (15*0.667 + 9*1.0) / 20 = (10 + 9) / 20 = 0.95
        assert inv.avg_pair_cost == pytest.approx(0.95, abs=0.001)

    def test_avg_pair_cost_no_matched(self):
        inv = DutchInventory(shares_up=10, shares_dn=0, cost_up=5, cost_dn=0)
        assert inv.avg_pair_cost == 1.0

    def test_imbalance(self):
        inv = DutchInventory(shares_up=30, shares_dn=20)
        assert inv.imbalance == pytest.approx(10)

    def test_total_cost(self):
        inv = DutchInventory(cost_up=10, cost_dn=9)
        assert inv.total_cost == pytest.approx(19)


class TestDutchEngine:
    def _make_engine(self, **kwargs) -> DutchAccumulationEngine:
        config = DutchConfig(**kwargs)
        return DutchAccumulationEngine(config)

    def test_no_orders_when_books_none(self):
        engine = self._make_engine()
        orders = engine.on_tick(0.5, 0.55, None, None)
        assert orders == []

    def test_no_orders_when_one_book_none(self):
        engine = self._make_engine()
        book = make_book(0.48, 0.52)
        assert engine.on_tick(0.5, 0.55, book, None) == []
        assert engine.on_tick(0.5, 0.55, None, book) == []

    def test_buys_up_when_cheap(self):
        engine = self._make_engine(cheap_threshold=0.02, cooldown_s=0)
        book_up = make_book(0.48, 0.52)
        book_dn = make_book(0.44, 0.48)
        # model says P(UP)=0.58, ask_up=0.52, cheap_score=0.06 > 0.02
        orders = engine.on_tick(0.5, 0.58, book_up, book_dn)
        up_orders = [o for o in orders if o.side == "UP"]
        assert len(up_orders) >= 1
        assert up_orders[0].limit_price == pytest.approx(0.49, abs=0.01)

    def test_buys_dn_when_model_favors_dn(self):
        engine = self._make_engine(cheap_threshold=0.02, cooldown_s=0)
        book_up = make_book(0.48, 0.52)
        book_dn = make_book(0.44, 0.46)
        # model says P(UP)=0.42, so P(DN)=0.58, ask_dn=0.46, cheap_score=0.12
        orders = engine.on_tick(0.5, 0.42, book_up, book_dn)
        dn_orders = [o for o in orders if o.side == "DN"]
        assert len(dn_orders) >= 1

    def test_prioritizes_imbalanced_side(self):
        engine = self._make_engine(cheap_threshold=0.02, cooldown_s=0, order_size=10)
        book_up = make_book(0.48, 0.52)
        book_dn = make_book(0.44, 0.48)

        # Manually set inventory: holding UP but no DN
        engine._inventory.shares_up = 20
        engine._inventory.cost_up = 10

        # Model is neutral (0.50), both sides have same cheap_score
        orders = engine.on_tick(0.5, 0.50, book_up, book_dn)
        # Should buy DN because imbalance=20 (need DN)
        dn_orders = [o for o in orders if o.side == "DN"]
        assert len(dn_orders) >= 1

    def test_kill_switch_on_high_pair_cost(self):
        engine = self._make_engine(max_pair_cost=0.97, cooldown_s=0)
        # Set inventory with high avg pair cost
        engine._inventory.shares_up = 20
        engine._inventory.shares_dn = 20
        engine._inventory.cost_up = 10  # 0.50 avg
        engine._inventory.cost_dn = 10  # 0.50 avg → pair cost = 1.0

        book_up = make_book(0.48, 0.52)
        book_dn = make_book(0.44, 0.48)
        orders = engine.on_tick(0.5, 0.58, book_up, book_dn)
        assert orders == []

    def test_budget_exhaustion_stops_orders(self):
        engine = self._make_engine(bar_budget=15, order_size=10, cooldown_s=0)
        engine._inventory.cost_up = 12
        engine._inventory.cost_dn = 2  # total=14, remaining=1 < 10*0.5

        book_up = make_book(0.48, 0.52)
        book_dn = make_book(0.44, 0.48)
        orders = engine.on_tick(0.5, 0.58, book_up, book_dn)
        assert orders == []

    def test_emergency_balance_in_late_bar(self):
        engine = self._make_engine(
            cheap_threshold=0.05, cooldown_s=0,
            min_time_remaining=30, emergency_balance_time=120,
        )
        engine._inventory.shares_up = 20
        engine._inventory.cost_up = 10

        book_up = make_book(0.48, 0.52)
        book_dn = make_book(0.44, 0.49)

        # At t=0.90 (90s left on 15m bar), model neutral
        # cheap_score_dn = 0.50 - 0.49 = 0.01, below threshold 0.05
        # but imbalance=20, should trigger urgent_balance (needs cheap_score > 0)
        orders = engine.on_tick(0.90, 0.50, book_up, book_dn)
        dn_orders = [o for o in orders if o.side == "DN"]
        assert len(dn_orders) >= 1

    def test_cooldown_prevents_spam(self):
        engine = self._make_engine(cheap_threshold=0.02, cooldown_s=10)
        book_up = make_book(0.48, 0.52)
        book_dn = make_book(0.44, 0.48)

        # First tick: should place
        orders1 = engine.on_tick(0.50, 0.58, book_up, book_dn)
        assert len(orders1) > 0

        # Second tick 2s later: cooldown blocks (10s cooldown, only 2s passed)
        orders2 = engine.on_tick(0.5022, 0.58, book_up, book_dn)  # ~2s later on 900s bar
        # The side that was just ordered should be blocked
        sides1 = {o.side for o in orders1}
        sides2 = {o.side for o in orders2}
        assert not (sides1 & sides2), "Cooldown should prevent same-side orders"

    def test_resolve_up_with_matched_pairs(self):
        engine = self._make_engine()
        engine._inventory.shares_up = 20
        engine._inventory.shares_dn = 20
        engine._inventory.cost_up = 10
        engine._inventory.cost_dn = 9

        summary = engine.resolve("UP")
        assert summary.outcome == "UP"
        assert summary.pnl["payout"] == pytest.approx(20.0)  # 20 matched × $1
        assert summary.pnl["profit"] == pytest.approx(1.0)  # 20 - 19

    def test_resolve_dn_with_unmatched(self):
        engine = self._make_engine()
        engine._inventory.shares_up = 30
        engine._inventory.shares_dn = 20
        engine._inventory.cost_up = 15
        engine._inventory.cost_dn = 9

        summary = engine.resolve("DN")
        # matched=20, unmatched_up=10
        # payout = 20 (matched) + 0 (UP unmatched loses when DN wins) = 20
        assert summary.pnl["payout"] == pytest.approx(20.0)
        assert summary.pnl["profit"] == pytest.approx(-4.0)  # 20 - 24

    def test_resolve_up_with_unmatched_up_wins(self):
        engine = self._make_engine()
        engine._inventory.shares_up = 30
        engine._inventory.shares_dn = 20
        engine._inventory.cost_up = 15
        engine._inventory.cost_dn = 9

        summary = engine.resolve("UP")
        # matched=20, unmatched_up=10
        # payout = 20 (matched) + 10 (unmatched UP wins) = 30
        assert summary.pnl["payout"] == pytest.approx(30.0)
        assert summary.pnl["profit"] == pytest.approx(6.0)  # 30 - 24

    def test_reset_clears_state(self):
        engine = self._make_engine()
        engine._inventory.shares_up = 20
        engine._inventory.cost_up = 10
        engine._decision_log.append("test")
        engine._stopped = True

        engine.reset()
        assert engine._inventory.shares_up == 0
        assert engine._inventory.cost_up == 0
        assert engine._decision_log == []
        assert engine._stopped is False

    def test_on_fill_updates_inventory(self):
        engine = self._make_engine()
        from qm.strategy.dutch.engine import DutchOrder

        order = DutchOrder(
            side="UP", limit_price=0.49, shares=20.0, dollars=9.8,
            time_pct=0.5, placed_at=datetime.now(UTC), reason="cheap",
        )
        engine.on_fill(order, fill_price=0.49, filled_shares=20.0)
        assert engine._inventory.shares_up == pytest.approx(20.0)
        assert engine._inventory.cost_up == pytest.approx(9.8)

    def test_snapshot_returns_current_state(self):
        engine = self._make_engine()
        engine._inventory.shares_up = 20
        engine._inventory.shares_dn = 15
        engine._inventory.cost_up = 10
        engine._inventory.cost_dn = 7

        snap = engine.snapshot()
        assert snap["shares_up"] == 20
        assert snap["shares_dn"] == 15
        assert snap["matched"] == 15
        assert snap["unmatched_up"] == 5

    def test_model_flip_counting(self):
        engine = self._make_engine()
        engine._model_probs = [0.55, 0.52, 0.48, 0.53, 0.45]
        # Flips: 0.52→0.48 (crosses 0.5), 0.48→0.53, 0.53→0.45 = 3 flips
        assert engine._count_flips() == 3


class TestDutchBarSummary:
    def test_compute_pnl_up_wins(self):
        summary = DutchBarSummary()
        summary.inventory = {"matched": 20, "unmatched_up": 5, "unmatched_dn": 0}
        summary.cost = {"total": 19.0}
        summary.compute_pnl("UP")
        assert summary.pnl["payout"] == pytest.approx(25.0)
        assert summary.pnl["profit"] == pytest.approx(6.0)

    def test_compute_pnl_dn_wins(self):
        summary = DutchBarSummary()
        summary.inventory = {"matched": 20, "unmatched_up": 5, "unmatched_dn": 0}
        summary.cost = {"total": 19.0}
        summary.compute_pnl("DN")
        # unmatched UP loses → payout = 20 only
        assert summary.pnl["payout"] == pytest.approx(20.0)
        assert summary.pnl["profit"] == pytest.approx(1.0)

    def test_to_dict(self):
        summary = DutchBarSummary(bar_id=123)
        d = summary.to_dict()
        assert d["bar_id"] == 123
        assert "orders" in d
        assert "decision_log" in d
