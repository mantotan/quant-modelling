"""Divergence live order router — bridges DivergenceEngine to Polymarket CLOB.

Non-blocking: places orders asynchronously, checks fills on each tick.
Replaces LimitOrderSimulator for live execution while maintaining the
same DutchOrder/DutchFill interface so DivergenceEngine.on_fill() works
identically in paper and live modes.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field

from qm.execution.polymarket.client import PolymarketClient
from qm.strategy.dutch.engine import DutchOrder
from qm.strategy.dutch.fill_simulator import DutchFill

logger = logging.getLogger(__name__)


@dataclass
class _TrackedOrder:
    """Internal tracking for a live CLOB order."""

    dutch_order: DutchOrder
    clob_order_id: str = ""
    token_id: str = ""
    placed_at: float = 0.0
    last_checked: float = 0.0
    filled_size: float = 0.0
    status: str = "pending"  # pending, placed, filled, cancelled, failed


class DivergenceLiveRouter:
    """Routes DutchOrder decisions to real Polymarket CLOB.

    Non-blocking design:
    - place() submits to CLOB and returns immediately
    - check_fills() polls for fill updates (call each tick)
    - cancel_all() cancels all pending orders (call on bar end)
    """

    def __init__(
        self,
        client: PolymarketClient,
        *,
        dry_run: bool = False,
        cancel_timeout: float = 120.0,
    ) -> None:
        self._client = client
        self._dry_run = dry_run
        self._cancel_timeout = cancel_timeout
        self._pending: dict[str, _TrackedOrder] = {}
        self._current_market: object | None = None  # PolymarketMarket
        self._failed_count: int = 0  # Background failures, drain in check_fills
        self._order_counter: int = 0
        self._stats = {"placed": 0, "filled": 0, "cancelled": 0, "failed": 0}

    def set_market(self, market: object) -> None:
        """Update market reference on each bar transition.

        Must be called before placing orders — token_ids change every bar.
        """
        self._current_market = market

    async def place(self, order: DutchOrder) -> str | None:
        """Submit limit order to CLOB. Non-blocking for live orders.

        Dry-run: returns immediately with fake order_id.
        Live: fires CLOB API call as background task, returns placeholder ID.
        Call check_fills() on subsequent ticks to detect fills.
        """
        if not self._current_market:
            logger.warning("No market set — cannot place live order")
            return None

        token_id_up = getattr(self._current_market, "token_id_up", "")
        token_id_dn = getattr(self._current_market, "token_id_down",
                              getattr(self._current_market, "token_id_dn", ""))

        token_id = token_id_up if order.side == "UP" else token_id_dn
        if not token_id:
            logger.warning("Missing token_id for %s", order.side)
            return None

        clob_side = "BUY" if order.action == "BUY" else "SELL"
        tracked = _TrackedOrder(
            dutch_order=order,
            token_id=token_id,
            placed_at=time.monotonic(),
        )

        if self._dry_run:
            self._order_counter += 1
            tracked.clob_order_id = f"dry-{self._order_counter}"
            tracked.status = "filled"
            tracked.filled_size = order.shares
            self._pending[tracked.clob_order_id] = tracked
            self._stats["placed"] += 1
            logger.info(
                "DRY-RUN: %s %s %.1fsh @ $%.4f",
                clob_side, order.side, order.shares, order.limit_price,
            )
            return tracked.clob_order_id

        # Fire-and-forget: submit to CLOB in background, don't block tick loop
        import asyncio

        self._order_counter += 1
        placeholder_id = f"pending-{self._order_counter}"
        tracked.clob_order_id = placeholder_id
        tracked.status = "submitting"
        self._pending[placeholder_id] = tracked
        # Don't increment stats["placed"] yet — wait for confirmation

        asyncio.get_event_loop().run_in_executor(
            None, self._submit_order_sync, tracked, token_id, clob_side, placeholder_id,
        )

        logger.info(
            "LIVE order (async): %s %s %.1fsh @ $%.4f",
            clob_side, order.side, order.shares, order.limit_price,
        )
        return placeholder_id

    def _submit_order_sync(
        self, tracked: _TrackedOrder, token_id: str, clob_side: str, placeholder_id: str,
    ) -> None:
        """Submit order to CLOB synchronously (runs in thread pool)."""
        try:
            result = self._client.create_and_post_order(
                token_id=token_id,
                price=tracked.dutch_order.limit_price,
                size=tracked.dutch_order.shares,
                side=clob_side,
                post_only=True,
            )
            order_id = result.get("orderID", result.get("id", ""))
            # Update tracked order with real CLOB order_id
            tracked.clob_order_id = order_id
            tracked.status = "placed"
            # Move from placeholder to real ID in pending dict
            self._pending.pop(placeholder_id, None)
            self._pending[order_id] = tracked
            logger.info(
                "LIVE order confirmed: %s %s → %s",
                clob_side, tracked.dutch_order.side,
                order_id[:16] if order_id else "no-id",
            )
        except Exception as e:
            tracked.status = "failed"
            self._pending.pop(placeholder_id, None)
            self._stats["failed"] += 1
            self._failed_count += 1  # Track failures for safety decrement
            logger.warning(
                "LIVE order failed: %s %s @ $%.4f: %s",
                clob_side, tracked.dutch_order.side,
                tracked.dutch_order.limit_price, e,
            )

    def drain_failures(self) -> int:
        """Return and reset count of background order failures.

        Caller should decrement safety open_orders by this count.
        """
        count = self._failed_count
        self._failed_count = 0
        return count

    async def check_fills(self) -> list[DutchFill]:
        """Poll CLOB for fill updates on pending orders.

        Call this once per tick. Returns list of new fills since last check.
        """
        fills: list[DutchFill] = []
        now = time.monotonic()

        for order_id, tracked in list(self._pending.items()):
            # Dry-run: instant fill
            if self._dry_run and tracked.status == "filled":
                fill = DutchFill(
                    order=tracked.dutch_order,
                    fill_price=tracked.dutch_order.limit_price,
                    filled_shares=tracked.filled_size,
                )
                fills.append(fill)
                del self._pending[order_id]
                self._stats["filled"] += 1
                continue

            # Skip orders still being submitted to CLOB (background thread)
            if tracked.status == "submitting":
                continue

            # Skip failed orders (background thread marked them)
            if tracked.status == "failed":
                del self._pending[order_id]
                continue

            # Skip recently checked (throttle API calls)
            if now - tracked.last_checked < 2.0:
                continue
            tracked.last_checked = now

            # Check timeout
            elapsed = now - tracked.placed_at
            if elapsed > self._cancel_timeout:
                await self._cancel_order(order_id)
                tracked.status = "cancelled"
                del self._pending[order_id]
                self._stats["cancelled"] += 1
                continue

            # Poll CLOB
            try:
                status = self._client.get_order(order_id)
                api_status = (status.get("status", "") or "").upper()

                if api_status == "MATCHED":
                    tracked.status = "filled"
                    tracked.filled_size = tracked.dutch_order.shares
                    fill = DutchFill(
                        order=tracked.dutch_order,
                        fill_price=tracked.dutch_order.limit_price,
                        filled_shares=tracked.filled_size,
                    )
                    fills.append(fill)
                    del self._pending[order_id]
                    self._stats["filled"] += 1
                    logger.info(
                        "LIVE fill: %s %s %.1fsh @ $%.4f",
                        tracked.dutch_order.action,
                        tracked.dutch_order.side,
                        tracked.filled_size,
                        tracked.dutch_order.limit_price,
                    )
                elif api_status == "CANCELED":
                    tracked.status = "cancelled"
                    del self._pending[order_id]
                    self._stats["cancelled"] += 1
                elif api_status in ("LIVE", "OPEN"):
                    # Check partial fills
                    filled = float(status.get("size_matched", 0))
                    if filled > tracked.filled_size:
                        new_fill = filled - tracked.filled_size
                        tracked.filled_size = filled
                        fill = DutchFill(
                            order=tracked.dutch_order,
                            fill_price=tracked.dutch_order.limit_price,
                            filled_shares=new_fill,
                        )
                        fills.append(fill)
                        logger.info(
                            "LIVE partial fill: %s %s +%.1fsh (total %.1f/%.1f)",
                            tracked.dutch_order.side,
                            tracked.dutch_order.action,
                            new_fill, tracked.filled_size,
                            tracked.dutch_order.shares,
                        )
            except Exception as e:
                logger.debug("Fill check failed for %s: %s", order_id[:12], e)

        return fills

    async def cancel_all(self) -> list[DutchOrder]:
        """Cancel all pending orders on CLOB. Called on bar end."""
        cancelled: list[DutchOrder] = []
        for order_id, tracked in list(self._pending.items()):
            if tracked.status == "placed":
                await self._cancel_order(order_id)
            cancelled.append(tracked.dutch_order)
            self._stats["cancelled"] += 1
        self._pending.clear()
        return cancelled

    async def cancel_all_open_orders(self) -> int:
        """Startup crash recovery: cancel ALL open orders for this account.

        Call once on startup to clean up any orders left from a previous crash.
        """
        try:
            result = self._client.cancel_all()
            count = len(result) if isinstance(result, list) else result.get("cancelled", 0)
            if count:
                logger.info("Startup: cancelled %d stale CLOB orders", count)
            return count
        except Exception as e:
            logger.warning("Startup cancel-all failed: %s", e)
            return 0

    async def _cancel_order(self, order_id: str) -> None:
        """Cancel a single order on CLOB."""
        if self._dry_run:
            return
        try:
            self._client.cancel_order(order_id)
        except Exception as e:
            logger.debug("Cancel failed for %s: %s", order_id[:12], e)

    @property
    def pending_count(self) -> int:
        return len(self._pending)

    @property
    def stats(self) -> dict:
        return dict(self._stats)
