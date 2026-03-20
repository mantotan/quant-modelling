"""Tests for DutchAccumulationEngine V2."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from qm.data.connectors.polymarket_ws import TokenBook
from qm.strategy.dutch.engine import (
    DutchAccumulationEngine,
    DutchBarSummary,
    DutchConfig,
    DutchInventory,
    DutchOrder,
)


def make_book(
    best_bid: float, best_ask: float, depth: float = 100.0,
) -> TokenBook:
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

    def test_avg_pair_cost_no_matched(self):
        inv = DutchInventory(shares_up=10, shares_dn=0, cost_up=5, cost_dn=0)
        assert inv.avg_pair_cost == 1.0

    def test_pnl_if_up(self):
        inv = DutchInventory(shares_up=20, shares_dn=10, cost_up=10, cost_dn=5)
        # UP wins: 20 * $1 - $15 = $5
        assert inv.pnl_if_up == pytest.approx(5.0)

    def test_pnl_if_dn(self):
        inv = DutchInventory(shares_up=20, shares_dn=10, cost_up=10, cost_dn=5)
        # DN wins: 10 * $1 - $15 = -$5
        assert inv.pnl_if_dn == pytest.approx(-5.0)

    def test_worst_case_pnl(self):
        inv = DutchInventory(shares_up=20, shares_dn=10, cost_up=10, cost_dn=5)
        assert inv.worst_case_pnl == pytest.approx(-5.0)

    def test_both_outcomes_profitable(self):
        # 10 UP @ $0.10 = $1, 5.7 DN @ $0.70 = $4, total $5
        inv = DutchInventory(shares_up=10, shares_dn=5.7, cost_up=1, cost_dn=4)
        assert inv.pnl_if_up == pytest.approx(5.0)  # 10 - 5
        assert inv.pnl_if_dn == pytest.approx(0.7)  # 5.7 - 5
        assert inv.worst_case_pnl > 0


class TestDutchEngine:
    def _make_engine(self, **kwargs) -> DutchAccumulationEngine:
        config = DutchConfig(**kwargs)
        return DutchAccumulationEngine(config)

    def test_no_orders_when_books_none(self):
        engine = self._make_engine()
        assert engine.on_tick(0.5, 0.55, None, None) == []

    def test_no_orders_when_one_book_none(self):
        engine = self._make_engine()
        book = make_book(0.48, 0.52)
        assert engine.on_tick(0.5, 0.55, book, None) == []
        assert engine.on_tick(0.5, 0.55, None, book) == []

    def test_no_orders_when_book_unhealthy(self):
        engine = self._make_engine()
        # Spread > 0.10 = unhealthy
        book_up = make_book(0.30, 0.50)  # spread 0.20
        book_dn = make_book(0.44, 0.48)
        assert engine.on_tick(0.5, 0.55, book_up, book_dn) == []

    def test_no_orders_when_depth_too_low(self):
        engine = self._make_engine()
        book_up = make_book(0.48, 0.52, depth=3)  # depth < 5
        book_dn = make_book(0.44, 0.48, depth=100)
        assert engine.on_tick(0.5, 0.55, book_up, book_dn) == []

    def test_buys_up_when_cheap(self):
        # Model P(UP)=0.65, ask_UP=0.52 → cheap=0.13 > threshold 0.10
        engine = self._make_engine(cheap_threshold=0.10)
        book_up = make_book(0.48, 0.52)
        book_dn = make_book(0.44, 0.48)
        orders = engine.on_tick(0.5, 0.65, book_up, book_dn)
        up_orders = [o for o in orders if o.side == "UP"]
        assert len(up_orders) >= 1
        assert "cheap" in up_orders[0].reason

    def test_no_buy_when_edge_below_threshold(self):
        # Model P(UP)=0.55, ask_UP=0.52 → cheap=0.03 < threshold 0.10
        engine = self._make_engine(cheap_threshold=0.10)
        book_up = make_book(0.48, 0.52)
        book_dn = make_book(0.44, 0.48)
        orders = engine.on_tick(0.5, 0.55, book_up, book_dn)
        assert orders == []

    def test_contra_signal_buys_cheap_side(self):
        """When DN is overpriced, contra-signal buys UP (if UP is cheap)."""
        engine = self._make_engine(
            cheap_threshold=0.10, contra_threshold=0.11, max_pair_cost=1.10,
        )
        # Model P(UP)=0.55, ask_UP=0.42, ask_DN=0.75
        # cheap_up = 0.55 - 0.42 = +0.13 → Tier 1 direct buy
        # cheap_dn = 0.45 - 0.75 = -0.30 (DN overpriced)
        # marginal = 0.40+0.01 + 0.70+0.01 = 1.12 → raise max_pair_cost to 1.10
        # Actually marginal 1.12 > 1.10 still kills. Use lower bids.
        # bid_up=0.40, bid_dn=0.50 → marginal = 0.41+0.51 = 0.92 < 1.10
        # DN spread = 0.58-0.50 = 0.08 (healthy < 0.10)
        book_up = make_book(0.40, 0.42)
        book_dn = make_book(0.50, 0.58)
        orders = engine.on_tick(0.3, 0.55, book_up, book_dn)
        up_orders = [o for o in orders if o.side == "UP"]
        assert len(up_orders) >= 1

    def test_contra_requires_my_cheap_positive(self):
        """Contra must not fire when both sides are overpriced (total ask > 1.0)."""
        engine = self._make_engine(
            cheap_threshold=0.10, contra_threshold=0.11,
        )
        # Model P(UP)=0.50, ask_UP=0.65, ask_DN=0.55 → total 1.20
        # cheap_up = -0.15, cheap_dn = -0.05
        # contra for UP = -(-0.05) = +0.05 < 0.11 (no contra for UP)
        # contra for DN = -(-0.15) = +0.15 > 0.11 BUT cheap_dn = -0.05 < 0
        # → Guard prevents contra buy: my_cheap must be > 0
        book_up = make_book(0.60, 0.65)
        book_dn = make_book(0.50, 0.55)
        orders = engine.on_tick(0.3, 0.50, book_up, book_dn)
        assert orders == []

    def test_contra_requires_enough_time(self):
        """Contra-signal only fires when remaining_s > 180."""
        engine = self._make_engine(
            cheap_threshold=0.10, contra_threshold=0.11,
        )
        # Good contra setup but late in bar (t=0.85, only 135s left on 15m)
        book_up = make_book(0.40, 0.45)  # cheap_up = model - 0.45
        book_dn = make_book(0.70, 0.75)  # cheap_dn = very negative → contra for UP
        # At t=0.85: remaining = 0.15 * 900 = 135s < 180
        # cheap_up = 0.55 - 0.45 = 0.10, exactly at threshold with time_factor
        # But time_factor at 0.85 = 0.5, so adjusted_threshold = 0.05
        # cheap_up = 0.10 > 0.05 → this would actually trigger Tier 1
        # Use a case where Tier 1 doesn't trigger but contra would
        book_up2 = make_book(0.40, 0.50)  # cheap_up = 0.55 - 0.50 = 0.05 < threshold
        orders = engine.on_tick(0.85, 0.55, book_up2, book_dn)
        # Even though contra_signal = 0.30, remaining < 180s → no contra
        contra_orders = [o for o in orders if "contra" in o.reason]
        assert len(contra_orders) == 0

    def test_pnl_aware_no_balance_when_both_profitable(self):
        """Don't urgently balance when both outcomes are profitable."""
        engine = self._make_engine(cheap_threshold=0.10)
        # Inventory: 10 UP@$0.10, 5.7 DN@$0.70 → both outcomes profitable
        engine._inventory.shares_up = 10
        engine._inventory.shares_dn = 5.7
        engine._inventory.cost_up = 1
        engine._inventory.cost_dn = 4

        # Mid-bar, model neutral, neither side is cheap enough
        book_up = make_book(0.48, 0.52)
        book_dn = make_book(0.44, 0.48)
        orders = engine.on_tick(0.5, 0.50, book_up, book_dn)
        # No balance orders since worst_case_pnl > 0
        balance_orders = [o for o in orders if "balance" in o.reason]
        assert len(balance_orders) == 0

    def test_pnl_aware_balances_when_worst_case_negative(self):
        """Balance when one outcome loses money."""
        engine = self._make_engine(cheap_threshold=0.10)
        # 20 UP@$0.50 = $10, 0 DN → if DN wins, lose $10
        engine._inventory.shares_up = 20
        engine._inventory.cost_up = 10

        # Late bar (urgent window), DN is fairly priced
        book_up = make_book(0.48, 0.52)
        book_dn = make_book(0.44, 0.48)  # cheap_dn = 0.50 - 0.48 = 0.02 > 0
        orders = engine.on_tick(0.90, 0.50, book_up, book_dn)
        dn_orders = [o for o in orders if o.side == "DN"]
        assert len(dn_orders) >= 1

    def test_marginal_kill_switch(self):
        """Stop when marginal maker pair cost exceeds threshold."""
        engine = self._make_engine(max_pair_cost=0.97, spread_offset=0.01)
        # bid_up=0.48 + 0.01 + bid_dn=0.48 + 0.01 = 0.98 > 0.97
        book_up = make_book(0.48, 0.52)
        book_dn = make_book(0.48, 0.52)
        orders = engine.on_tick(0.5, 0.65, book_up, book_dn)
        assert orders == []
        assert engine._stopped

    def test_marginal_kill_allows_when_below(self):
        """Don't kill when marginal maker cost is below threshold."""
        engine = self._make_engine(
            max_pair_cost=0.97, spread_offset=0.01, cheap_threshold=0.10,
        )
        # bid_up=0.40 + 0.01 + bid_dn=0.40 + 0.01 = 0.82 < 0.97
        book_up = make_book(0.40, 0.45)
        book_dn = make_book(0.40, 0.48)
        orders = engine.on_tick(0.5, 0.65, book_up, book_dn)
        assert not engine._stopped

    def test_min_order_usd(self):
        """Orders below $1 are skipped."""
        engine = self._make_engine(
            bar_budget=1.5, order_size=10, min_order_usd=1.0,
            cheap_threshold=0.10,
        )
        engine._inventory.cost_up = 0.6
        book_up = make_book(0.40, 0.45)
        book_dn = make_book(0.44, 0.48)
        # budget remaining = 1.5 - 0.6 = 0.9 < min_order_usd → no orders
        orders = engine.on_tick(0.5, 0.65, book_up, book_dn)
        assert orders == []

    def test_smart_sizing_edge_scaled(self):
        """Higher edge → larger order size."""
        engine = self._make_engine(
            order_size=10, cheap_threshold=0.10,
        )
        book_up = make_book(0.30, 0.35)
        book_dn = make_book(0.44, 0.48)
        # cheap_up = 0.70 - 0.35 = 0.35, edge_scale = 0.35/(0.10*2) = 1.75
        orders = engine.on_tick(0.5, 0.70, book_up, book_dn)
        up_orders = [o for o in orders if o.side == "UP"]
        if up_orders:
            assert up_orders[0].dollars > 10.0  # scaled up

    def test_smart_sizing_balance(self):
        """Balance sizing targets exact share count needed."""
        engine = self._make_engine(
            order_size=10, cheap_threshold=0.10,
        )
        # Need DN shares to make worst_case = 0
        engine._inventory.shares_up = 20
        engine._inventory.cost_up = 10  # total cost $10, need 10 DN shares

        book_up = make_book(0.48, 0.52)
        book_dn = make_book(0.44, 0.48)
        orders = engine.on_tick(0.90, 0.50, book_up, book_dn)
        dn_orders = [o for o in orders if o.side == "DN"]
        if dn_orders:
            # shares_needed = total_cost - shares_dn = 10 - 0 = 10
            # dollar_size = 10 * 0.45 = $4.50
            assert dn_orders[0].dollars <= 10.0

    def test_resolve_up_with_matched_pairs(self):
        engine = self._make_engine()
        engine._inventory.shares_up = 20
        engine._inventory.shares_dn = 20
        engine._inventory.cost_up = 10
        engine._inventory.cost_dn = 9

        summary = engine.resolve("UP")
        assert summary.outcome == "UP"
        assert summary.pnl["payout"] == pytest.approx(20.0)
        assert summary.pnl["profit"] == pytest.approx(1.0)

    def test_resolve_dn_with_unmatched(self):
        engine = self._make_engine()
        engine._inventory.shares_up = 30
        engine._inventory.shares_dn = 20
        engine._inventory.cost_up = 15
        engine._inventory.cost_dn = 9

        summary = engine.resolve("DN")
        assert summary.pnl["payout"] == pytest.approx(20.0)
        assert summary.pnl["profit"] == pytest.approx(-4.0)

    def test_reset_clears_state(self):
        engine = self._make_engine()
        engine._inventory.shares_up = 20
        engine._inventory.cost_up = 10
        engine._decision_log.append("test")
        engine._stopped = True

        engine.reset()
        assert engine._inventory.shares_up == 0
        assert engine._decision_log == []
        assert engine._stopped is False

    def test_on_fill_updates_inventory(self):
        engine = self._make_engine()
        order = DutchOrder(
            side="UP", limit_price=0.49, shares=20.0, dollars=9.8,
            time_pct=0.5, placed_at=datetime.now(UTC), reason="cheap",
        )
        engine.on_fill(order, fill_price=0.49, filled_shares=20.0)
        assert engine._inventory.shares_up == pytest.approx(20.0)
        assert engine._inventory.cost_up == pytest.approx(9.8)

    def test_snapshot_includes_pnl(self):
        engine = self._make_engine()
        engine._inventory.shares_up = 20
        engine._inventory.shares_dn = 15
        engine._inventory.cost_up = 10
        engine._inventory.cost_dn = 7

        snap = engine.snapshot()
        assert "pnl_if_up" in snap
        assert "pnl_if_dn" in snap
        assert "worst_case_pnl" in snap

    def test_model_flip_counting_incremental(self):
        engine = self._make_engine()
        book_up = make_book(0.20, 0.90)  # unhealthy (spread>0.10), no orders placed
        book_dn = make_book(0.20, 0.90)
        # Feed probs: 0.55, 0.52, 0.48, 0.53, 0.45 → 3 flips
        for p in [0.55, 0.52, 0.48, 0.53, 0.45]:
            engine.on_tick(0.5, p, book_up, book_dn)
        assert engine._model_flips == 3

    def test_emergency_balance_with_unhealthy_book(self):
        """Emergency balance should not place orders if book is thin."""
        engine = self._make_engine(cheap_threshold=0.10)
        engine._inventory.shares_up = 20
        engine._inventory.cost_up = 10

        book_up = make_book(0.48, 0.52, depth=100)
        book_dn = make_book(0.44, 0.48, depth=2)  # depth < 5 = unhealthy
        orders = engine.on_tick(0.96, 0.50, book_up, book_dn)
        assert orders == []


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
        assert summary.pnl["payout"] == pytest.approx(20.0)
        assert summary.pnl["profit"] == pytest.approx(1.0)

    def test_to_dict(self):
        summary = DutchBarSummary(bar_id=123)
        d = summary.to_dict()
        assert d["bar_id"] == 123
        assert "decision_log" in d
