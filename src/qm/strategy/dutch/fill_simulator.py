"""Limit order fill simulator V3 for dutch accumulation paper trading.

Simulates realistic maker-only (post_only=True) limit order fills:
  - Consecutive-tick fill model (N ticks at/below limit = fill, default 10 ~5s)
  - Sweep detection: instant fill when price passes through by >= 1c
  - Order chasing: cancel + re-place when market moves away (never above ask)
  - Cancel orders that drift too far (>=5c)
  - Depth-aware partial fills (buy checks asks, sell checks bids)
  - State machine: PENDING → CROSSING → FILLED | CANCELLED | EXPIRED
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from qm.strategy.dutch.engine import DutchOrder

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class DutchFill:
    """A simulated limit order fill."""

    order: DutchOrder
    fill_price: float
    filled_shares: float
    fill_time_pct: float
    fill_ticks: int
    partial: bool


@dataclass
class _PendingOrder:
    """Internal state for a pending limit order."""

    order: DutchOrder
    state: str = "PENDING"  # PENDING, CROSSING, FILLED, CANCELLED
    consecutive_ticks_at_limit: int = 0
    would_fill_count: int = 0
    chase_count: int = 0


@dataclass
class SimulatorStats:
    """Cumulative stats for the simulator."""

    placed: int = 0
    filled: int = 0
    partial: int = 0
    would_fill: int = 0
    expired: int = 0
    chased: int = 0
    chase_cancelled: int = 0  # V3: old orders replaced by chase
    cancelled: int = 0        # distance-based cancels only
    total_fill_ticks: int = 0

    @property
    def avg_fill_ticks(self) -> float:
        return self.total_fill_ticks / self.filled if self.filled > 0 else 0.0


class LimitOrderSimulator:
    """Simulates limit order fills with consecutive-tick model and chasing.

    Fill model: order fills after N consecutive ticks where ask <= limit (buy)
    or bid >= limit (sell). If price bounces, counter resets to 0.
    Sweep: if price passes through limit by >= sweep_threshold, fill on tick 1.

    Chase model: if market moves >chase_threshold from our limit, cancel
    and re-place at new bid + offset (never at/above ask). Max chase_count.
    """

    def __init__(
        self,
        fill_ticks: int = 10,
        chase_threshold: float = 0.03,
        max_chase: int = 2,
        spread_offset: float = 0.01,
        cancel_distance: float = 0.05,
        sweep_threshold: float = 0.01,
        resting_cancel_distance: float = 0.10,  # V7.4: wider for resting
    ) -> None:
        self._fill_ticks = fill_ticks
        self._chase_threshold = chase_threshold
        self._max_chase = max_chase
        self._spread_offset = spread_offset
        self._cancel_distance = cancel_distance
        self._sweep_threshold = sweep_threshold
        self._resting_cancel_distance = resting_cancel_distance
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
        """Process pending orders: chase pass then fill-check pass.

        book_up/book_dn are TokenBook | None.
        Returns list of fills that occurred this tick.
        """
        # --- Chase pass: check if market moved away (BUY orders only) ---
        for po in self._pending:
            if po.state not in ("PENDING", "CROSSING"):
                continue
            # V5: skip chase for sell orders (they sit on ask side)
            if getattr(po.order, "action", "BUY") == "SELL":
                continue
            # V7.4: Never chase resting orders — they wait for price to come
            if getattr(po.order, "order_mode", "reactive") == "resting":
                continue
            book = book_up if po.order.side == "UP" else book_dn
            if book is None or book.best_bid <= 0:
                continue

            new_limit = book.best_bid + self._spread_offset
            distance = new_limit - po.order.limit_price

            if distance > self._chase_threshold and po.chase_count < self._max_chase:
                # Chase: cancel old + re-place at new price
                new_ask = book.best_ask
                # V3: never chase TO the ask (maker principle)
                if new_limit >= new_ask:
                    new_limit = new_ask - 0.01
                # Don't chase to a worse-or-equal price
                if new_limit <= po.order.limit_price:
                    continue
                po.order = DutchOrder(
                    side=po.order.side,
                    limit_price=round(new_limit, 4),
                    shares=po.order.shares,
                    dollars=round(po.order.shares * new_limit, 2),
                    time_pct=po.order.time_pct,
                    placed_at=po.order.placed_at,
                    reason=po.order.reason + f" chase#{po.chase_count + 1}",
                    order_mode=getattr(po.order, "order_mode", "reactive"),
                )
                po.chase_count += 1
                po.state = "PENDING"
                po.consecutive_ticks_at_limit = 0
                self._stats.chased += 1
                self._stats.chase_cancelled += 1
            else:
                # V7.4: wider cancel distance for resting orders
                eff_cancel = (
                    self._resting_cancel_distance
                    if getattr(po.order, "order_mode", "reactive") == "resting"
                    else self._cancel_distance
                )
                if distance >= eff_cancel:
                    # V3: >= (was >) — cancel at exact boundary too
                    po.state = "CANCELLED"
                    po.consecutive_ticks_at_limit = 0
                    self._stats.cancelled += 1

        # --- Fill-check pass ---
        fills: list[DutchFill] = []
        remaining: list[_PendingOrder] = []

        for po in self._pending:
            if po.state in ("FILLED", "CANCELLED"):
                continue

            book = book_up if po.order.side == "UP" else book_dn
            if book is None:
                remaining.append(po)
                continue

            limit = po.order.limit_price
            is_sell = getattr(po.order, "action", "BUY") == "SELL"

            if is_sell:
                # Sell fills when bid >= limit (buyer reaches our ask price)
                bid = book.best_bid
                if bid >= limit:
                    po.consecutive_ticks_at_limit += 1
                    # V3: sweep detection — bid passed through our sell limit
                    sweep = (bid - limit) >= self._sweep_threshold
                    if sweep or po.consecutive_ticks_at_limit >= self._fill_ticks:
                        # V3: check bid-side depth before filling
                        available = self._available_at_or_above(book, limit)
                        if available <= 0:
                            po.consecutive_ticks_at_limit = 0
                            remaining.append(po)
                        else:
                            fill = self._execute_fill(po, time_pct, available)
                            fills.append(fill)
                            po.state = "FILLED"
                    else:
                        remaining.append(po)
                else:
                    if po.consecutive_ticks_at_limit > 0:
                        po.would_fill_count += 1
                    po.consecutive_ticks_at_limit = 0
                    po.state = "PENDING"
                    remaining.append(po)
            else:
                # Buy fills when ask <= limit (seller reaches our bid price)
                ask = book.best_ask
                if ask <= limit:
                    po.consecutive_ticks_at_limit += 1
                    # V3: sweep detection — ask dropped through our buy limit
                    sweep = (limit - ask) >= self._sweep_threshold
                    if sweep or po.consecutive_ticks_at_limit >= self._fill_ticks:
                        # V3: check ask-side depth before filling
                        available = self._available_at_or_below(book, limit)
                        if available <= 0:
                            po.consecutive_ticks_at_limit = 0
                            remaining.append(po)
                        else:
                            fill = self._execute_fill(po, time_pct, available)
                            fills.append(fill)
                            po.state = "FILLED"
                    else:
                        remaining.append(po)
                else:
                    if po.consecutive_ticks_at_limit > 0:
                        po.would_fill_count += 1
                    po.consecutive_ticks_at_limit = 0
                    po.state = "PENDING"
                    remaining.append(po)

        self._pending = remaining
        return fills

    def _execute_fill(
        self, po: _PendingOrder, time_pct: float, available: float,
    ) -> DutchFill:
        """Execute a fill. Caller guarantees available > 0."""
        requested = po.order.shares

        if available < requested:
            filled_shares = available
            partial = True
            self._stats.partial += 1
        else:
            filled_shares = requested
            partial = False

        self._stats.filled += 1
        self._stats.total_fill_ticks += po.consecutive_ticks_at_limit

        return DutchFill(
            order=po.order,
            fill_price=po.order.limit_price,
            filled_shares=round(filled_shares, 4),
            fill_time_pct=round(time_pct, 4),
            fill_ticks=po.consecutive_ticks_at_limit,
            partial=partial,
        )

    @staticmethod
    def _available_at_or_below(book, limit_price: float) -> float:
        """Sum shares available at all ask levels <= limit_price."""
        return sum(
            size for price, size in book.asks.items() if price <= limit_price
        )

    @staticmethod
    def _available_at_or_above(book, limit_price: float) -> float:
        """Sum shares available at all bid levels >= limit_price."""
        return sum(
            size for price, size in book.bids.items() if price >= limit_price
        )

    def cancel_all(self) -> list[DutchOrder]:
        """Cancel all pending orders. Returns the cancelled orders."""
        cancelled = []
        for po in self._pending:
            if po.state not in ("FILLED", "CANCELLED"):
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
