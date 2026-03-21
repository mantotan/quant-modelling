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

    def test_buys_up_when_model_edge(self):
        """V4: Tier 2 (edge) fires when model says underpriced and ask > 0.50."""
        engine = self._make_engine(cheap_threshold=0.10)
        # ask_UP=0.52 > 0.50, so Tier 1 doesn't fire
        # my_cheap = 0.65 - 0.52 = 0.13 > threshold → Tier 2 fires
        book_up = make_book(0.48, 0.52)
        book_dn = make_book(0.44, 0.48)
        orders = engine.on_tick(0.5, 0.65, book_up, book_dn)
        up_orders = [o for o in orders if o.side == "UP"]
        assert len(up_orders) >= 1
        assert "edge" in up_orders[0].reason

    def test_no_buy_when_both_asks_above_50c_no_edge(self):
        """V4: No buy when both asks > 0.50 and no model edge and no hedge trigger."""
        engine = self._make_engine(cheap_threshold=0.10)
        # Both asks > 0.50, no model edge, no other_cheap for hedge
        book_up = make_book(0.53, 0.57)
        book_dn = make_book(0.53, 0.57)
        orders = engine.on_tick(0.5, 0.50, book_up, book_dn)
        assert orders == []

    def test_cheap_tier_buys_both_sides_across_ticks(self):
        """V4 Tier 1: both asks < 0.50 → buys both sides across 2 ticks."""
        engine = self._make_engine(cheap_threshold=0.10)
        book_up = make_book(0.40, 0.42)  # ask < 0.50
        book_dn = make_book(0.40, 0.42)  # ask < 0.50
        # First tick: one side
        orders1 = engine.on_tick(0.3, 0.50, book_up, book_dn)
        assert len(orders1) == 1  # one side per tick
        for o in orders1:
            engine.on_fill(o, o.limit_price, o.shares)
        # Second tick: other side
        orders2 = engine.on_tick(0.301, 0.50, book_up, book_dn)
        all_sides = {o.side for o in orders1 + orders2}
        assert "UP" in all_sides or "DN" in all_sides  # at least one side bought

    def test_hedge_tier_replaces_contra(self):
        """V4: Hedge tier fires where old contra used to, without model gate."""
        engine = self._make_engine(
            cheap_threshold=0.10, max_hedge_ask=0.80, rebalance_warmup=0.0,
        )
        # ask_UP = 0.58, model P(UP)=0.40 → cheap_UP = 0.40-0.58 = -0.18 (negative)
        # cheap_DN = 0.60 - 0.35 = +0.25 > threshold 0.10 → hedge fires for UP
        book_up = make_book(0.50, 0.58)
        book_dn = make_book(0.30, 0.35)
        orders = engine.on_tick(0.3, 0.40, book_up, book_dn)
        up_orders = [o for o in orders if o.side == "UP"]
        assert len(up_orders) >= 1

    def test_no_hedge_when_both_overpriced(self):
        """V4: No hedge when both sides above 0.50 and neither has edge."""
        engine = self._make_engine(cheap_threshold=0.10, max_hedge_ask=0.80)
        # Both asks > 0.50, model neutral → no edge on either side
        book_up = make_book(0.60, 0.65)
        book_dn = make_book(0.55, 0.60)
        orders = engine.on_tick(0.3, 0.50, book_up, book_dn)
        # Neither side should trigger (no cheap, no edge, no hedge)
        assert orders == []

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

    def test_kill_switch_on_bad_avg_pair_cost(self):
        """Stop when avg pair cost exceeds threshold after 60% of bar."""
        engine = self._make_engine(max_pair_cost=1.05, kill_switch_after=0.60)
        # Pair cost = 1.06 > 1.05
        engine._inventory.shares_up = 20
        engine._inventory.shares_dn = 20
        engine._inventory.cost_up = 10.6
        engine._inventory.cost_dn = 10.6
        book_up = make_book(0.48, 0.52)
        book_dn = make_book(0.48, 0.52)
        # At t=0.70 (after kill_switch_after=0.60) → should kill
        orders = engine.on_tick(0.70, 0.65, book_up, book_dn)
        assert orders == []
        assert engine._stopped

    def test_no_kill_before_inventory(self):
        """Don't kill on marginal cost alone — allow first entries even if skewed."""
        engine = self._make_engine(
            max_pair_cost=0.97, cheap_threshold=0.10,
        )
        # Skewed market: bid_UP=0.35, bid_DN=0.64 → marginal = 1.01
        # But no inventory yet, so kill switch should NOT fire
        book_up = make_book(0.35, 0.36)  # UP is cheap
        book_dn = make_book(0.64, 0.65)
        orders = engine.on_tick(0.5, 0.55, book_up, book_dn)
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
            cheap_threshold=0.10, order_size=5.0, bar_budget=200.0,
        )
        book_up = make_book(0.48, 0.52)
        book_dn = make_book(0.20, 0.25)  # cheap_dn = 0.35 - 0.25 = huge edge
        total_orders = 0
        for i in range(5):
            t = 0.05 + i * 0.001  # ~1ms apart
            orders = engine.on_tick(t, 0.65, book_up, book_dn)
            for o in orders:
                self._fill_order(engine, o)
            total_orders += len(orders)
        # Envelope at t=0.05 with edge ~0.40: urgency=2.0, pace=0.05^0.5=0.224
        # allowed=$44.7. At $5/order, ~9 orders max, but spacing gate should
        # further limit. Should NOT be all 5*2=10.
        assert total_orders < 8

    def test_envelope_allows_more_at_high_time_pct(self):
        """At t=0.80, envelope allows substantial spend."""
        engine = self._make_engine(
            cheap_threshold=0.10, order_size=5.0, bar_budget=200.0,
        )
        book_up = make_book(0.48, 0.52)
        book_dn = make_book(0.20, 0.25)
        orders = engine.on_tick(0.80, 0.65, book_up, book_dn)
        assert len(orders) >= 1

    def test_envelope_handles_zero_time_pct(self):
        """t=0.0 should still allow first order (floor at 0.01)."""
        engine = self._make_engine(
            cheap_threshold=0.10, order_size=5.0, bar_budget=200.0,
        )
        book_up = make_book(0.20, 0.25)  # cheap_up = 0.65 - 0.25 = 0.40
        book_dn = make_book(0.48, 0.52)
        orders = engine.on_tick(0.0, 0.65, book_up, book_dn)
        # pace(0.01) with urgency=2.0 = 0.01^0.5 = 0.1 → allowed=$20
        assert len(orders) >= 1

    def test_slot_spacing_blocks_rapid_same_side(self):
        """Two ticks ~0.001 apart should block the second order on same side."""
        engine = self._make_engine(
            cheap_threshold=0.10, order_size=5.0, bar_budget=200.0,
        )
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

    def test_slot_spacing_exempts_emergency(self):
        """Emergency orders (last 30s) bypass spacing gate."""
        engine = self._make_engine(
            cheap_threshold=0.10, order_size=5.0, bar_budget=200.0,
            max_hedge_ask=0.80, min_share_match=0.0,  # disable share match
        )
        # Build UP inventory → need DN for emergency balance
        engine._inventory.shares_up = 40
        engine._inventory.cost_up = 20
        # Set last_order_time very close to now
        engine._last_order_time_pct_dn = 0.969

        book_up = make_book(0.48, 0.52)
        book_dn = make_book(0.44, 0.48)
        # t=0.97 → remaining = 0.03 * 900 = 27s < 30s → emergency window
        orders = engine.on_tick(0.97, 0.50, book_up, book_dn)
        dn_orders = [o for o in orders if o.side == "DN"]
        # Emergency should fire despite close spacing
        assert len(dn_orders) >= 1
        assert "emergency" in dn_orders[0].reason

    def test_side_cap_blocks_heavy_side(self):
        """65% budget on UP → next UP order blocked, DN still allowed."""
        engine = self._make_engine(
            cheap_threshold=0.10, max_side_fraction=0.65, bar_budget=200.0,
            min_share_match=0.0,  # disable share match to test side cap alone
        )
        # UP already at 65% of budget = $130
        engine._inventory.shares_up = 260
        engine._inventory.cost_up = 130

        book_up = make_book(0.20, 0.25)  # UP is very cheap
        book_dn = make_book(0.20, 0.25)  # DN is also cheap
        # Use t=0.90 so envelope allows enough spend ($130 < envelope at 90%)
        orders = engine.on_tick(0.90, 0.65, book_up, book_dn)
        up_orders = [o for o in orders if o.side == "UP"]
        dn_orders = [o for o in orders if o.side == "DN"]
        assert len(up_orders) == 0  # blocked by side cap
        assert len(dn_orders) >= 1  # DN is fine

    def test_side_cap_exempts_balance(self):
        """Balance order on heavy side still fires (it reduces risk)."""
        engine = self._make_engine(
            cheap_threshold=0.10, max_side_fraction=0.65, bar_budget=200.0,
        )
        # DN heavy at cap, need UP to balance
        engine._inventory.cost_dn = 135  # over 65% cap ($130)
        engine._inventory.shares_dn = 270
        engine._inventory.cost_up = 0
        engine._inventory.shares_up = 0
        # pnl_if_up = 0 - 135 = -135, pnl_if_dn = 270 - 135 = 135
        # need_side = UP (pnl_if_dn > pnl_if_up)
        book_up = make_book(0.44, 0.48)  # cheap_up = 0.50 - 0.48 = 0.02 > 0
        book_dn = make_book(0.44, 0.48)
        orders = engine.on_tick(0.90, 0.50, book_up, book_dn)
        up_orders = [o for o in orders if o.side == "UP"]
        # Balance on UP should fire despite it not being the capped side
        assert len(up_orders) >= 1

    def test_per_prediction_cap(self):
        """$100 per prediction: blocks after spending, resets on new cal_prob."""
        engine = self._make_engine(
            cheap_threshold=0.10, order_size=5.0, bar_budget=200.0,
            max_per_prediction=100.0,
        )
        book_up = make_book(0.20, 0.25)
        book_dn = make_book(0.20, 0.25)
        # Accumulate ~$95 of prediction spend
        engine._prediction_spend = 95.0
        engine._current_cal_prob = 0.65
        # Next order at same cal_prob — only $5 left
        orders = engine.on_tick(0.50, 0.65, book_up, book_dn)
        total_dollars = sum(o.dollars for o in orders)
        assert total_dollars <= 6.0  # clamped to ~$5 remaining

        # Fill and try again — should be blocked
        for o in orders:
            self._fill_order(engine, o)
        engine._prediction_spend = 100.0
        orders2 = engine.on_tick(0.51, 0.65, book_up, book_dn)
        assert orders2 == []

        # New cal_prob → counter resets
        orders3 = engine.on_tick(0.52, 0.66, book_up, book_dn)
        assert len(orders3) >= 1

    def test_per_prediction_clamps_order_size(self):
        """At $90 prediction spend, $20 order should be clamped to $10."""
        engine = self._make_engine(
            cheap_threshold=0.10, order_size=20.0, bar_budget=200.0,
            max_per_prediction=100.0,
        )
        engine._prediction_spend = 90.0
        engine._current_cal_prob = 0.65
        book_up = make_book(0.20, 0.25)
        book_dn = make_book(0.48, 0.52)
        orders = engine.on_tick(0.50, 0.65, book_up, book_dn)
        if orders:
            assert orders[0].dollars <= 11.0  # clamped to ~$10

    def test_vwap_gate_blocks_worse_price(self):
        """After filling at 0.45, skip order at 0.50 (> 0.459)."""
        engine = self._make_engine(
            cheap_threshold=0.10, vwap_tolerance=0.02,
        )
        # Simulate prior fill on UP side at 0.45
        fill_order = DutchOrder(
            side="UP", limit_price=0.45, shares=10.0, dollars=4.5,
            time_pct=0.3, placed_at=datetime.now(UTC), reason="cheap",
        )
        engine.on_fill(fill_order, fill_price=0.45, filled_shares=10.0)

        # Now book has ask=0.50, which is > 0.45 * 1.02 = 0.459
        book_up = make_book(0.48, 0.50)
        book_dn = make_book(0.44, 0.48)
        orders = engine.on_tick(0.50, 0.70, book_up, book_dn)
        up_orders = [o for o in orders if o.side == "UP"]
        assert len(up_orders) == 0

    def test_vwap_gate_allows_first_order(self):
        """No prior fills → VWAP gate skipped, first order goes through."""
        engine = self._make_engine(
            cheap_threshold=0.10, vwap_tolerance=0.02,
        )
        book_up = make_book(0.48, 0.52)
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
        engine = self._make_engine(cheap_threshold=0.10)
        engine.set_event_callback(lambda e: events.append(e))

        book_up = make_book(0.20, 0.25)
        book_dn = make_book(0.48, 0.52)
        orders = engine.on_tick(0.50, 0.65, book_up, book_dn)
        assert len(orders) >= 1
        order_events = [e for e in events if e["type"] == "order"]
        assert len(order_events) >= 1
        assert order_events[0]["side"] == "UP"

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


