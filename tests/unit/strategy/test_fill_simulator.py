"""Tests for LimitOrderSimulator V4 (market-cross fill model)."""

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


class TestMarketCrossFill:
    def test_no_fill_when_ask_above_limit(self):
        sim = LimitOrderSimulator()
        sim.place(make_order(limit_price=0.49))
        book_up = make_book(0.48, 0.52)  # ask > limit
        book_dn = make_book(0.44, 0.48)
        fills = sim.on_tick(0.55, book_up, book_dn)
        assert fills == []

    def test_fill_when_ask_at_limit(self):
        """V4: fills immediately when ask <= limit (market crossed our level)."""
        sim = LimitOrderSimulator()
        sim.place(make_order(side="UP", limit_price=0.49))
        book_up = make_book(0.47, 0.49)  # ask = limit
        book_dn = make_book(0.44, 0.48)
        fills = sim.on_tick(0.50, book_up, book_dn)
        assert len(fills) == 1
        assert fills[0].filled_shares == pytest.approx(20.0)

    def test_fill_when_ask_below_limit(self):
        """V4: fills immediately when ask < limit (price went through)."""
        sim = LimitOrderSimulator()
        sim.place(make_order(side="UP", limit_price=0.49))
        book_up = make_book(0.45, 0.47)  # ask < limit
        book_dn = make_book(0.44, 0.48)
        fills = sim.on_tick(0.50, book_up, book_dn)
        assert len(fills) == 1
        assert fills[0].fill_ticks == 1

    def test_partial_fill_low_depth(self):
        sim = LimitOrderSimulator()
        sim.place(make_order(side="UP", limit_price=0.49, shares=200.0))
        book_up = make_book(0.47, 0.49, depth=50.0)
        book_dn = make_book(0.44, 0.48)
        fills = sim.on_tick(0.50, book_up, book_dn)
        assert len(fills) == 1
        assert sim.stats.partial == 1
        assert fills[0].filled_shares == pytest.approx(50.0)

    def test_dn_side_order(self):
        sim = LimitOrderSimulator()
        sim.place(make_order(side="DN", limit_price=0.45))
        book_up = make_book(0.48, 0.52)
        book_dn = make_book(0.43, 0.45)  # ask = limit
        fills = sim.on_tick(0.50, book_up, book_dn)
        assert len(fills) == 1

    def test_none_book_keeps_pending(self):
        sim = LimitOrderSimulator()
        sim.place(make_order())
        fills = sim.on_tick(0.50, None, None)
        assert fills == []
        assert len(sim.pending_orders) == 1


class TestOrderChasing:
    def test_chase_when_market_moves_away(self):
        sim = LimitOrderSimulator(
            chase_threshold=0.03, max_chase=2, spread_offset=0.01,
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
            chase_threshold=0.03, max_chase=2,
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
            chase_threshold=0.03, max_chase=0,  # no chasing allowed
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
            chase_threshold=0.03, max_chase=2, spread_offset=0.01,
        )
        sim.place(make_order(side="UP", limit_price=0.45))
        book_dn = make_book(0.44, 0.48)

        # Chase: bid moves to 0.50
        sim.on_tick(0.50, make_book(0.50, 0.53), book_dn)
        assert sim.stats.chased == 1
        new_limit = sim.pending_orders[0].limit_price  # should be 0.51

        # Now ask drops to new limit → V4: fill immediately
        book_fill = make_book(0.49, new_limit)
        fills = sim.on_tick(0.51, book_fill, book_dn)
        assert len(fills) == 1
        assert "chase#1" in fills[0].order.reason


class TestSimulatorStats:
    def test_stats_tracking(self):
        sim = LimitOrderSimulator()
        sim.place(make_order())
        book_up = make_book(0.47, 0.49)
        book_dn = make_book(0.44, 0.48)
        fills = sim.on_tick(0.50, book_up, book_dn)

        assert sim.stats.placed == 1
        assert sim.stats.filled == 1
        assert sim.stats.avg_fill_ticks == pytest.approx(1.0)

    def test_cancel_all(self):
        sim = LimitOrderSimulator()
        sim.place(make_order(side="UP"))
        sim.place(make_order(side="DN", limit_price=0.45))
        cancelled = sim.cancel_all()
        assert len(cancelled) == 2
        assert sim.stats.expired == 2

    def test_reset(self):
        sim = LimitOrderSimulator()
        sim.place(make_order())
        sim.reset()
        assert sim.pending_orders == []
        assert sim.stats.placed == 0

    def test_multiple_orders_independent(self):
        sim = LimitOrderSimulator()
        sim.place(make_order(side="UP", limit_price=0.49))
        sim.place(make_order(side="DN", limit_price=0.45))

        book_up = make_book(0.47, 0.49)  # ask = UP limit → fill UP
        book_dn = make_book(0.43, 0.48)  # ask > DN limit → no fill

        fills = sim.on_tick(0.50, book_up, book_dn)
        assert len(fills) == 1
        assert fills[0].order.side == "UP"
        assert len(sim.pending_orders) == 1  # DN still pending


