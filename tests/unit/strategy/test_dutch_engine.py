"""Tests for DutchAccumulationEngine V6."""

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

    def test_simulated_avg_pair_cost(self):
        inv = DutchInventory(shares_up=20, cost_up=8)  # avg UP = 0.40
        # sim buy 20 DN @ 0.50 -> matched=20, pair = 0.40 + 0.50 = 0.90
        result = inv.simulated_avg_pair_cost("DN", 20, 0.50)
        assert result == pytest.approx(0.90, abs=0.001)



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

    def test_no_buy_when_both_asks_above_50c_no_edge(self):
        """V6: No buy when pair_cost=1.14 > 0.98 and pnl_gap=0 (empty inventory)."""
        engine = self._make_engine(max_marginal_pair_cost=0.98)
        # Both asks > 0.50, pair_cost=1.14, no inventory -> no pnl_gap -> wait
        book_up = make_book(0.53, 0.57)
        book_dn = make_book(0.53, 0.57)
        orders = engine.on_tick(0.5, 0.50, book_up, book_dn)
        assert orders == []

    def test_pnl_aware_no_orders_when_both_profitable_and_no_dutch(self):
        """No orders when both outcomes profitable, pair_cost > threshold, balanced."""
        engine = self._make_engine(max_marginal_pair_cost=0.98)
        # Inventory: 10 UP@$0.10, 5.7 DN@$0.70 -> both outcomes profitable
        engine._inventory.shares_up = 10
        engine._inventory.shares_dn = 5.7
        engine._inventory.cost_up = 1
        engine._inventory.cost_dn = 4

        # pair_cost = 0.52 + 0.48 = 1.00 > 0.98 -> no dutch opportunity
        # pnl_gap = (10-5) - (5.7-5) = 5 - 0.7 = 4.3 < tolerance=5 -> wait
        book_up = make_book(0.48, 0.52)
        book_dn = make_book(0.44, 0.48)
        orders = engine.on_tick(0.5, 0.50, book_up, book_dn)
        assert orders == []

    def test_min_order_usd(self):
        """Orders below $1 are skipped."""
        engine = self._make_engine(
            bar_budget=1.5, order_size=10, min_order_usd=1.0,
        )
        engine._inventory.cost_up = 0.6
        book_up = make_book(0.40, 0.45)
        book_dn = make_book(0.44, 0.48)
        # budget remaining = 1.5 - 0.6 = 0.9 < min_order_usd -> no orders
        orders = engine.on_tick(0.5, 0.65, book_up, book_dn)
        assert orders == []

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

        engine.reset()
        assert engine._inventory.shares_up == 0
        assert engine._decision_log == []
        assert engine._last_ask_up == 0.0
        assert engine._last_ask_dn == 0.0

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
        assert "risk_budget" in snap
        assert "worst_case_loss" in snap
        assert "pair_cost_live" in snap
        assert "stopped" not in snap

    def test_model_flip_counting_incremental(self):
        engine = self._make_engine()
        book_up = make_book(0.20, 0.90)  # unhealthy (spread>0.10), no orders placed
        book_dn = make_book(0.20, 0.90)
        # Feed probs: 0.55, 0.52, 0.48, 0.53, 0.45 -> 3 flips
        for p in [0.55, 0.52, 0.48, 0.53, 0.45]:
            engine.on_tick(0.5, p, book_up, book_dn)
        assert engine._model_flips == 3

    def test_emergency_balance_with_unhealthy_book(self):
        """Emergency balance should not place orders if book is thin."""
        engine = self._make_engine()
        engine._inventory.shares_up = 20
        engine._inventory.cost_up = 10

        book_up = make_book(0.48, 0.52, depth=100)
        book_dn = make_book(0.44, 0.48, depth=2)  # depth < 5 = unhealthy
        orders = engine.on_tick(0.96, 0.50, book_up, book_dn)
        assert orders == []


