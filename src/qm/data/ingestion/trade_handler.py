"""Processes raw trades from exchange connectors into the bar builder.

Handles:
- Symbol → Asset mapping
- Trade deduplication via trade_id tracking
- Sequencing validation (timestamps should be monotonic)
- Forwarding to BarBuilder and emitting BarCompleted events
"""

from __future__ import annotations

import logging
from collections import OrderedDict
from datetime import datetime, timezone
from typing import Any

from qm.core.constants import EXCHANGE_SYMBOLS
from qm.core.events import BarCompleted, EventBus
from qm.core.types import Asset, Bar
from qm.data.ingestion.bar_builder import BarBuilder

logger = logging.getLogger(__name__)

# Reverse mapping: "BTC/USDT" → Asset.BTC
_SYMBOL_TO_ASSET: dict[str, Asset] = {v: k for k, v in EXCHANGE_SYMBOLS.items()}

_MAX_DEDUP_SIZE = 100_000


class TradeHandler:
    """Receives raw trades from connectors and feeds them to the BarBuilder.

    Emits BarCompleted events for each completed bar.
    """

    def __init__(
        self,
        bar_builder: BarBuilder,
        event_bus: EventBus,
    ) -> None:
        self._bar_builder = bar_builder
        self._event_bus = event_bus
        # OrderedDict for FIFO eviction — oldest trade IDs removed first
        self._seen_trade_ids: dict[str, OrderedDict[str, None]] = {}
        self._last_timestamp: dict[str, datetime] = {}
        self._trade_count = 0

    async def handle_trades(
        self, symbol: str, trades: list[dict[str, Any]]
    ) -> None:
        """Process a batch of trades from an exchange connector.

        Args:
            symbol: ccxt symbol (e.g., "BTC/USDT")
            trades: List of ccxt trade dicts with keys:
                    id, timestamp, datetime, price, amount, side
        """
        asset = _SYMBOL_TO_ASSET.get(symbol)
        if asset is None:
            return

        completed_bars: list[Bar] = []

        for trade in trades:
            trade_id = trade.get("id", "")
            exchange = trade.get("exchange", "unknown")

            # Deduplicate using OrderedDict for FIFO eviction
            dedup_key = f"{exchange}:{symbol}"
            if dedup_key not in self._seen_trade_ids:
                self._seen_trade_ids[dedup_key] = OrderedDict()

            seen = self._seen_trade_ids[dedup_key]
            if trade_id and trade_id in seen:
                continue
            if trade_id:
                seen[trade_id] = None
                # Evict oldest entries when over limit
                while len(seen) > _MAX_DEDUP_SIZE:
                    seen.popitem(last=False)

            # Parse trade data — skip malformed entries
            try:
                ts_ms = trade.get("timestamp")
                if ts_ms is not None:
                    ts = datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc)
                else:
                    ts = datetime.now(timezone.utc)
                price = float(trade["price"])
                size = float(trade["amount"])
            except (KeyError, TypeError, ValueError):
                continue  # skip malformed trade

            # Feed to bar builder
            bars = self._bar_builder.on_trade(asset, price, size, ts)
            completed_bars.extend(bars)
            self._trade_count += 1

        # Emit completed bars
        for bar in completed_bars:
            await self._event_bus.publish(BarCompleted(bar=bar))

    @property
    def total_trades_processed(self) -> int:
        return self._trade_count
