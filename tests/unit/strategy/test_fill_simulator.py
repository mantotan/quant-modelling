"""Tests for LimitOrderSimulator V2 (consecutive-tick + chasing)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from qm.data.connectors.polymarket_ws import TokenBook
from qm.strategy.dutch.engine import DutchOrder
from qm.strategy.dutch.fill_simulator import LimitOrderSimulator


def make_book(best_bid: float, best_ask: float, depth: float = 100.0) -> TokenBook:
    book = TokenBook(token_id="test")
    book.bids = {best_bid: depth}
    book.asks = {best_ask: depth}
    book._update_bbo()
    return book


def make_order(
    side: str = "UP", limit_price: float = 0.49, shares: float = 20.0,
) -> DutchOrder:
    return DutchOrder(
        side=side,
        limit_price=limit_price,
        shares=shares,
        dollars=shares * limit_price,
        time_pct=0.50,
        placed_at=datetime.now(UTC),
        reason="test",
    )


class TestConsecutiveTickFill:
    def test_no_fill_when_ask_above_limit(self):
        sim = LimitOrderSimulator(fill_ticks=3)
        sim.place(make_order(limit_price=0.49))
        book_up = make_book(0.48, 0.52)  # ask > limit
        book_dn = make_book(0.44, 0.48)
        fills = sim.on_tick(0.55, book_up, book_dn)
        assert fills == []

    def test_no_fill_before_n_ticks(self):
        sim = LimitOrderSimulator(fill_ticks=3)
        sim.place(make_order(side="UP", limit_price=0.49))
        book_up = make_book(0.47, 0.49)  # ask = limit
        book_dn = make_book(0.44, 0.48)

        # Tick 1 and 2: crossing but not enough ticks
        assert sim.on_tick(0.50, book_up, book_dn) == []
        assert sim.on_tick(0.51, book_up, book_dn) == []

    def test_fills_after_n_consecutive_ticks(self):
        sim = LimitOrderSimulator(fill_ticks=3)
        sim.place(make_order(side="UP", limit_price=0.49))
        book_up = make_book(0.47, 0.49)
        book_dn = make_book(0.44, 0.48)

        sim.on_tick(0.50, book_up, book_dn)  # tick 1
        sim.on_tick(0.51, book_up, book_dn)  # tick 2
        fills = sim.on_tick(0.52, book_up, book_dn)  # tick 3 → fill
        assert len(fills) == 1
        assert fills[0].fill_ticks == 3
        assert fills[0].filled_shares == pytest.approx(20.0)

    def test_bounce_resets_counter(self):
        sim = LimitOrderSimulator(fill_ticks=3)
        sim.place(make_order(side="UP", limit_price=0.49))
        book_low = make_book(0.47, 0.49)
        book_high = make_book(0.48, 0.52)
        book_dn = make_book(0.44, 0.48)

        sim.on_tick(0.50, book_low, book_dn)  # tick 1
        sim.on_tick(0.51, book_low, book_dn)  # tick 2
        sim.on_tick(0.52, book_high, book_dn)  # bounce! counter resets
        sim.on_tick(0.53, book_low, book_dn)  # tick 1 again
        sim.on_tick(0.54, book_low, book_dn)  # tick 2
        fills = sim.on_tick(0.55, book_low, book_dn)  # tick 3 → fill
        assert len(fills) == 1

    def test_would_fill_count_on_bounce(self):
        sim = LimitOrderSimulator(fill_ticks=3)
        sim.place(make_order(side="UP", limit_price=0.49))
        book_low = make_book(0.47, 0.49)
        book_high = make_book(0.48, 0.52)
        book_dn = make_book(0.44, 0.48)

        # 2 bounces before final fill
        sim.on_tick(0.50, book_low, book_dn)
        sim.on_tick(0.51, book_high, book_dn)  # bounce 1
        sim.on_tick(0.52, book_low, book_dn)
        sim.on_tick(0.53, book_high, book_dn)  # bounce 2
        sim.on_tick(0.54, book_low, book_dn)
        sim.on_tick(0.55, book_low, book_dn)
        sim.on_tick(0.56, book_low, book_dn)  # fill

        # Cancel to collect stats
        assert sim.stats.filled == 1

    def test_partial_fill_low_depth(self):
        sim = LimitOrderSimulator(fill_ticks=3)
        sim.place(make_order(side="UP", limit_price=0.49, shares=200.0))
        book_up = make_book(0.47, 0.49, depth=50.0)
        book_dn = make_book(0.44, 0.48)

        for _ in range(3):
            sim.on_tick(0.50 + _ * 0.01, book_up, book_dn)

        # Last tick should have filled
        assert sim.stats.filled == 1
        assert sim.stats.partial == 1

    def test_dn_side_order(self):
        sim = LimitOrderSimulator(fill_ticks=3)
        sim.place(make_order(side="DN", limit_price=0.45))
        book_up = make_book(0.48, 0.52)
        book_dn = make_book(0.43, 0.45)

        for i in range(3):
            sim.on_tick(0.50 + i * 0.01, book_up, book_dn)

        assert sim.stats.filled == 1

    def test_none_book_keeps_pending(self):
        sim = LimitOrderSimulator(fill_ticks=3)
        sim.place(make_order())
        fills = sim.on_tick(0.50, None, None)
        assert fills == []
        assert len(sim.pending_orders) == 1


class TestOrderChasing:
    def test_chase_when_market_moves_away(self):
        sim = LimitOrderSimulator(
            fill_ticks=3, chase_threshold=0.03, max_chase=2, spread_offset=0.01,
        )
        order = make_order(side="UP", limit_price=0.49)
        sim.place(order)

        # Market moves: bid goes from 0.48 to 0.54
        # new_limit = 0.54 + 0.01 = 0.55, distance = 0.55 - 0.49 = 0.06 > 0.03
        book_up = make_book(0.54, 0.56)
        book_dn = make_book(0.44, 0.48)
        sim.on_tick(0.55, book_up, book_dn)

        assert sim.stats.chased == 1
        # Order should have new limit price
        assert sim.pending_orders[0].limit_price == pytest.approx(0.55)

    def test_max_chase_limit(self):
        sim = LimitOrderSimulator(
            fill_ticks=3, chase_threshold=0.03, max_chase=2,
            spread_offset=0.01, cancel_distance=0.05,
        )
        sim.place(make_order(side="UP", limit_price=0.40))
        book_dn = make_book(0.44, 0.48)

        # Chase 1: bid=0.44 → new_limit=0.45, distance=0.05 > 0.03
        sim.on_tick(0.50, make_book(0.44, 0.48), book_dn)
        assert sim.stats.chased == 1

        # Chase 2: bid=0.49 → new_limit=0.50, distance from 0.45=0.05 > 0.03
        sim.on_tick(0.51, make_book(0.49, 0.53), book_dn)
        assert sim.stats.chased == 2

        # No more chases. Bid=0.56 → new_limit=0.57, distance=0.07 > cancel=0.05
        sim.on_tick(0.52, make_book(0.56, 0.60), book_dn)
        assert sim.stats.cancelled == 1

    def test_cancel_when_too_far_and_no_chases(self):
        """When distance > cancel_distance and no chases remaining, cancel."""
        sim = LimitOrderSimulator(
            fill_ticks=3, chase_threshold=0.03, max_chase=0,  # no chasing allowed
            spread_offset=0.01, cancel_distance=0.05,
        )
        sim.place(make_order(side="UP", limit_price=0.40))
        book_dn = make_book(0.44, 0.48)

        # distance = 0.47 - 0.40 = 0.07 > cancel=0.05, chase_count=0 >= max=0
        book_up = make_book(0.46, 0.50)
        sim.on_tick(0.55, book_up, book_dn)
        assert sim.stats.cancelled == 1
        assert len(sim.pending_orders) == 0

    def test_chase_then_fill(self):
        sim = LimitOrderSimulator(
            fill_ticks=2, chase_threshold=0.03, max_chase=2, spread_offset=0.01,
        )
        sim.place(make_order(side="UP", limit_price=0.45))
        book_dn = make_book(0.44, 0.48)

        # Chase: bid moves to 0.50
        sim.on_tick(0.50, make_book(0.50, 0.53), book_dn)
        assert sim.stats.chased == 1
        new_limit = sim.pending_orders[0].limit_price  # should be 0.51

        # Now ask drops to new limit → fill after 2 ticks
        book_fill = make_book(0.49, new_limit)
        sim.on_tick(0.51, book_fill, book_dn)  # tick 1
        fills = sim.on_tick(0.52, book_fill, book_dn)  # tick 2
        assert len(fills) == 1
        assert "chase#1" in fills[0].order.reason


class TestSimulatorStats:
    def test_stats_tracking(self):
        sim = LimitOrderSimulator(fill_ticks=2)
        sim.place(make_order())
        book_up = make_book(0.47, 0.49)
        book_dn = make_book(0.44, 0.48)
        sim.on_tick(0.50, book_up, book_dn)
        sim.on_tick(0.51, book_up, book_dn)

        assert sim.stats.placed == 1
        assert sim.stats.filled == 1
        assert sim.stats.avg_fill_ticks == pytest.approx(2.0)

    def test_cancel_all(self):
        sim = LimitOrderSimulator(fill_ticks=3)
        sim.place(make_order(side="UP"))
        sim.place(make_order(side="DN", limit_price=0.45))
        cancelled = sim.cancel_all()
        assert len(cancelled) == 2
        assert sim.stats.expired == 2

    def test_reset(self):
        sim = LimitOrderSimulator(fill_ticks=3)
        sim.place(make_order())
        sim.reset()
        assert sim.pending_orders == []
        assert sim.stats.placed == 0

    def test_multiple_orders_independent(self):
        sim = LimitOrderSimulator(fill_ticks=2)
        sim.place(make_order(side="UP", limit_price=0.49))
        sim.place(make_order(side="DN", limit_price=0.45))

        book_up = make_book(0.47, 0.49)
        book_dn = make_book(0.43, 0.48)  # ask > DN limit

        sim.on_tick(0.50, book_up, book_dn)
        fills = sim.on_tick(0.51, book_up, book_dn)
        assert len(fills) == 1
        assert fills[0].order.side == "UP"
        assert len(sim.pending_orders) == 1  # DN still pending


class TestV3Realism:
    """V3 fixes: sweep detection, zero-depth rejection, sell-side depth, chase stats."""

    def test_default_fill_ticks_is_10(self):
        sim = LimitOrderSimulator()
        assert sim._fill_ticks == 10

    def test_sweep_fills_on_tick_1(self):
        """Ask drops 1c+ below limit → sweep fill on first qualifying tick."""
        sim = LimitOrderSimulator(fill_ticks=10, sweep_threshold=0.01)
        sim.place(make_order(side="UP", limit_price=0.49))
        # Ask at 0.47 — 2c below limit (sweep)
        book_up = make_book(0.45, 0.47)
        book_dn = make_book(0.44, 0.48)
        fills = sim.on_tick(0.50, book_up, book_dn)
        assert len(fills) == 1
        assert fills[0].fill_ticks == 1  # swept on first tick

    def test_no_sweep_when_ask_at_limit(self):
        """Ask exactly at limit is NOT a sweep — needs fill_ticks consecutive."""
        sim = LimitOrderSimulator(fill_ticks=10, sweep_threshold=0.01)
        sim.place(make_order(side="UP", limit_price=0.49))
        book_up = make_book(0.47, 0.49)  # ask = limit, 0c gap
        book_dn = make_book(0.44, 0.48)
        fills = sim.on_tick(0.50, book_up, book_dn)
        assert fills == []  # needs 10 ticks, only 1 so far

    def test_zero_depth_no_fill(self):
        """When no depth at limit price, order stays pending."""
        sim = LimitOrderSimulator(fill_ticks=1, sweep_threshold=0.01)
        sim.place(make_order(side="UP", limit_price=0.49))
        # Book has ask at 0.49 but with 0 depth
        book_up = TokenBook(token_id="test")
        book_up.bids = {0.47: 100.0}
        book_up.asks = {0.50: 100.0}  # depth at 0.50, NOT at 0.49
        book_up._update_bbo()
        # best_ask is 0.50 > 0.49, so ask > limit → no fill condition met
        # But let's test with ask AT limit but no depth at that price
        book_up2 = TokenBook(token_id="test")
        book_up2.bids = {0.47: 100.0}
        book_up2.asks = {0.49: 0.0}  # zero size at limit
        book_up2._update_bbo()
        book_dn = make_book(0.44, 0.48)
        # Sweep: ask drops 2c below
        book_sweep = TokenBook(token_id="test")
        book_sweep.bids = {0.45: 100.0}
        book_sweep.asks = {}  # NO asks at all
        book_sweep.best_ask = 0.47  # synthetic — less than limit
        book_dn = make_book(0.44, 0.48)
        fills = sim.on_tick(0.50, book_sweep, book_dn)
        # Sweep triggered but available_at_or_below = 0 (empty asks) → no fill
        assert fills == []
        assert len(sim.pending_orders) == 1  # still pending

    def test_sell_depth_uses_bids(self):
        """Sell fills check bid-side depth, not ask-side."""
        sim = LimitOrderSimulator(fill_ticks=1, sweep_threshold=0.01)
        sell_order = DutchOrder(
            side="UP", limit_price=0.50, shares=20.0,
            dollars=10.0, time_pct=0.50,
            placed_at=__import__("datetime").datetime.now(__import__("datetime").timezone.utc),
            reason="test_sell", action="SELL",
        )
        sim.place(sell_order)
        # bid=0.52 >= limit=0.50 → sweep (2c above), but bids have depth
        book_up = TokenBook(token_id="test")
        book_up.bids = {0.52: 50.0}  # 50 shares at bid
        book_up.asks = {0.55: 100.0}
        book_up._update_bbo()
        book_dn = make_book(0.44, 0.48)
        fills = sim.on_tick(0.50, book_up, book_dn)
        assert len(fills) == 1
        assert fills[0].filled_shares == 20.0  # filled from bid-side depth

    def test_chase_cancelled_stat(self):
        """Chase increments both chased and chase_cancelled."""
        sim = LimitOrderSimulator(
            fill_ticks=10, chase_threshold=0.03, max_chase=2, spread_offset=0.01,
        )
        sim.place(make_order(side="UP", limit_price=0.40))
        book_dn = make_book(0.44, 0.48)
        # bid=0.44 → new_limit=0.45, distance=0.05 > 0.03 → chase
        sim.on_tick(0.50, make_book(0.44, 0.48), book_dn)
        assert sim.stats.chased == 1
        assert sim.stats.chase_cancelled == 1

    def test_cancel_at_exact_boundary(self):
        """Distance == cancel_distance → cancels (was > only)."""
        sim = LimitOrderSimulator(
            fill_ticks=10, chase_threshold=0.03, max_chase=0,
            spread_offset=0.01, cancel_distance=0.05,
        )
        sim.place(make_order(side="UP", limit_price=0.40))
        book_dn = make_book(0.44, 0.48)
        # new_limit=0.46, distance=0.06 >= 0.05 → cancel (was > so 0.05 wouldn't cancel)
        sim.on_tick(0.50, make_book(0.45, 0.50), book_dn)
        assert sim.stats.cancelled == 1

    def test_chase_stays_below_ask(self):
        """Chased price never reaches ask."""
        sim = LimitOrderSimulator(
            fill_ticks=10, chase_threshold=0.03, max_chase=2, spread_offset=0.01,
        )
        sim.place(make_order(side="UP", limit_price=0.40))
        book_dn = make_book(0.44, 0.48)
        # bid=0.48, ask=0.49 → new_limit=0.49 >= ask → clamped to 0.48
        sim.on_tick(0.50, make_book(0.48, 0.49), book_dn)
        assert sim.stats.chased == 1
        assert sim.pending_orders[0].limit_price < 0.49  # below ask

    def test_chase_no_downward(self):
        """Chase is skipped if new_limit <= current limit."""
        sim = LimitOrderSimulator(
            fill_ticks=10, chase_threshold=0.03, max_chase=2, spread_offset=0.01,
        )
        sim.place(make_order(side="UP", limit_price=0.49))
        book_dn = make_book(0.44, 0.48)
        # bid=0.47, ask=0.49 → new_limit=0.48, but clamp to ask-0.01=0.48
        # 0.48 < 0.49 (current limit) → skip chase
        sim.on_tick(0.50, make_book(0.47, 0.49), book_dn)
        assert sim.stats.chased == 0  # no chase — would be downward