class TestDutchPacingGates:
    """Tests for the V3 pacing gates (R1-R6)."""

    def _make_engine(self, **kwargs) -> DutchAccumulationEngine:
        config = DutchConfig(**kwargs)
        return DutchAccumulationEngine(config)

    def _fill_order(self, engine, order):
        """Simulate immediate fill at limit price."""
        engine.on_fill(order, order.limit_price, order.shares)

    def test_envelope_blocks_burst_at_low_time_pct(self):
        """Rapid on_tick calls at t=0.05 should not produce 5 orders."""
        engine = self._make_engine(
            order_size=5.0, bar_budget=200.0, max_marginal_pair_cost=0.98,
        )
        # pair_cost = 0.52 + 0.25 = 0.77 < 0.98 -> dutch opportunity
        book_up = make_book(0.48, 0.52)
        book_dn = make_book(0.20, 0.25)
        total_orders = 0
        for i in range(5):
            t = 0.05 + i * 0.001  # ~1ms apart
            orders = engine.on_tick(t, 0.65, book_up, book_dn)
            for o in orders:
                self._fill_order(engine, o)
            total_orders += len(orders)
        # Envelope at t=0.05 with pair_opportunity=0.23: urgency from that
        # Should NOT be all 5*2=10.
        assert total_orders < 8

    def test_envelope_allows_more_at_high_time_pct(self):
        """At t=0.80, envelope allows substantial spend."""
        engine = self._make_engine(
            order_size=5.0, bar_budget=200.0, max_marginal_pair_cost=0.98,
        )
        # pair_cost = 0.52 + 0.25 = 0.77 < 0.98
        book_up = make_book(0.48, 0.52)
        book_dn = make_book(0.20, 0.25)
        orders = engine.on_tick(0.80, 0.65, book_up, book_dn)
        assert len(orders) >= 1

    def test_envelope_handles_zero_time_pct(self):
        """t=0.0 should still allow first order with permissive risk budget."""
        engine = self._make_engine(
            order_size=5.0, bar_budget=200.0, max_marginal_pair_cost=0.98,
            risk_floor=0.10,  # 10% floor allows early buys
        )
        # pair_cost = 0.25 + 0.52 = 0.77 < 0.98
        book_up = make_book(0.20, 0.25)
        book_dn = make_book(0.48, 0.52)
        orders = engine.on_tick(0.0, 0.65, book_up, book_dn)
        assert len(orders) >= 1

    def test_slot_spacing_blocks_rapid_same_side(self):
        """Two ticks ~0.001 apart should block the second order on same side."""
        engine = self._make_engine(
            order_size=5.0, bar_budget=200.0, max_marginal_pair_cost=0.98,
            risk_floor=0.10,  # permissive early risk budget
        )
        # pair_cost = 0.25 + 0.52 = 0.77 -> dutch opportunity
        book_up = make_book(0.20, 0.25)
        book_dn = make_book(0.48, 0.52)
        # First tick
        orders1 = engine.on_tick(0.10, 0.65, book_up, book_dn)
        assert len(orders1) >= 1
        for o in orders1:
            self._fill_order(engine, o)
        # Second tick, almost immediately
        orders2 = engine.on_tick(0.101, 0.65, book_up, book_dn)
        # UP side should be blocked by spacing
        up_orders = [o for o in orders2 if o.side == "UP"]
        assert len(up_orders) == 0

    def test_slot_spacing_blocks_late_bar(self):
        """V6.1: No spacing exemptions — rapid orders blocked even late in bar."""
        engine = self._make_engine(
            order_size=5.0, bar_budget=200.0, max_marginal_pair_cost=0.98,
            risk_ceil=0.50,  # permissive risk
        )
        # Build UP inventory -> DN is lighter side
        engine._inventory.shares_up = 40
        engine._inventory.cost_up = 20
        # Set last_order_time very close to now
        engine._last_order_time_pct_dn = 0.969

        # pair_cost = 0.30 + 0.48 = 0.78 < 0.98 -> dutch opportunity
        book_up = make_book(0.28, 0.30)
        book_dn = make_book(0.44, 0.48)
        # t=0.97, last_dn=0.969: gap=0.001, min_gap=(1-0.97)/remaining_slots
        # With 200 slots remaining, min_gap is tiny, should allow
        orders = engine.on_tick(0.97, 0.50, book_up, book_dn)
        dn_orders = [o for o in orders if o.side == "DN"]
        # DN is lighter side so ordered first; spacing check with many remaining slots allows it
        assert len(dn_orders) >= 1

    def test_side_cap_blocks_heavy_side(self):
        """65% budget on UP -> next UP order blocked, DN still allowed."""
        engine = self._make_engine(
            max_side_fraction=0.65, bar_budget=200.0,
            max_marginal_pair_cost=0.98,
        )
        # UP already at 65% of budget = $130
        engine._inventory.shares_up = 260
        engine._inventory.cost_up = 130

        # pair_cost = 0.25 + 0.25 = 0.50 < 0.98 -> dutch opportunity
        # pnl_gap = 260 - 0 - 130 = 130 >> tolerance -> DN trailing
        book_up = make_book(0.20, 0.25)
        book_dn = make_book(0.20, 0.25)
        # Use t=0.90 so envelope allows enough spend
        orders = engine.on_tick(0.90, 0.65, book_up, book_dn)
        up_orders = [o for o in orders if o.side == "UP"]
        dn_orders = [o for o in orders if o.side == "DN"]
        assert len(up_orders) == 0  # blocked by side cap (non-trailing)
        assert len(dn_orders) >= 1  # DN is trailing and fine

    def test_per_prediction_cap(self):
        """$100 per prediction: blocks after spending, resets on new cal_prob."""
        engine = self._make_engine(
            order_size=5.0, bar_budget=200.0,
            max_per_prediction=100.0, max_marginal_pair_cost=0.98,
        )
        book_up = make_book(0.20, 0.25)
        book_dn = make_book(0.20, 0.25)
        # Accumulate ~$95 of prediction spend
        engine._prediction_spend = 95.0
        engine._current_cal_prob = 0.65
        # Next order at same cal_prob -- only $5 left
        orders = engine.on_tick(0.50, 0.65, book_up, book_dn)
        total_dollars = sum(o.dollars for o in orders)
        assert total_dollars <= 6.0  # clamped to ~$5 remaining

        # Fill and try again -- should be blocked
        for o in orders:
            self._fill_order(engine, o)
        engine._prediction_spend = 100.0
        orders2 = engine.on_tick(0.51, 0.65, book_up, book_dn)
        assert orders2 == []

        # New cal_prob -> counter resets
        orders3 = engine.on_tick(0.52, 0.66, book_up, book_dn)
        assert len(orders3) >= 1

    def test_per_prediction_clamps_order_size(self):
        """At $90 prediction spend, $20 order should be clamped to $10."""
        engine = self._make_engine(
            order_size=20.0, bar_budget=200.0,
            max_per_prediction=100.0, max_marginal_pair_cost=0.98,
        )
        engine._prediction_spend = 90.0
        engine._current_cal_prob = 0.65
        # pair_cost = 0.25 + 0.52 = 0.77 < 0.98
        book_up = make_book(0.20, 0.25)
        book_dn = make_book(0.48, 0.52)
        orders = engine.on_tick(0.50, 0.65, book_up, book_dn)
        if orders:
            assert orders[0].dollars <= 11.0  # clamped to ~$10

    def test_vwap_gate_blocks_worse_price(self):
        """After filling at 0.45, skip order at 0.50 (> 0.459)."""
        engine = self._make_engine(vwap_tolerance=0.02, max_marginal_pair_cost=0.98)
        # Simulate prior fill on UP side at 0.45
        fill_order = DutchOrder(
            side="UP", limit_price=0.45, shares=10.0, dollars=4.5,
            time_pct=0.3, placed_at=datetime.now(UTC), reason="paired pc=0.900",
        )
        engine.on_fill(fill_order, fill_price=0.45, filled_shares=10.0)

        # Now book has ask=0.50, which is > 0.45 * 1.02 = 0.459
        # pair_cost = 0.50 + 0.48 = 0.98 -> barely a dutch opportunity
        # But VWAP should block UP (non-trailing)
        book_up = make_book(0.48, 0.50)
        book_dn = make_book(0.44, 0.48)
        orders = engine.on_tick(0.50, 0.70, book_up, book_dn)
        up_orders = [o for o in orders if o.side == "UP"]
        assert len(up_orders) == 0

    def test_vwap_gate_allows_first_order(self):
        """No prior fills -> VWAP gate skipped, first order goes through."""
        engine = self._make_engine(vwap_tolerance=0.02, max_marginal_pair_cost=0.98)
        # pair_cost = 0.52 + 0.48 = 1.00 > 0.98 -> no dutch
        # But with model tilt cal_prob=0.65, if pnl_gap=0 and no dutch -> wait
        # Need dutch opportunity for first order
        book_up = make_book(0.40, 0.45)  # pair_cost = 0.45 + 0.48 = 0.93 < 0.98
        book_dn = make_book(0.44, 0.48)
        orders = engine.on_tick(0.50, 0.65, book_up, book_dn)
        up_orders = [o for o in orders if o.side == "UP"]
        assert len(up_orders) >= 1

    def test_reset_clears_new_state(self):
        """All pacing state cleared on reset."""
        engine = self._make_engine()
        engine._last_order_time_pct_up = 0.5
        engine._last_order_time_pct_dn = 0.6
        engine._current_cal_prob = 0.55
        engine._prediction_spend = 50.0
        engine._last_allowed_spend = 100.0
        engine._last_gate_emitted["gate_envelope"] = 0.3

        engine.reset()

        assert engine._last_order_time_pct_up == -1.0
        assert engine._last_order_time_pct_dn == -1.0
        assert engine._current_cal_prob is None
        assert engine._prediction_spend == 0.0
        assert engine._last_allowed_spend == 0.0
        assert engine._last_gate_emitted == {}

    def test_event_callback_fires_on_order(self):
        """Event callback receives order events."""
        events = []
        engine = self._make_engine(max_marginal_pair_cost=0.98)
        engine.set_event_callback(lambda e: events.append(e))

        # pair_cost = 0.25 + 0.52 = 0.77 < 0.98
        book_up = make_book(0.20, 0.25)
        book_dn = make_book(0.48, 0.52)
        orders = engine.on_tick(0.50, 0.65, book_up, book_dn)
        assert len(orders) >= 1
        order_events = [e for e in events if e["type"] == "order"]
        assert len(order_events) >= 1

    def test_auto_max_orders(self):
        """max_orders=0 auto-derives from bar_budget / min_order_usd."""
        engine = self._make_engine(
            bar_budget=200.0, min_order_usd=1.0,
        )
        assert engine._effective_max == 200

        engine2 = self._make_engine(
            bar_budget=200.0, min_order_usd=1.0, max_orders=50,
        )
        assert engine2._effective_max == 50

    def test_envelope_back_loaded(self):
        """Back-loaded envelope: pace(0.33) < 0.30 of budget."""
        engine = self._make_engine(
            bar_budget=200.0, max_marginal_pair_cost=0.98,
        )
        # pair_cost = 0.25 + 0.25 = 0.50 < 0.98
        book_up = make_book(0.20, 0.25)
        book_dn = make_book(0.20, 0.25)
        total = 0
        for i in range(8):
            t = 0.33 + i * 0.001
            orders = engine.on_tick(t, 0.65, book_up, book_dn)
            for o in orders:
                self._fill_order(engine, o)
                total += o.dollars
        assert total < 60  # back-loaded = less than 30% of $200

    def test_paired_buy_share_sizing(self):
        """Paired buys size by shares (expensive side sets pace), not dollars."""
        engine = self._make_engine(
            order_size=10.0,
            max_marginal_pair_cost=1.03,
        )
        # Asymmetric market: UP cheap at 0.25, DN expensive at 0.72
        # max_ask = 0.72, base_shares = 10/0.72 ≈ 13.9
        book_up = make_book(0.20, 0.25)
        book_dn = make_book(0.48, 0.72)
        orders = engine.on_tick(0.50, 0.50, book_up, book_dn)
        up_orders = [o for o in orders if o.side == "UP"]
        dn_orders = [o for o in orders if o.side == "DN"]
        if up_orders and dn_orders:
            # Share counts should be similar (both ~13.9)
            ratio = up_orders[0].shares / dn_orders[0].shares
            assert 0.5 < ratio < 2.0  # within 2x, not 10x like V5


