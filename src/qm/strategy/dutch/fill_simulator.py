"""Limit order fill simulator for dutch accumulation paper trading.

Simulates realistic maker-only limit order fills:
  - Orders placed at bid + offset (inside the spread)
  - Fill only when ask drops to or below limit price
  - Latency delay between price crossing and fill
  - Depth-aware partial fills
  - State machine: PENDING → CROSSING → FILLED | EXPIRED

This is separate from PaperExecutor which does instant pessimistic fills.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from qm.strategy.dutch.engine import DutchOrder

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class DutchFill:
    """A simulated limit order fill."""

    order: DutchOrder
    fill_price: float
    filled_shares: float
    fill_time_pct: float
    latency_s: float
    partial: bool


@dataclass
class _PendingOrder:
    """Internal state for a pending limit order."""

    order: DutchOrder
    state: str = "PENDING"  # PENDING, CROSSING, FILLED
    cross_time_pct: float = 0.0
    would_fill_count: int = 0


@dataclass
class SimulatorStats:
    """Cumulative stats for the simulator."""

    placed: int = 0
    filled: int = 0
    partial: int = 0
    would_fill: int = 0
    expired: int = 0
    total_latency_s: float = 0.0

    @property
    def avg_fill_latency_s(self) -> float:
        return self.total_latency_s / self.filled if self.filled > 0 else 0.0


class LimitOrderSimulator:
    """Simulates limit order fills with latency and depth checks.

    On each tick, checks if any pending order's limit price has been
    reached by the market. After a configurable latency delay, fills
    the order if depth is sufficient.
    """

    def __init__(
        self,
        fill_latency_s: float = 2.0,
        bar_seconds: float = 900.0,
    ) -> None:
        self._fill_latency_s = fill_latency_s
        self._bar_seconds = bar_seconds
        self._latency_pct = fill_latency_s / bar_seconds
        self._pending: list[_PendingOrder] = []
        self._stats = SimulatorStats()

    def place(self, order: DutchOrder) -> None:
        """Add a limit order to the pending queue."""
        self._pending.append(_PendingOrder(order=order))
        self._stats.placed += 1

    def on_tick(
        self,
        time_pct: float,
        book_up,
        book_dn,
    ) -> list[DutchFill]:
        """Process pending orders against current orderbook state.

        book_up/book_dn are TokenBook | None.
        Returns list of fills that occurred this tick.
        """
        fills: list[DutchFill] = []
        remaining: list[_PendingOrder] = []

        for po in self._pending:
            if po.state == "FILLED":
                continue

            # Get the relevant book
            book = book_up if po.order.side == "UP" else book_dn
            if book is None:
                remaining.append(po)
                continue

            ask = book.best_ask
            limit = po.order.limit_price

            if po.state == "PENDING":
                if ask <= limit:
                    # Ask has crossed our limit — start latency timer
                    po.state = "CROSSING"
                    po.cross_time_pct = time_pct
                    po.would_fill_count += 1
                remaining.append(po)

            elif po.state == "CROSSING":
                if ask > limit:
                    # Ask bounced back above our limit — back to pending
                    po.state = "PENDING"
                    remaining.append(po)
                elif time_pct - po.cross_time_pct >= self._latency_pct:
                    # Latency elapsed and ask is still at/below limit — FILL
                    fill = self._execute_fill(po, time_pct, book)
                    fills.append(fill)
                    po.state = "FILLED"
                    # Don't add to remaining (it's done)
                else:
                    remaining.append(po)

        self._pending = remaining
        return fills

    def _execute_fill(
        self, po: _PendingOrder, time_pct: float, book,
    ) -> DutchFill:
        """Execute a fill with depth checking."""
        available = self._available_at_or_below(book, po.order.limit_price)
        requested = po.order.shares

        if available <= 0:
            # Edge case: book drained between crossing and fill
            # Fill at limit price anyway (simulating aggressive)
            filled_shares = requested
            partial = False
        elif available < requested:
            filled_shares = available
            partial = True
            self._stats.partial += 1
        else:
            filled_shares = requested
            partial = False

        latency_s = (time_pct - po.cross_time_pct) * self._bar_seconds
        self._stats.filled += 1
        self._stats.total_latency_s += latency_s

        return DutchFill(
            order=po.order,
            fill_price=po.order.limit_price,
            filled_shares=round(filled_shares, 4),
            fill_time_pct=round(time_pct, 4),
            latency_s=round(latency_s, 2),
            partial=partial,
        )

    @staticmethod
    def _available_at_or_below(book, limit_price: float) -> float:
        """Sum shares available at all ask levels <= limit_price."""
        return sum(
            size for price, size in book.asks.items() if price <= limit_price
        )

    def cancel_all(self) -> list[DutchOrder]:
        """Cancel all pending orders. Returns the cancelled orders."""
        cancelled = []
        for po in self._pending:
            if po.state != "FILLED":
                cancelled.append(po.order)
                self._stats.expired += 1
                self._stats.would_fill += po.would_fill_count
        self._pending.clear()
        return cancelled

    @property
    def pending_orders(self) -> list[DutchOrder]:
        return [po.order for po in self._pending]

    @property
    def pending_states(self) -> list[tuple[DutchOrder, str]]:
        """Orders with their current state (for display)."""
        return [(po.order, po.state) for po in self._pending]

    @property
    def stats(self) -> SimulatorStats:
        return self._stats

    def reset(self) -> None:
        """Reset for next bar."""
        self._pending.clear()
        self._stats = SimulatorStats()