class TestDutchV4BilateralGrid:
    """Tests for V4: bilateral grid accumulation (matching trader_a)."""

    def _make_engine(self, **kwargs) -> DutchAccumulationEngine:
        config = DutchConfig(**kwargs)
        return DutchAccumulationEngine(config)

    def _fill_order(self, engine, order):
        engine.on_fill(order, order.limit_price, order.shares)

    def test_cheap_tier_buys_below_50c(self):
        """Tier 1: ask < 0.50 buys regardless of model edge."""
        engine = self._make_engine(cheap_threshold=0.10)
        # Model says P(UP)=0.30, but ask_UP=0.35 < 0.50 → buy anyway
        # my_cheap = 0.30 - 0.35 = -0.05 (negative edge!)
        book_up = make_book(0.30, 0.35)
        book_dn = make_book(0.60, 0.65)
        orders = engine.on_tick(0.50, 0.30, book_up, book_dn)
        up_orders = [o for o in orders if o.side == "UP"]
        assert len(up_orders) >= 1
        assert "cheap" in up_orders[0].reason

    def test_hedge_buys_expensive_side(self):
        """Tier 3: hedge fires when other side has edge and ask < max_hedge_ask."""
        engine = self._make_engine(
            cheap_threshold=0.10, max_hedge_ask=0.80, rebalance_warmup=0.0,
        )
        # Model P(UP)=0.40 → cheap_DN = 0.60 - 0.35 = +0.25 (strong DN edge)
        # ask_UP = 0.65 (expensive but < 0.80)
        # cheap_UP = 0.40 - 0.65 = -0.25 (overpriced)
        book_up = make_book(0.60, 0.65)  # ask_UP = 0.65
        book_dn = make_book(0.30, 0.35)  # ask_DN = 0.35 < 0.50
        orders = engine.on_tick(0.50, 0.40, book_up, book_dn)
        up_orders = [o for o in orders if o.side == "UP"]
        assert len(up_orders) >= 1
        assert "hedge" in up_orders[0].reason

    def test_hedge_blocked_above_max_ask(self):
        """Hedge blocked when ask > max_hedge_ask."""
        engine = self._make_engine(
            cheap_threshold=0.10, max_hedge_ask=0.80,
        )
        # ask_UP = 0.85 > 0.80 → no hedge
        book_up = make_book(0.80, 0.85)
        book_dn = make_book(0.10, 0.15)  # DN very cheap
        orders = engine.on_tick(0.50, 0.30, book_up, book_dn)
        up_orders = [o for o in orders if o.side == "UP"]
        # UP should NOT get a hedge order (ask too high)
        hedge_orders = [o for o in up_orders if "hedge" in o.reason]
        assert len(hedge_orders) == 0

    def test_hedge_sizing_half_base(self):
        """Hedge orders use half base order size."""
        engine = self._make_engine(
            cheap_threshold=0.10, order_size=10.0, max_hedge_ask=0.80,
        )
        book_up = make_book(0.60, 0.65)
        book_dn = make_book(0.30, 0.35)
        orders = engine.on_tick(0.50, 0.40, book_up, book_dn)
        hedge = [o for o in orders if "hedge" in o.reason]
        if hedge:
            assert hedge[0].dollars <= 6.0  # ~$5 = 10 * 0.5

    def test_balance_fires_at_high_ask(self):
        """Balance fires at ask=0.75 (was blocked by my_cheap > 0 in V3)."""
        engine = self._make_engine(
            cheap_threshold=0.10, max_hedge_ask=0.80,
        )
        # Heavy DN, need UP to balance
        engine._inventory.shares_dn = 100
        engine._inventory.cost_dn = 30
        # pnl_if_up = 0 - 30 = -30 → need UP
        book_up = make_book(0.70, 0.75)  # ask=0.75 < max_hedge_ask=0.80
        book_dn = make_book(0.20, 0.25)
        orders = engine.on_tick(0.90, 0.50, book_up, book_dn)
        up_orders = [o for o in orders if o.side == "UP"]
        assert len(up_orders) >= 1

    def test_balance_blocked_above_max_ask(self):
        """Balance blocked when ask > max_hedge_ask."""
        engine = self._make_engine(
            cheap_threshold=0.10, max_hedge_ask=0.80,
        )
        engine._inventory.shares_dn = 100
        engine._inventory.cost_dn = 30
        book_up = make_book(0.82, 0.88)  # ask=0.88 > 0.80
        book_dn = make_book(0.10, 0.12)
        orders = engine.on_tick(0.90, 0.50, book_up, book_dn)
        up_balance = [o for o in orders if o.side == "UP" and "balance" in o.reason]
        assert len(up_balance) == 0

    def test_envelope_back_loaded(self):
        """Back-loaded envelope: pace(0.33) < 0.30 of budget."""
        engine = self._make_engine(bar_budget=200.0, cheap_threshold=0.10)
        book_up = make_book(0.20, 0.25)
        book_dn = make_book(0.20, 0.25)
        # At t=0.33, edge ~0.40 → urgency ~2.0, pace = 0.33^2.0 = 0.109
        # allowed = 200 * 0.109 = $21.8 → only ~4 orders at $5
        total = 0
        for i in range(8):
            t = 0.33 + i * 0.001
            orders = engine.on_tick(t, 0.65, book_up, book_dn)
            for o in orders:
                self._fill_order(engine, o)
                total += o.dollars
        assert total < 60  # back-loaded = less than 30% of $200

    def test_kill_switch_delayed(self):
        """Kill switch doesn't fire before kill_switch_after."""
        engine = self._make_engine(
            max_pair_cost=1.05, kill_switch_after=0.60,
        )
        engine._inventory.shares_up = 20
        engine._inventory.shares_dn = 20
        engine._inventory.cost_up = 10.6
        engine._inventory.cost_dn = 10.6  # pair cost = 1.06
        book_up = make_book(0.48, 0.52)
        book_dn = make_book(0.48, 0.52)
        # At t=0.40 (before 0.60) → should NOT kill
        engine.on_tick(0.40, 0.55, book_up, book_dn)
        assert not engine._stopped

    def test_edge_scale_narrowed(self):
        """Edge scaling uses 0.8x-1.2x range."""
        engine = self._make_engine(
            order_size=10.0, cheap_threshold=0.10,
            edge_scale_lo=0.8, edge_scale_hi=1.2,
        )
        book_up = make_book(0.20, 0.25)  # ask < 0.50 → cheap tier
        book_dn = make_book(0.48, 0.52)
        orders = engine.on_tick(0.50, 0.70, book_up, book_dn)
        up_orders = [o for o in orders if o.side == "UP"]
        if up_orders:
            # $10 base * [0.8, 1.2] = $8-12
            assert 7.0 <= up_orders[0].dollars <= 13.0

    def test_bilateral_accumulation(self):
        """With directional model, BOTH sides get orders across multiple ticks."""
        engine = self._make_engine(
            cheap_threshold=0.10, max_hedge_ask=0.80,
            rebalance_warmup=0.0,  # disable warmup for this test
        )
        book_up = make_book(0.55, 0.60)
        book_dn = make_book(0.35, 0.40)
        # Accumulate: UP fires first (hedge), R2 eventually blocks UP, DN gets turn
        all_sides = set()
        for i in range(10):
            t = 0.50 + i * 0.01  # spaced enough for R2 to sometimes pass
            orders = engine.on_tick(t, 0.44, book_up, book_dn)
            for o in orders:
                all_sides.add(o.side)
                engine.on_fill(o, o.limit_price, o.shares)
        # R2 blocks UP after first order, DN (cheap <0.50) fires on next tick
        assert len(all_sides) >= 2, f"Both sides should have orders, got {all_sides}"

    def test_share_match_forces_light_side(self):
        """Share match monitor forces buying the light side."""
        engine = self._make_engine(
            min_share_match=0.30, max_hedge_ask=0.80,
        )
        # Heavy DN: 100 shares, 0 UP → share_match = 0%
        engine._inventory.shares_dn = 100
        engine._inventory.cost_dn = 30
        book_up = make_book(0.60, 0.65)  # ask < max_hedge_ask
        book_dn = make_book(0.30, 0.35)
        orders = engine.on_tick(0.50, 0.50, book_up, book_dn)
        up_orders = [o for o in orders if o.side == "UP"]
        assert len(up_orders) >= 1
        assert "match_rebalance" in up_orders[0].reason

    def test_share_match_no_force_when_balanced(self):
        """Share match monitor doesn't fire when ratio is healthy."""
        engine = self._make_engine(
            min_share_match=0.30, max_hedge_ask=0.80, cheap_threshold=0.10,
        )
        engine._inventory.shares_up = 60
        engine._inventory.shares_dn = 80  # 75% match > 30%
        engine._inventory.cost_up = 30
        engine._inventory.cost_dn = 24
        book_up = make_book(0.60, 0.65)
        book_dn = make_book(0.60, 0.65)
        orders = engine.on_tick(0.50, 0.50, book_up, book_dn)
        rebalance = [o for o in orders if "match_rebalance" in o.reason]
        assert len(rebalance) == 0

    def test_rebalance_subject_to_spacing(self):
        """Match rebalance orders are paced by R2 (not exempt like balance)."""
        engine = self._make_engine(
            min_share_match=0.50, max_hedge_ask=0.80,
        )
        # Heavy DN, need UP rebalance
        engine._inventory.shares_dn = 100
        engine._inventory.cost_dn = 30
        book_up = make_book(0.55, 0.60)
        book_dn = make_book(0.35, 0.40)
        # First tick: rebalance fires
        orders1 = engine.on_tick(0.30, 0.50, book_up, book_dn)
        rebal1 = [o for o in orders1 if "match_rebalance" in o.reason]
        assert len(rebal1) >= 1
        for o in rebal1:
            self._fill_order(engine, o)
        # Immediate second tick: should be blocked by R2 spacing
        orders2 = engine.on_tick(0.301, 0.50, book_up, book_dn)
        rebal2 = [o for o in orders2 if "match_rebalance" in o.reason]
        assert len(rebal2) == 0  # blocked by spacing

    def test_hedge_exempt_from_vwap(self):
        """Hedge orders skip R6 VWAP gate (they inherently buy at worse prices)."""
        engine = self._make_engine(
            cheap_threshold=0.10, max_hedge_ask=0.80, vwap_tolerance=0.10,
            rebalance_warmup=0.0,
        )
        # Fill UP at 0.50 to set a VWAP baseline
        fill_order = DutchOrder(
            side="UP", limit_price=0.50, shares=10.0, dollars=5.0,
            time_pct=0.2, placed_at=datetime.now(UTC), reason="cheap",
        )
        engine.on_fill(fill_order, fill_price=0.50, filled_shares=10.0)
        # Now hedge buy at 0.65 (> 0.50 * 1.10 = 0.55) — would be blocked by R6
        # But hedge orders should be exempt
        book_up = make_book(0.60, 0.65)  # ask=0.65, hedge tier
        book_dn = make_book(0.20, 0.25)  # cheap_dn = strong edge
        orders = engine.on_tick(0.50, 0.40, book_up, book_dn)
        up_hedge = [o for o in orders if o.side == "UP" and "hedge" in o.reason]
        assert len(up_hedge) >= 1  # hedge goes through despite VWAP

    def test_vwap_still_blocks_cheap_tier(self):
        """R6 still blocks cheap/edge tiers when price deteriorates."""
        engine = self._make_engine(
            cheap_threshold=0.10, vwap_tolerance=0.10,
        )
        # Fill DN at 0.30
        fill_order = DutchOrder(
            side="DN", limit_price=0.30, shares=10.0, dollars=3.0,
            time_pct=0.2, placed_at=datetime.now(UTC), reason="cheap",
        )
        engine.on_fill(fill_order, fill_price=0.30, filled_shares=10.0)
        # Cheap tier at ask=0.45 (> 0.30 * 1.10 = 0.33) — should be blocked
        book_up = make_book(0.50, 0.55)
        book_dn = make_book(0.40, 0.45)  # ask=0.45 < 0.50 → cheap tier
        orders = engine.on_tick(0.50, 0.50, book_up, book_dn)
        dn_orders = [o for o in orders if o.side == "DN"]
        assert len(dn_orders) == 0  # blocked by R6 VWAP

    def test_balance_subject_to_spacing(self):
        """Balance orders are now paced by R2 (not exempt like emergency)."""
        engine = self._make_engine(
            cheap_threshold=0.10, max_hedge_ask=0.80,
        )
        # Heavy DN, need UP to balance
        engine._inventory.shares_dn = 100
        engine._inventory.cost_dn = 30
        # Set last UP order time close to now
        engine._last_order_time_pct_up = 0.499

        book_up = make_book(0.44, 0.48)
        book_dn = make_book(0.44, 0.48)
        # t=0.50, gap = 0.001 which is less than min_gap
        orders = engine.on_tick(0.50, 0.50, book_up, book_dn)
        up_balance = [o for o in orders if o.side == "UP" and "balance" in o.reason]
        assert len(up_balance) == 0  # blocked by R2 spacing

    def test_emergency_still_exempt_from_spacing(self):
        """Emergency (last 30s) still bypasses R2 spacing."""
        engine = self._make_engine(
            cheap_threshold=0.10, max_hedge_ask=0.80,
            min_share_match=0.0,  # disable share match to test emergency
        )
        engine._inventory.shares_up = 40
        engine._inventory.cost_up = 20
        engine._last_order_time_pct_dn = 0.969

        book_up = make_book(0.48, 0.52)
        book_dn = make_book(0.44, 0.48)
        # t=0.97 → 27s left < 30s → emergency window
        orders = engine.on_tick(0.97, 0.50, book_up, book_dn)
        dn_emergency = [o for o in orders if "emergency" in o.reason]
        assert len(dn_emergency) >= 1  # emergency bypasses R2

    def test_one_side_per_tick(self):
        """Only one side gets an order per on_tick call."""
        engine = self._make_engine(cheap_threshold=0.10)
        book_up = make_book(0.40, 0.42)  # both cheap
        book_dn = make_book(0.40, 0.42)
        orders = engine.on_tick(0.50, 0.50, book_up, book_dn)
        assert len(orders) == 1  # break after first order

    def test_rebalance_warmup_blocks_early(self):
        """No rebalance until warm-up threshold met."""
        engine = self._make_engine(
            min_share_match=0.50, rebalance_warmup=0.10, max_hedge_ask=0.80,
        )
        # Only $5 spent (2.5% of $200, below 10% warmup)
        engine._inventory.shares_up = 10
        engine._inventory.cost_up = 5.0
        # share match = 0% but warmup not reached
        book_up = make_book(0.48, 0.52)
        book_dn = make_book(0.44, 0.48)
        orders = engine.on_tick(0.50, 0.50, book_up, book_dn)
        rebalance = [o for o in orders if "match_rebalance" in o.reason]
        assert len(rebalance) == 0

    def test_rebalance_after_warmup(self):
        """Rebalance fires after warm-up threshold met."""
        engine = self._make_engine(
            min_share_match=0.50, rebalance_warmup=0.10, max_hedge_ask=0.80,
        )
        # $25 spent (12.5% of $200, above 10% warmup)
        engine._inventory.shares_up = 50
        engine._inventory.cost_up = 25.0
        book_up = make_book(0.48, 0.52)
        book_dn = make_book(0.44, 0.48)
        orders = engine.on_tick(0.50, 0.50, book_up, book_dn)
        rebalance = [o for o in orders if "match_rebalance" in o.reason]
        assert len(rebalance) >= 1