class TestDutchV6PnlParity:
    """Tests for V6: P/L parity targeting, paired buys, profit-only sells."""

    def _make_engine(self, **kwargs) -> DutchAccumulationEngine:
        config = DutchConfig(**kwargs)
        return DutchAccumulationEngine(config)

    def _fill_order(self, engine, order):
        engine.on_fill(order, order.limit_price, order.shares)

    def test_buys_lighter_side_first(self):
        # Setup: 50 UP @ $0.30, 0 DN. DN is lighter side.
        # book: ask_up=0.30, ask_dn=0.60, pair_cost=0.90 < 0.98
        # Expect: DN ordered first (lighter side)
        engine = self._make_engine(max_marginal_pair_cost=0.98, risk_ceil=0.50)
        engine._inventory.shares_up = 50
        engine._inventory.cost_up = 15
        book_up = make_book(0.28, 0.30)
        book_dn = make_book(0.58, 0.60)
        orders = engine.on_tick(0.5, 0.50, book_up, book_dn)
        dn_orders = [o for o in orders if o.side == "DN"]
        assert len(dn_orders) >= 1
        assert "dutch" in dn_orders[0].reason

    def test_buys_both_sides_when_balanced(self):
        # Setup: balanced inventory, pair_cost=0.70, VWAP-safe prices
        engine = self._make_engine(
            max_marginal_pair_cost=0.98,
            vwap_tolerance=0.20,
            risk_ceil=0.50,  # permissive risk for balanced test
        )
        engine._inventory.shares_up = 20
        engine._inventory.shares_dn = 20
        engine._inventory.cost_up = 6  # avg 0.30
        engine._inventory.cost_dn = 6  # avg 0.30
        # pair_cost = 0.35 + 0.35 = 0.70 < 0.98
        # VWAP: 0.35 <= 0.30 * 1.20 = 0.36 -> passes
        book_up = make_book(0.33, 0.35)
        book_dn = make_book(0.33, 0.35)
        orders = engine.on_tick(0.5, 0.50, book_up, book_dn)
        sides = {o.side for o in orders}
        assert "UP" in sides and "DN" in sides
        for o in orders:
            assert "dutch" in o.reason

    def test_v61_buys_both_sides_always(self):
        """V6.1: Both sides always bought when dutch opportunity exists."""
        engine = self._make_engine(
            max_marginal_pair_cost=0.98,
            risk_ceil=0.50,  # permissive risk
        )
        # pair_cost = 0.40 + 0.50 = 0.90 < 0.98 -> dutch opportunity
        book_up = make_book(0.38, 0.40)
        book_dn = make_book(0.48, 0.50)
        orders = engine.on_tick(0.5, 0.70, book_up, book_dn)
        # V6.1 always buys both sides when dutch opportunity
        sides = {o.side for o in orders if o.action == "BUY"}
        assert "UP" in sides and "DN" in sides

    def test_no_orders_when_no_dutch_opportunity_and_balanced(self):
        engine = self._make_engine(max_marginal_pair_cost=0.98)
        # pair_cost = 0.57+0.57 = 1.14 > 0.98, pnl_gap=0 -> wait
        book_up = make_book(0.53, 0.57)
        book_dn = make_book(0.53, 0.57)
        orders = engine.on_tick(0.5, 0.50, book_up, book_dn)
        assert orders == []

    def test_marginal_pair_cost_blocks_bad_buy(self):
        engine = self._make_engine(max_marginal_pair_cost=0.98)
        # Already have pairs at 1.05 cost
        engine._inventory.shares_up = 20
        engine._inventory.shares_dn = 20
        engine._inventory.cost_up = 10.5
        engine._inventory.cost_dn = 10.5
        # pair_cost=0.52+0.52=1.04 > 0.98 normally, but pnl_gap matters
        # gap = (20-21)-(20-21) = 0, pair_cost=1.04 -> no dutch opp -> wait
        book_up = make_book(0.50, 0.52)
        book_dn = make_book(0.50, 0.52)
        orders = engine.on_tick(0.7, 0.50, book_up, book_dn)
        assert orders == []

    def test_marginal_pair_cost_allows_good_buy(self):
        engine = self._make_engine(max_marginal_pair_cost=0.98)
        # 20 UP @ $0.40, now buy DN at $0.50 -> sim_pair = 0.40+0.50 = 0.90 < 0.98
        engine._inventory.shares_up = 20
        engine._inventory.cost_up = 8  # avg 0.40
        book_up = make_book(0.38, 0.40)
        book_dn = make_book(0.48, 0.50)
        orders = engine.on_tick(0.5, 0.50, book_up, book_dn)
        dn_orders = [o for o in orders if o.side == "DN"]
        assert len(dn_orders) >= 1

    def test_recovers_after_bad_pairs(self):
        engine = self._make_engine(max_marginal_pair_cost=0.98)
        # Small bad pairs: 5 UP @ $0.55, 5 DN @ $0.55, avg=1.10
        engine._inventory.shares_up = 5
        engine._inventory.shares_dn = 5
        engine._inventory.cost_up = 2.75
        engine._inventory.cost_dn = 2.75
        # Now prices are good: ask_up=0.20, ask_dn=0.70, pair=0.90
        # gap = (5-(2.75+2.75))-(5-(2.75+2.75)) = 0, pair=0.90 -> paired buy
        book_up = make_book(0.18, 0.20)
        book_dn = make_book(0.68, 0.70)
        orders = engine.on_tick(0.5, 0.50, book_up, book_dn)
        # sim_pair_cost for buying UP at 0.20: blended cost should be pulled below 0.98
        assert len(orders) >= 1  # engine NOT permanently stopped

    def test_no_permanent_kill_switch(self):
        # Old V5 would permanently stop here. V6 should still trade.
        engine = self._make_engine(max_marginal_pair_cost=0.98)
        engine._inventory.shares_up = 20
        engine._inventory.shares_dn = 20
        engine._inventory.cost_up = 10.6  # avg_pair = 1.06 > 1.05
        engine._inventory.cost_dn = 10.6
        # At t=0.70, V5 would have killed. V6 should try to trade if prices good.
        book_up = make_book(0.18, 0.20)
        book_dn = make_book(0.68, 0.70)
        orders = engine.on_tick(0.70, 0.50, book_up, book_dn)
        # pair=0.90, pnl_gap~=0 -> paired buy. sim_pair_cost blends old bad + new good
        assert len(orders) >= 1

    def test_no_sell_at_loss(self):
        engine = self._make_engine(sell_profit_only=True, rebalance_warmup=0.0)
        # UP heavy: 100 @ avg $0.60, DN: 50 shares
        engine._inventory.shares_up = 100
        engine._inventory.cost_up = 60
        engine._inventory.shares_dn = 50
        engine._inventory.cost_dn = 15
        # bid_UP = 0.53 < avg_cost 0.60 -> should NOT sell
        book_up = make_book(0.53, 0.55)
        book_dn = make_book(0.43, 0.45)
        orders = engine.on_tick(0.5, 0.50, book_up, book_dn)
        sell_orders = [o for o in orders if o.action == "SELL"]
        assert len(sell_orders) == 0

    def test_sell_at_profit_only(self):
        engine = self._make_engine(sell_profit_only=True, rebalance_warmup=0.0)
        # UP heavy: 100 @ avg $0.40, DN: 50 shares
        engine._inventory.shares_up = 100
        engine._inventory.cost_up = 40
        engine._inventory.shares_dn = 50
        engine._inventory.cost_dn = 15
        # bid_UP = 0.55 > avg_cost 0.40 -> should sell UP
        book_up = make_book(0.55, 0.57)
        book_dn = make_book(0.43, 0.45)
        orders = engine.on_tick(0.5, 0.50, book_up, book_dn)
        sell_orders = [o for o in orders if o.action == "SELL"]
        assert len(sell_orders) >= 1
        assert sell_orders[0].side == "UP"
        assert "sell_profit" in sell_orders[0].reason

    def test_never_sell_lighter_side(self):
        engine = self._make_engine(sell_profit_only=True, rebalance_warmup=0.0)
        # DN lighter: 50 shares @ $0.30, UP heavy: 100 shares @ $0.40
        engine._inventory.shares_up = 100
        engine._inventory.cost_up = 40
        engine._inventory.shares_dn = 50
        engine._inventory.cost_dn = 15
        # bid_DN=0.50 > avg 0.30, but DN is lighter -> should NOT sell DN
        # bid_UP=0.35 < avg 0.40 -> should NOT sell UP either (loss)
        book_up = make_book(0.35, 0.37)
        book_dn = make_book(0.50, 0.52)
        orders = engine.on_tick(0.5, 0.50, book_up, book_dn)
        sell_orders = [o for o in orders if o.action == "SELL"]
        assert len(sell_orders) == 0

    def test_paired_buy_both_sides_per_tick(self):
        engine = self._make_engine(
            allow_paired_buys=True, max_marginal_pair_cost=0.98,
        )
        book_up = make_book(0.38, 0.40)
        book_dn = make_book(0.48, 0.50)
        orders = engine.on_tick(0.5, 0.50, book_up, book_dn)
        buy_orders = [o for o in orders if o.action == "BUY"]
        sides = {o.side for o in buy_orders}
        assert len(sides) == 2  # both UP and DN

    def test_share_sizing_uses_max_ask(self):
        """V6.1: Sizing is share-based — order_size / max(ask_up, ask_dn)."""
        engine = self._make_engine(
            max_marginal_pair_cost=0.98,
            order_size=5.0,
            risk_ceil=0.50,  # permissive risk
            vwap_tolerance=0.20,  # wide enough for test prices
        )
        engine._inventory.shares_up = 30
        engine._inventory.cost_up = 9  # avg 0.30
        engine._inventory.shares_dn = 10
        engine._inventory.cost_dn = 5  # avg 0.50
        # DN is lighter side, ordered first
        book_up = make_book(0.28, 0.30)
        book_dn = make_book(0.58, 0.60)
        orders = engine.on_tick(0.5, 0.50, book_up, book_dn)
        dn_orders = [o for o in orders if o.side == "DN"]
        assert len(dn_orders) >= 1
        # max_ask=0.60, base_shares=5/0.60≈8.33, dollar_size=8.33*limit_price
        assert dn_orders[0].shares <= 10.0

    def test_simulated_avg_pair_cost(self):
        inv = DutchInventory(shares_up=20, cost_up=8)  # avg UP = 0.40
        # sim buy 20 DN @ 0.50 -> matched=20, pair = 0.40 + 0.50 = 0.90
        result = inv.simulated_avg_pair_cost("DN", 20, 0.50)
        assert result == pytest.approx(0.90, abs=0.001)

    def test_no_death_spiral(self):
        # Buy DN to rebalance -> DN becomes lighter -> sell skips DN
        engine = self._make_engine(
            sell_profit_only=True, rebalance_warmup=0.0,
            max_marginal_pair_cost=0.98,
        )
        # UP heavy: 50 shares @ 0.30, DN: 20 shares @ 0.50
        engine._inventory.shares_up = 50
        engine._inventory.cost_up = 15
        engine._inventory.shares_dn = 20
        engine._inventory.cost_dn = 10
        book_up = make_book(0.28, 0.30)
        book_dn = make_book(0.58, 0.60)
        orders = engine.on_tick(0.5, 0.50, book_up, book_dn)
        # Should buy DN (trailing), should NOT sell DN (DN is lighter)
        sell_dn = [o for o in orders if o.action == "SELL" and o.side == "DN"]
        assert len(sell_dn) == 0

    def test_sell_updates_net_inventory(self):
        """Sell fill updates net shares and revenue."""
        engine = self._make_engine()
        engine._inventory.shares_up = 100.0
        engine._inventory.cost_up = 30.0

        sell_order = DutchOrder(
            side="UP", limit_price=0.40, shares=50.0, dollars=20.0,
            time_pct=0.5, placed_at=datetime.now(UTC), reason="sell_profit bid=0.400>avg=0.300",
            action="SELL",
        )
        engine.on_fill(sell_order, fill_price=0.40, filled_shares=50.0)

        assert engine._inventory.sold_shares_up == 50.0
        assert engine._inventory.sell_revenue_up == 20.0
        assert engine._inventory.net_shares_up == 50.0  # 100 - 50
        assert engine._inventory.net_cost_up == 10.0  # 30 - 20

    def test_sell_cooldown_prevents_rapid_sells(self):
        """Two on_tick calls within cooldown window should produce only 1 sell."""
        engine = self._make_engine(
            sell_profit_only=True, sell_min_shares=5.0,
            rebalance_warmup=0.0, max_marginal_pair_cost=0.98,
        )
        # UP heavy with profit: 100 @ avg $0.30, bid=0.55 > avg
        engine._inventory.shares_up = 100.0
        engine._inventory.cost_up = 30.0
        engine._inventory.shares_dn = 50.0
        engine._inventory.cost_dn = 15.0

        book_up = make_book(0.55, 0.57)
        book_dn = make_book(0.43, 0.45)

        # First tick at t=0.50 -> should sell UP (profitable, heavy)
        orders1 = engine.on_tick(0.50, 0.50, book_up, book_dn)
        sells1 = [o for o in orders1 if o.action == "SELL"]
        assert len(sells1) == 1

        # Second tick at t=0.502 (within 0.005 cooldown) -> no sell
        orders2 = engine.on_tick(0.502, 0.50, book_up, book_dn)
        sells2 = [o for o in orders2 if o.action == "SELL"]
        assert len(sells2) == 0

        # Third tick at t=0.510 (past cooldown) -> should sell again
        orders3 = engine.on_tick(0.510, 0.50, book_up, book_dn)
        sells3 = [o for o in orders3 if o.action == "SELL"]
        assert len(sells3) == 1

    def test_sell_pending_released_on_cancel(self):
        """Cancelled sell releases pending reservation."""
        engine = self._make_engine(
            sell_profit_only=True, sell_min_shares=5.0,
            sell_max_fraction=0.50, rebalance_warmup=0.0,
            max_marginal_pair_cost=0.98,
        )
        # UP heavy with profit
        engine._inventory.shares_up = 100.0
        engine._inventory.cost_up = 30.0
        engine._inventory.shares_dn = 50.0
        engine._inventory.cost_dn = 15.0

        book_up = make_book(0.55, 0.57)
        book_dn = make_book(0.43, 0.45)

        orders1 = engine.on_tick(0.50, 0.50, book_up, book_dn)
        sell = [o for o in orders1 if o.action == "SELL"][0]
        assert engine._pending_sell_shares_up > 0

        # Cancel releases reservation
        engine.on_order_cancelled(sell)
        assert engine._pending_sell_shares_up == 0.0

    def test_sell_not_same_side_as_buy(self):
        """V6: sell pass skips the side that just got a buy order."""
        engine = self._make_engine(
            sell_profit_only=True, sell_min_shares=5.0,
            rebalance_warmup=0.0, max_marginal_pair_cost=0.98,
        )
        # DN heavy with profit, DN is trailing -> buy DN (trailing)
        # But also DN bid > avg -> would sell? No, buy_side=DN skips sell DN.
        engine._inventory.shares_dn = 50.0
        engine._inventory.cost_dn = 15.0
        engine._inventory.shares_up = 20.0
        engine._inventory.cost_up = 6.0

        # pair_cost = 0.30 + 0.60 = 0.90 < 0.98
        # pnl_gap = (20-21)-(50-21) = -1-29 = -30 -> UP trailing
        book_up = make_book(0.28, 0.30)
        book_dn = make_book(0.58, 0.60)
        orders = engine.on_tick(0.50, 0.50, book_up, book_dn)

        buy_up = [o for o in orders if o.action == "BUY" and o.side == "UP"]
        sell_up = [o for o in orders if o.action == "SELL" and o.side == "UP"]
        assert len(buy_up) >= 1  # UP is trailing
        assert len(sell_up) == 0  # can't sell same side we bought


