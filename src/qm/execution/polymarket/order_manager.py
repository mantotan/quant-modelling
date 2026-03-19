"""Order lifecycle manager: submit, monitor, re-price, cancel.

Handles the full lifecycle of a Polymarket limit order:
PENDING → PLACED → PARTIALLY_FILLED → FILLED | CANCELLED | EXPIRED
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from enum import Enum

from qm.execution.polymarket.client import PolymarketClient

logger = logging.getLogger(__name__)


class OrderStatus(str, Enum):
    PENDING = "PENDING"
    PLACED = "PLACED"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"
    EXPIRED = "EXPIRED"
    FAILED = "FAILED"


@dataclass
class ManagedOrder:
    """Tracks the state of an order through its lifecycle."""

    order_id: str = ""
    token_id: str = ""
    side: str = ""
    price: float = 0.0
    size: float = 0.0
    filled_size: float = 0.0
    status: OrderStatus = OrderStatus.PENDING
    placed_at: float = 0.0
    last_checked: float = 0.0
    reprice_count: int = 0


class OrderManager:
    """Manages Polymarket order lifecycle with heartbeat monitoring.

    Features:
    - Submit maker-only limit orders
    - Heartbeat: check order status every 10s
    - Auto-cancel after timeout (default 60s)
    - Re-pricing: tighten price after 30s if unfilled
    - Max slippage protection
    """

    def __init__(
        self,
        client: PolymarketClient,
        heartbeat_interval: float = 10.0,
        cancel_timeout: float = 60.0,
        reprice_after: float = 30.0,
        max_reprice_count: int = 2,
        max_slippage: float = 0.02,
    ) -> None:
        self._client = client
        self._heartbeat_interval = heartbeat_interval
        self._cancel_timeout = cancel_timeout
        self._reprice_after = reprice_after
        self._max_reprice_count = max_reprice_count
        self._max_slippage = max_slippage
        self._active_orders: dict[str, ManagedOrder] = {}
        self._fill_count = 0

    async def submit(
        self,
        token_id: str,
        price: float,
        size: float,
        side: str = "BUY",
        submit: bool = True,
    ) -> ManagedOrder:
        """Submit a limit order and manage its lifecycle.

        Args:
            token_id: Polymarket token ID.
            price: Limit price.
            size: Number of shares.
            side: "BUY" or "SELL".
            submit: If False (dry-run mode), log but don't submit.

        Returns:
            ManagedOrder with final status.
        """
        order = ManagedOrder(
            token_id=token_id,
            side=side,
            price=price,
            size=size,
            placed_at=time.monotonic(),
        )

        if not submit:
            logger.info(
                "DRY-RUN: would submit %s %.0f @ %.4f on %s",
                side, size, price, token_id[:12],
            )
            order.status = OrderStatus.FILLED
            order.filled_size = size
            order.order_id = f"dry-run-{self._fill_count}"
            self._fill_count += 1
            return order

        try:
            result = self._client.create_and_post_order(
                token_id=token_id,
                price=price,
                size=size,
                side=side,
                post_only=True,
            )
            order.order_id = result.get("orderID", result.get("id", ""))
            order.status = OrderStatus.PLACED
            self._active_orders[order.order_id] = order
            logger.info(
                "Order placed: %s %s %.0f @ %.4f → %s",
                side, token_id[:12], size, price, order.order_id[:12],
            )
        except Exception as e:
            order.status = OrderStatus.FAILED
            logger.error("Order submission failed: %s", e)
            return order

        # Monitor until filled, cancelled, or timed out
        return await self._monitor(order)

    async def _monitor(self, order: ManagedOrder) -> ManagedOrder:
        """Monitor order until terminal state."""
        original_price = order.price

        while order.status in (OrderStatus.PLACED, OrderStatus.PARTIALLY_FILLED):
            await asyncio.sleep(self._heartbeat_interval)
            elapsed = time.monotonic() - order.placed_at

            # Check timeout
            if elapsed > self._cancel_timeout:
                await self._cancel(order)
                order.status = OrderStatus.EXPIRED
                logger.info(
                    "Order expired (%.0fs): %s", elapsed, order.order_id[:12],
                )
                break

            # Check for re-pricing opportunity
            if (
                elapsed > self._reprice_after
                and order.reprice_count < self._max_reprice_count
                and order.status == OrderStatus.PLACED
            ):
                new_price = self._compute_reprice(
                    order.price, order.side, original_price,
                )
                if new_price is not None:
                    await self._reprice(order, new_price)

            # Poll order status
            try:
                status = self._client.get_order(order.order_id)
                api_status = status.get("status", "").upper()

                if api_status == "MATCHED":
                    order.status = OrderStatus.FILLED
                    order.filled_size = order.size
                    self._fill_count += 1
                    logger.info(
                        "Order filled: %s @ %.4f",
                        order.order_id[:12], order.price,
                    )
                elif api_status == "CANCELED":
                    order.status = OrderStatus.CANCELLED
                elif api_status in ("LIVE", "OPEN"):
                    # Check partial fills
                    filled = float(status.get("size_matched", 0))
                    if filled > order.filled_size:
                        order.filled_size = filled
                        order.status = OrderStatus.PARTIALLY_FILLED
            except Exception as e:
                logger.warning(
                    "Status check failed for %s: %s",
                    order.order_id[:12], e,
                )

            order.last_checked = time.monotonic()

        # Clean up
        self._active_orders.pop(order.order_id, None)
        return order

    def _compute_reprice(
        self, current_price: float, side: str, original_price: float,
    ) -> float | None:
        """Compute a tighter price for re-pricing."""
        step = 0.005  # 0.5 cent tighter each time
        if side == "BUY":
            new_price = current_price + step
            # Don't exceed original + max_slippage
            if new_price > original_price + self._max_slippage:
                return None
            return min(0.99, new_price)
        else:
            new_price = current_price - step
            if new_price < original_price - self._max_slippage:
                return None
            return max(0.01, new_price)

    async def _reprice(
        self, order: ManagedOrder, new_price: float,
    ) -> None:
        """Cancel and re-place at a tighter price."""
        try:
            await self._cancel(order)
            result = self._client.create_and_post_order(
                token_id=order.token_id,
                price=new_price,
                size=order.size - order.filled_size,
                side=order.side,
                post_only=True,
            )
            old_id = order.order_id
            order.order_id = result.get("orderID", result.get("id", ""))
            order.price = new_price
            order.status = OrderStatus.PLACED
            order.reprice_count += 1
            self._active_orders.pop(old_id, None)
            self._active_orders[order.order_id] = order
            logger.info(
                "Re-priced: %.4f → %.4f (%s → %s)",
                order.price, new_price,
                old_id[:12], order.order_id[:12],
            )
        except Exception as e:
            logger.warning("Re-price failed: %s", e)

    async def _cancel(self, order: ManagedOrder) -> None:
        """Cancel an order."""
        try:
            self._client.cancel_order(order.order_id)
        except Exception as e:
            logger.warning(
                "Cancel failed for %s: %s", order.order_id[:12], e,
            )

    @property
    def fill_count(self) -> int:
        return self._fill_count

    @property
    def active_count(self) -> int:
        return len(self._active_orders)
