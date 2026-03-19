"""Live executor: places real orders on Polymarket via CLOB API.

Implements the same Executor protocol as PaperExecutor, ensuring
paper and live trading use identical decision logic.
"""

from __future__ import annotations

import logging

from qm.core.types import Outcome, PolymarketMarket, Signal
from qm.execution.loop import Fill
from qm.execution.polymarket.client import PolymarketClient
from qm.execution.polymarket.order_manager import OrderManager, OrderStatus

logger = logging.getLogger(__name__)


class LiveExecutor:
    """Executes trades on Polymarket via the CLOB API.

    Same interface as PaperExecutor (Executor protocol).
    Uses OrderManager for lifecycle management.

    Args:
        client: Authenticated Polymarket client.
        order_manager: Order lifecycle manager.
        submit: If False (dry-run mode), log orders without submitting.
    """

    def __init__(
        self,
        client: PolymarketClient,
        order_manager: OrderManager,
        submit: bool = True,
    ) -> None:
        self._client = client
        self._order_mgr = order_manager
        self._submit = submit
        self._fill_count = 0

    async def execute(
        self,
        signal: Signal,
        size_usd: float,
        market: PolymarketMarket | None = None,
    ) -> Fill:
        """Execute a trade on Polymarket.

        Converts the signal into a CLOB limit order, manages its
        lifecycle, and returns a Fill result.
        """
        if market is None:
            return Fill(price=0.0, size_usd=0.0, status="rejected")

        # Determine which token to buy
        if signal.recommended_side == Outcome.UP:
            token_id = market.token_id_up
            base_price = signal.market_prob_up
        else:
            token_id = market.token_id_down
            base_price = 1 - signal.market_prob_up

        # Maker-only pricing: bid at or below current mid
        # Subtract half the spread to ensure we're maker
        limit_price = max(0.01, min(0.99, base_price - market.spread / 2))

        # Calculate shares from USD size
        shares = size_usd / limit_price

        # Submit order via OrderManager
        managed = await self._order_mgr.submit(
            token_id=token_id,
            price=limit_price,
            size=shares,
            side="BUY",
            submit=self._submit,
        )

        if managed.status == OrderStatus.FILLED:
            self._fill_count += 1
            actual_size = managed.filled_size * managed.price
            logger.info(
                "LIVE FILL: %s %s $%.2f @ %.4f (order %s)",
                signal.asset.value, signal.recommended_side.value,
                actual_size, managed.price, managed.order_id[:12],
            )
            return Fill(
                price=managed.price,
                size_usd=actual_size,
                status="filled",
                order_id=managed.order_id,
            )

        if managed.status == OrderStatus.PARTIALLY_FILLED:
            actual_size = managed.filled_size * managed.price
            logger.info(
                "PARTIAL FILL: %s %s $%.2f/$%.2f @ %.4f",
                signal.asset.value, signal.recommended_side.value,
                actual_size, size_usd, managed.price,
            )
            return Fill(
                price=managed.price,
                size_usd=actual_size,
                status="filled",
                order_id=managed.order_id,
            )

        # Not filled (expired, cancelled, failed)
        logger.info(
            "Order not filled: %s (%s)",
            managed.order_id[:12], managed.status.value,
        )
        return Fill(
            price=0.0,
            size_usd=0.0,
            status=managed.status.value.lower(),
            order_id=managed.order_id,
        )

    @property
    def total_fills(self) -> int:
        return self._fill_count
