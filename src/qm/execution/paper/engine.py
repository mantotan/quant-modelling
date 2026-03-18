"""Paper trading executor: simulates fills without real orders.

Same interface as LiveExecutor. Pessimistic fill assumption:
always cross the spread (worst-case entry price).
"""

from __future__ import annotations

import logging
from typing import Any

from qm.core.types import Outcome, PolymarketMarket, Signal
from qm.execution.loop import Fill

logger = logging.getLogger(__name__)


class PaperExecutor:
    """Simulates order execution for paper trading.

    Fill price = market_price + spread/2 (pessimistic: always cross the spread).
    No network calls, instant return.
    """

    def __init__(self) -> None:
        self._fill_count = 0

    async def execute(
        self,
        signal: Signal,
        size_usd: float,
        market: PolymarketMarket | None = None,
    ) -> Fill:
        """Simulate a fill at pessimistic price."""
        # Buy price is the side we're buying
        if signal.recommended_side == Outcome.UP:
            base_price = signal.market_prob_up
        else:
            base_price = 1 - signal.market_prob_up

        # Pessimistic: cross the spread
        spread = market.spread if market else 0.02
        fill_price = min(0.99, max(0.01, base_price + spread / 2))

        self._fill_count += 1
        order_id = f"paper-{self._fill_count}"

        logger.debug(
            "Paper fill: %s %s $%.2f @ %.4f",
            signal.asset.value, signal.recommended_side.value,
            size_usd, fill_price,
        )

        return Fill(
            price=fill_price,
            size_usd=size_usd,
            status="filled",
            order_id=order_id,
        )

    @property
    def total_fills(self) -> int:
        return self._fill_count
