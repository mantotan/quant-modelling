"""Tests for LimitOrderSimulator."""

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


def make_order(side: str = "UP", limit_price: float = 0.49, shares: float = 20.0) -> DutchOrder:
    return DutchOrder(
        side=side,
        limit_price=limit_price,
        shares=shares,
        dollars=shares * limit_price,
        time_pct=0.50,
        placed_at=datetime.now(UTC),
        reason="test",
    )


class TestLimitOrderSimulator:
    def test_no_fill_when_ask_above_limit(self):
        sim = LimitOrderSimulator(fill_latency_s=2.0, bar_seconds=900.0)
        order = make_order(limit_price=0.49)
        sim.place(order)

        book_up = make_book(0.48, 0.52)  # ask=0.52 > limit=0.49
        book_dn = make_book(0.44, 0.48)
        fills = sim.on_tick(0.55, book_up, book_dn)
        assert fills == []
        assert len(sim.pending_orders) == 1

    def test_fill_after_latency(self):
        sim = LimitOrderSimulator(fill_latency_s=2.0, bar_seconds=900.0)
        order = make_order(side="UP", limit_price=0.49)
        sim.place(order)

        # Tick 1: ask drops to 0.49 → CROSSING
        book_up = make_book(0.47, 0.49)
        book_dn = make_book(0.44, 0.48)
        fills = sim.on_tick(0.50, book_up, book_dn)
        assert fills == []  # latency not elapsed yet

        # Tick 2: 3s later (>2s latency), ask still at 0.49 → FILLED
        fills = sim.on_tick(0.5034, book_up, book_dn)  # ~3s on 900s bar
        assert len(fills) == 1
        assert fills[0].fill_price == pytest.approx(0.49)
        assert fills[0].filled_shares == pytest.approx(20.0)
        assert fills[0].partial is False

    def test_bounce_back_resets_to_pending(self):
        sim = LimitOrderSimulator(fill_latency_s=2.0, bar_seconds=900.0)
        order = make_order(side="UP", limit_price=0.49)
        sim.place(order)

        # Tick 1: ask drops → CROSSING
        book_up_low = make_book(0.47, 0.49)
        book_dn = make_book(0.44, 0.48)
        sim.on_tick(0.50, book_up_low, book_dn)

        # Tick 2: ask bounces back → PENDING
        book_up_high = make_book(0.48, 0.52)
        fills = sim.on_tick(0.501, book_up_high, book_dn)
        assert fills == []
        assert len(sim.pending_orders) == 1

        # Tick 3: ask drops again → new CROSSING
        sim.on_tick(0.51, book_up_low, book_dn)

        # Tick 4: latency passes → FILLED
        fills = sim.on_tick(0.5134, book_up_low, book_dn)
        assert len(fills) == 1

    def test_partial_fill_when_low_depth(self):
        sim = LimitOrderSimulator(fill_latency_s=2.0, bar_seconds=900.0)
        order = make_order(side="UP", limit_price=0.49, shares=200.0)
        sim.place(order)

        # Book has only 50 shares at 0.49
        book_up = make_book(0.47, 0.49, depth=50.0)
        book_dn = make_book(0.44, 0.48)

        sim.on_tick(0.50, book_up, book_dn)  # CROSSING
        fills = sim.on_tick(0.5034, book_up, book_dn)  # latency passed

        assert len(fills) == 1
        assert fills[0].filled_shares == pytest.approx(50.0)
        assert fills[0].partial is True
        assert sim.stats.partial == 1

    def test_depth_sums_multiple_levels(self):
        sim = LimitOrderSimulator(fill_latency_s=2.0, bar_seconds=900.0)
        order = make_order(side="UP", limit_price=0.49, shares=80.0)
        sim.place(order)

        # Book has 30 at 0.48 and 60 at 0.49 (total 90 at or below 0.49)
        book_up = TokenBook(token_id="test")
        book_up.asks = {0.48: 30.0, 0.49: 60.0, 0.52: 200.0}
        book_up.bids = {0.47: 100.0}
        book_up._update_bbo()
        book_dn = make_book(0.44, 0.48)

        sim.on_tick(0.50, book_up, book_dn)
        fills = sim.on_tick(0.5034, book_up, book_dn)

        assert len(fills) == 1
        assert fills[0].filled_shares == pytest.approx(80.0)  # 90 available > 80 requested
        assert fills[0].partial is False

    def test_dn_side_order(self):
        sim = LimitOrderSimulator(fill_latency_s=2.0, bar_seconds=900.0)
        order = make_order(side="DN", limit_price=0.45)
        sim.place(order)

        book_up = make_book(0.48, 0.52)
        book_dn = make_book(0.43, 0.45)  # ask=0.45 = limit

        sim.on_tick(0.50, book_up, book_dn)  # CROSSING
        fills = sim.on_tick(0.5034, book_up, book_dn)
        assert len(fills) == 1
        assert fills[0].order.side == "DN"

    def test_multiple_orders_fill_independently(self):
        sim = LimitOrderSimulator(fill_latency_s=2.0, bar_seconds=900.0)
        order_up = make_order(side="UP", limit_price=0.49)
        order_dn = make_order(side="DN", limit_price=0.45)
        sim.place(order_up)
        sim.place(order_dn)

        # Only UP ask crosses, DN stays above
        book_up = make_book(0.47, 0.49)
        book_dn = make_book(0.43, 0.48)  # ask=0.48 > limit=0.45

        sim.on_tick(0.50, book_up, book_dn)
        fills = sim.on_tick(0.5034, book_up, book_dn)
        assert len(fills) == 1
        assert fills[0].order.side == "UP"
        assert len(sim.pending_orders) == 1  # DN still pending

    def test_cancel_all_returns_unfilled(self):
        sim = LimitOrderSimulator(fill_latency_s=2.0, bar_seconds=900.0)
        order1 = make_order(side="UP", limit_price=0.49)
        order2 = make_order(side="DN", limit_price=0.45)
        sim.place(order1)
        sim.place(order2)

        cancelled = sim.cancel_all()
        assert len(cancelled) == 2
        assert sim.pending_orders == []
        assert sim.stats.expired == 2

    def test_stats_tracking(self):
        sim = LimitOrderSimulator(fill_latency_s=2.0, bar_seconds=900.0)
        order = make_order(side="UP", limit_price=0.49)
        sim.place(order)

        book_up = make_book(0.47, 0.49)
        book_dn = make_book(0.44, 0.48)
        sim.on_tick(0.50, book_up, book_dn)
        sim.on_tick(0.5034, book_up, book_dn)

        assert sim.stats.placed == 1
        assert sim.stats.filled == 1
        assert sim.stats.avg_fill_latency_s > 0

    def test_would_fill_count_on_bounce(self):
        sim = LimitOrderSimulator(fill_latency_s=2.0, bar_seconds=900.0)
        order = make_order(side="UP", limit_price=0.49)
        sim.place(order)

        book_low = make_book(0.47, 0.49)
        book_high = make_book(0.48, 0.52)
        book_dn = make_book(0.44, 0.48)

        # Bounce 1: cross then bounce
        sim.on_tick(0.50, book_low, book_dn)
        sim.on_tick(0.501, book_high, book_dn)

        # Bounce 2: cross then bounce
        sim.on_tick(0.52, book_low, book_dn)
        sim.on_tick(0.521, book_high, book_dn)

        cancelled = sim.cancel_all()
        assert sim.stats.would_fill == 2

    def test_none_book_keeps_order_pending(self):
        sim = LimitOrderSimulator(fill_latency_s=2.0, bar_seconds=900.0)
        order = make_order(side="UP", limit_price=0.49)
        sim.place(order)

        fills = sim.on_tick(0.50, None, None)
        assert fills == []
        assert len(sim.pending_orders) == 1

    def test_reset_clears_everything(self):
        sim = LimitOrderSimulator(fill_latency_s=2.0, bar_seconds=900.0)
        sim.place(make_order())
        sim.reset()
        assert sim.pending_orders == []
        assert sim.stats.placed == 0