class TestV4Realism:
    """V4: market-cross fill model using real book data."""

    def test_default_fill_ticks_is_1(self):
        sim = LimitOrderSimulator()
        assert sim._fill_ticks == 1

    def test_zero_depth_no_fill(self):
        """When no depth at limit price, order stays pending."""
        sim = LimitOrderSimulator()
        sim.place(make_order(side="UP", limit_price=0.49))
        # Book with ask below limit but no depth
        book_sweep = TokenBook(token_id="test")
        book_sweep.bids = {0.45: 100.0}
        book_sweep.asks = {}  # NO asks at all
        book_sweep.best_ask = 0.47  # synthetic — less than limit
        book_dn = make_book(0.44, 0.48)
        fills = sim.on_tick(0.50, book_sweep, book_dn)
        assert fills == []
        assert len(sim.pending_orders) == 1  # still pending

    def test_sell_depth_uses_bids(self):
        """Sell fills check bid-side depth, not ask-side."""
        sim = LimitOrderSimulator()
        sell_order = DutchOrder(
            side="UP", limit_price=0.50, shares=20.0,
            dollars=10.0, time_pct=0.50,
            placed_at=__import__("datetime").datetime.now(__import__("datetime").timezone.utc),
            reason="test_sell", action="SELL",
        )
        sim.place(sell_order)
        # bid=0.52 >= limit=0.50 → fill
        book_up = TokenBook(token_id="test")
        book_up.bids = {0.52: 50.0}
        book_up.asks = {0.55: 100.0}
        book_up._update_bbo()
        book_dn = make_book(0.44, 0.48)
        fills = sim.on_tick(0.50, book_up, book_dn)
        assert len(fills) == 1
        assert fills[0].filled_shares == 20.0

    def test_chase_cancelled_stat(self):
        """Chase increments both chased and chase_cancelled."""
        sim = LimitOrderSimulator(
            chase_threshold=0.03, max_chase=2, spread_offset=0.01,
        )
        sim.place(make_order(side="UP", limit_price=0.40))
        book_dn = make_book(0.44, 0.48)
        # bid=0.44 → new_limit=0.45, distance=0.05 > 0.03 → chase
        sim.on_tick(0.50, make_book(0.44, 0.48), book_dn)
        assert sim.stats.chased == 1
        assert sim.stats.chase_cancelled == 1

    def test_cancel_at_exact_boundary(self):
        """Distance == cancel_distance → cancels."""
        sim = LimitOrderSimulator(
            chase_threshold=0.03, max_chase=0,
            spread_offset=0.01, cancel_distance=0.05,
        )
        sim.place(make_order(side="UP", limit_price=0.40))
        book_dn = make_book(0.44, 0.48)
        sim.on_tick(0.50, make_book(0.45, 0.50), book_dn)
        assert sim.stats.cancelled == 1

    def test_chase_stays_below_ask(self):
        """Chased price never reaches ask."""
        sim = LimitOrderSimulator(
            chase_threshold=0.03, max_chase=2, spread_offset=0.01,
        )
        sim.place(make_order(side="UP", limit_price=0.40))
        book_dn = make_book(0.44, 0.48)
        # bid=0.48, ask=0.49 → new_limit=0.49 >= ask → clamped to 0.48
        sim.on_tick(0.50, make_book(0.48, 0.49), book_dn)
        assert sim.stats.chased == 1
        assert sim.pending_orders[0].limit_price < 0.49

    def test_chase_no_downward(self):
        """Chase is skipped if new_limit <= current limit."""
        sim = LimitOrderSimulator(
            chase_threshold=0.03, max_chase=2, spread_offset=0.01,
        )
        sim.place(make_order(side="UP", limit_price=0.49))
        book_dn = make_book(0.44, 0.48)
        sim.on_tick(0.50, make_book(0.47, 0.49), book_dn)
        assert sim.stats.chased == 0  # no chase — would be downward