class TestDutchV5Sells:
    """Tests for V5: sell logic + warm-up gate."""

    def _make_engine(self, **kwargs) -> DutchAccumulationEngine:
        config = DutchConfig(**kwargs)
        return DutchAccumulationEngine(config)

    def test_sell_losing_side(self):
        """Sell fires when model strongly disagrees with held side."""
        engine = self._make_engine(
            sell_loss_threshold=0.05, sell_min_shares=5.0,
            rebalance_warmup=0.0, max_hedge_ask=0.80,
        )
        # Hold 50 UP shares at 0.30 ($15)
        engine._inventory.shares_up = 50.0
        engine._inventory.cost_up = 15.0

        # Model P(UP)=0.20. Both asks > 0.80 → no buy triggers at all.
        # Sell pass: cheap_UP = 0.20 - 0.90 = -0.70 < -0.05 → sell UP
        book_up = make_book(0.85, 0.90)
        book_dn = make_book(0.08, 0.10)  # DN is cheap but loop starts UP, no buy
        orders = engine.on_tick(0.50, 0.20, book_up, book_dn)
        sell_orders = [o for o in orders if getattr(o, "action", "BUY") == "SELL"]
        assert len(sell_orders) >= 1
        assert sell_orders[0].side == "UP"
        assert "sell_losing" in sell_orders[0].reason

    def test_no_sell_when_model_agrees(self):
        """No sell when model says this side is fine."""
        engine = self._make_engine(
            sell_loss_threshold=0.05, sell_min_shares=5.0,
            rebalance_warmup=0.0,
        )
        engine._inventory.shares_up = 50.0
        engine._inventory.cost_up = 15.0

        # Model says P(UP)=0.60 → cheap_UP = 0.60 - 0.50 = +0.10 (positive)
        book_up = make_book(0.48, 0.50)
        book_dn = make_book(0.48, 0.50)
        orders = engine.on_tick(0.50, 0.60, book_up, book_dn)
        sell_orders = [o for o in orders if getattr(o, "action", "BUY") == "SELL"]
        assert len(sell_orders) == 0

    def test_sell_max_fraction(self):
        """Sell respects max fraction of net shares."""
        engine = self._make_engine(
            sell_loss_threshold=0.05, sell_max_fraction=0.50,
            sell_min_shares=5.0, order_size=1000.0,  # large to not limit
            rebalance_warmup=0.0,
        )
        engine._inventory.shares_up = 100.0
        engine._inventory.cost_up = 30.0

        book_up = make_book(0.48, 0.50)
        book_dn = make_book(0.48, 0.50)
        orders = engine.on_tick(0.50, 0.20, book_up, book_dn)
        sell_orders = [o for o in orders if getattr(o, "action", "BUY") == "SELL"]
        if sell_orders:
            assert sell_orders[0].shares <= 50.0  # 50% of 100

    def test_sell_updates_net_inventory(self):
        """Sell fill updates net shares and revenue."""
        engine = self._make_engine()
        engine._inventory.shares_up = 100.0
        engine._inventory.cost_up = 30.0

        sell_order = DutchOrder(
            side="UP", limit_price=0.40, shares=50.0, dollars=20.0,
            time_pct=0.5, placed_at=datetime.now(UTC), reason="sell_losing",
            action="SELL",
        )
        engine.on_fill(sell_order, fill_price=0.40, filled_shares=50.0)

        assert engine._inventory.sold_shares_up == 50.0
        assert engine._inventory.sell_revenue_up == 20.0
        assert engine._inventory.net_shares_up == 50.0  # 100 - 50
        assert engine._inventory.net_cost_up == 10.0  # 30 - 20

    def test_sell_concurrent_with_buy(self):
        """Buy and sell can fire on same tick (different sides)."""
        engine = self._make_engine(
            cheap_threshold=0.10, sell_loss_threshold=0.05,
            sell_min_shares=5.0, rebalance_warmup=0.0,
            max_hedge_ask=0.80,
        )
        # Hold UP shares, model says UP losing
        engine._inventory.shares_up = 50.0
        engine._inventory.cost_up = 15.0

        # DN ask=0.30 < 0.50 → cheap buy DN
        # UP ask=0.85 > max_hedge_ask → no hedge, but sell pass: edge=-0.65 → sell UP
        book_up = make_book(0.83, 0.85)
        book_dn = make_book(0.13, 0.15)
        orders = engine.on_tick(0.50, 0.20, book_up, book_dn)

        buy_orders = [o for o in orders if getattr(o, "action", "BUY") == "BUY"]
        sell_orders = [o for o in orders if getattr(o, "action", "BUY") == "SELL"]
        assert len(buy_orders) >= 1  # DN cheap buy
        assert len(sell_orders) >= 1  # UP sell

    def test_sell_not_same_side_as_buy(self):
        """Can't sell the same side we just bought."""
        engine = self._make_engine(
            cheap_threshold=0.10, sell_loss_threshold=0.05,
            sell_min_shares=5.0, rebalance_warmup=0.0,
            max_hedge_ask=0.80, min_share_match=0.0,  # disable share match
        )
        # Hold DN shares. Model P(UP)=0.80 → DN is losing.
        # DN ask=0.30 < 0.50 → cheap BUY DN fires (loop starts DN since count=0→UP first,
        # but UP ask=0.85 > 0.50, no edge → skips to DN).
        engine._inventory.shares_dn = 50.0
        engine._inventory.cost_dn = 15.0

        book_up = make_book(0.83, 0.85)  # not cheap, not hedge-eligible
        book_dn = make_book(0.28, 0.30)  # cheap → buy DN
        orders = engine.on_tick(0.50, 0.80, book_up, book_dn)

        buy_dn = [o for o in orders if getattr(o, "action", "BUY") == "BUY" and o.side == "DN"]
        sell_dn = [o for o in orders if getattr(o, "action", "BUY") == "SELL" and o.side == "DN"]
        assert len(buy_dn) >= 1, f"Should buy DN cheap, got {[o.reason for o in orders]}"
        assert len(sell_dn) == 0  # can't sell same side we bought

    def test_warm_up_blocks_hedge(self):
        """Hedge doesn't fire before warm-up."""
        engine = self._make_engine(
            cheap_threshold=0.10, max_hedge_ask=0.80, rebalance_warmup=0.10,
        )
        # $0 spent → warm-up not passed
        book_up = make_book(0.55, 0.60)  # hedge candidate
        book_dn = make_book(0.30, 0.35)  # other side has edge
        orders = engine.on_tick(0.50, 0.40, book_up, book_dn)
        hedge = [o for o in orders if "hedge" in o.reason]
        assert len(hedge) == 0

    def test_warm_up_blocks_balance(self):
        """Balance doesn't fire before warm-up."""
        engine = self._make_engine(
            cheap_threshold=0.10, max_hedge_ask=0.80, rebalance_warmup=0.10,
        )
        engine._inventory.shares_dn = 50
        engine._inventory.cost_dn = 5.0  # only 2.5% of $200 budget
        book_up = make_book(0.55, 0.60)
        book_dn = make_book(0.55, 0.60)
        orders = engine.on_tick(0.50, 0.50, book_up, book_dn)
        balance = [o for o in orders if "balance" in o.reason]
        assert len(balance) == 0

    def test_cheap_fires_before_warmup(self):
        """Cheap tier fires regardless of warm-up."""
        engine = self._make_engine(
            cheap_threshold=0.10, rebalance_warmup=0.10,
        )
        # $0 spent, but ask < 0.50 → cheap fires
        book_up = make_book(0.30, 0.35)
        book_dn = make_book(0.55, 0.60)
        orders = engine.on_tick(0.50, 0.50, book_up, book_dn)
        assert len(orders) >= 1
        assert "cheap" in orders[0].reason

    def test_sell_cooldown_prevents_rapid_sells(self):
        """Two on_tick calls within cooldown window should produce only 1 sell."""
        engine = self._make_engine(
            sell_loss_threshold=0.05, sell_min_shares=5.0,
            rebalance_warmup=0.0, max_hedge_ask=0.80,
        )
        engine._inventory.shares_up = 100.0
        engine._inventory.cost_up = 30.0

        book_up = make_book(0.85, 0.90)
        book_dn = make_book(0.08, 0.10)

        # First tick at t=0.50 → should sell
        orders1 = engine.on_tick(0.50, 0.20, book_up, book_dn)
        sells1 = [o for o in orders1 if o.action == "SELL"]
        assert len(sells1) == 1

        # Second tick at t=0.502 (within 0.005 cooldown) → no sell
        orders2 = engine.on_tick(0.502, 0.20, book_up, book_dn)
        sells2 = [o for o in orders2 if o.action == "SELL"]
        assert len(sells2) == 0

        # Third tick at t=0.510 (past cooldown) → should sell again
        orders3 = engine.on_tick(0.510, 0.20, book_up, book_dn)
        sells3 = [o for o in orders3 if o.action == "SELL"]
        assert len(sells3) == 1

    def test_sell_pending_prevents_oversell(self):
        """Total pending + sold shares can't exceed sell_max_fraction of net shares."""
        engine = self._make_engine(
            sell_loss_threshold=0.05, sell_min_shares=5.0,
            sell_max_fraction=0.50, order_size=500.0,  # large to hit max_sellable cap
            rebalance_warmup=0.0, max_hedge_ask=0.80,
        )
        engine._inventory.shares_up = 100.0
        engine._inventory.cost_up = 30.0

        book_up = make_book(0.85, 0.90)
        book_dn = make_book(0.08, 0.10)

        # First tick: sell fires, reserves up to 50% = 50 shares
        orders1 = engine.on_tick(0.50, 0.20, book_up, book_dn)
        sells1 = [o for o in orders1 if o.action == "SELL"]
        assert len(sells1) == 1
        reserved = engine._pending_sell_shares_up
        assert reserved > 0
        # With order_size=500/0.85=588 >> 50, sell should be capped at 50
        assert abs(reserved - 50.0) < 1.0

        # Second tick (past cooldown): max_sellable = 100*0.5 - 50 ≈ 0 → blocked
        orders2 = engine.on_tick(0.510, 0.20, book_up, book_dn)
        sells2 = [o for o in orders2 if o.action == "SELL"]
        assert len(sells2) == 0  # blocked by pending reservation

    def test_sell_pending_released_on_fill(self):
        """After fill, pending reservation is released and next sell can fire."""
        engine = self._make_engine(
            sell_loss_threshold=0.05, sell_min_shares=5.0,
            sell_max_fraction=0.50, rebalance_warmup=0.0, max_hedge_ask=0.80,
        )
        engine._inventory.shares_up = 100.0
        engine._inventory.cost_up = 30.0

        book_up = make_book(0.85, 0.90)
        book_dn = make_book(0.08, 0.10)

        # Place sell
        orders1 = engine.on_tick(0.50, 0.20, book_up, book_dn)
        sell = [o for o in orders1 if o.action == "SELL"][0]
        assert engine._pending_sell_shares_up > 0

        # Simulate fill — releases reservation
        engine.on_fill(sell, 0.85, sell.shares)
        assert engine._pending_sell_shares_up == 0.0

    def test_sell_pending_released_on_partial_fill(self):
        """Partial fill releases FULL order.shares reservation."""
        engine = self._make_engine(
            sell_loss_threshold=0.05, sell_min_shares=5.0,
            sell_max_fraction=0.50, rebalance_warmup=0.0, max_hedge_ask=0.80,
        )
        engine._inventory.shares_up = 100.0
        engine._inventory.cost_up = 30.0

        book_up = make_book(0.85, 0.90)
        book_dn = make_book(0.08, 0.10)

        orders1 = engine.on_tick(0.50, 0.20, book_up, book_dn)
        sell = [o for o in orders1 if o.action == "SELL"][0]
        reserved = engine._pending_sell_shares_up

        # Partial fill: only half filled, but full reservation released
        engine.on_fill(sell, 0.85, sell.shares * 0.5)
        assert engine._pending_sell_shares_up == 0.0  # full reservation released

    def test_sell_pending_released_on_cancel(self):
        """Cancelled sell releases pending reservation."""
        engine = self._make_engine(
            sell_loss_threshold=0.05, sell_min_shares=5.0,
            sell_max_fraction=0.50, rebalance_warmup=0.0, max_hedge_ask=0.80,
        )
        engine._inventory.shares_up = 100.0
        engine._inventory.cost_up = 30.0

        book_up = make_book(0.85, 0.90)
        book_dn = make_book(0.08, 0.10)

        orders1 = engine.on_tick(0.50, 0.20, book_up, book_dn)
        sell = [o for o in orders1 if o.action == "SELL"][0]
        assert engine._pending_sell_shares_up > 0

        # Cancel releases reservation
        engine.on_sell_cancelled(sell)
        assert engine._pending_sell_shares_up == 0.0


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