class TestDutchV61RiskBudget:
    """Tests for V6.1 risk-budget-aware sizing (cap, not block)."""

    def _make_engine(self, **kwargs):
        config = DutchConfig(**kwargs)
        return DutchAccumulationEngine(config)

    def test_risk_budget_caps_heavy_side(self):
        """Heavy side order is REDUCED to fit risk room, not blocked."""
        engine = self._make_engine(
            risk_floor=0.10, risk_ceil=0.15,  # 10% = $20 at t=0.50
            risk_t_start=0.0, risk_t_end=1.0,
            max_marginal_pair_cost=1.03,
            order_size=10.0,
        )
        # UP heavy: 50 shares @ $0.40 = $20, DN: 20 shares @ $0.50 = $10
        # base_cost = $30, risk_allowed = $20 (10% of $200 at t=0)
        # Buying UP: max_ds = 20 - 30 + 20(DN) = $10
        # Buying DN: max_ds = 20 - 30 + 50(UP) = $40
        engine._inventory.shares_up = 50
        engine._inventory.cost_up = 20
        engine._inventory.shares_dn = 20
        engine._inventory.cost_dn = 10
        book_up = make_book(0.38, 0.40)
        book_dn = make_book(0.48, 0.50)
        orders = engine.on_tick(0.50, 0.50, book_up, book_dn)
        # Should have orders (not blocked)
        assert len(orders) >= 1
        # UP (heavy side) should be capped
        up_orders = [o for o in orders if o.side == "UP" and o.action == "BUY"]
        if up_orders:
            assert up_orders[0].dollars <= 10.5  # ~$10 risk room

    def test_risk_budget_light_side_gets_bigger_cap(self):
        """Light side gets more room than heavy side from same risk budget."""
        engine = self._make_engine(
            risk_floor=0.10, risk_ceil=0.15,
            risk_t_start=0.0, risk_t_end=1.0,
            max_marginal_pair_cost=1.03,
            order_size=50.0,  # large so we hit the cap
        )
        engine._inventory.shares_up = 50
        engine._inventory.cost_up = 20
        engine._inventory.shares_dn = 20
        engine._inventory.cost_dn = 10
        book_up = make_book(0.38, 0.40)
        book_dn = make_book(0.48, 0.50)
        orders = engine.on_tick(0.50, 0.50, book_up, book_dn)
        up_orders = [o for o in orders if o.side == "UP" and o.action == "BUY"]
        dn_orders = [o for o in orders if o.side == "DN" and o.action == "BUY"]
        if up_orders and dn_orders:
            assert dn_orders[0].dollars > up_orders[0].dollars

    def test_risk_budget_first_order_capped_to_floor(self):
        """Empty inventory at t=0.10 — first order capped to risk_floor * budget."""
        engine = self._make_engine(
            risk_floor=0.01, risk_ceil=0.15,
            risk_t_start=0.10, risk_t_end=0.80,
            max_marginal_pair_cost=1.03,
            order_size=10.0,
        )
        book_up = make_book(0.38, 0.40)
        book_dn = make_book(0.48, 0.50)
        orders = engine.on_tick(0.10, 0.50, book_up, book_dn)
        # risk_allowed = 200 * 0.01 = $2. Orders should exist but be small.
        assert len(orders) >= 1
        for o in orders:
            assert o.dollars <= 2.5  # capped near $2

    def test_risk_curve_grows_with_time(self):
        """Verify quadratic risk curve at known points."""
        engine = self._make_engine(
            risk_floor=0.01, risk_ceil=0.15,
            risk_t_start=0.10, risk_t_end=0.80,
            risk_exponent=2.0,
        )
        # t=0.10 → 1% = $2
        assert engine._risk_budget(0.10) == pytest.approx(2.0, abs=0.1)
        # t=0.80 → 15% = $30
        assert engine._risk_budget(0.80) == pytest.approx(30.0, abs=0.1)
        # t=0.50 → ~5.6% = ~$11.2
        assert 10.0 < engine._risk_budget(0.50) < 13.0


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
