"""Orchestrates all data connectors and ingestion components.

The IngestionManager is the top-level coordinator that:
1. Creates and connects exchange connectors
2. Wires up trade handlers and bar builders
3. Starts health monitoring
4. Manages lifecycle (start/stop)
"""

from __future__ import annotations

import logging
from typing import Any

from qm.core.constants import EXCHANGE_SYMBOLS, SUPPORTED_ASSETS, SUPPORTED_TIMEFRAMES
from qm.core.events import EventBus
from qm.core.secrets import get_secret
from qm.data.connectors.base import BaseConnector
from qm.data.connectors.ccxt_ws import CcxtWebsocketConnector
from qm.data.connectors.health import HealthMonitor
from qm.data.ingestion.bar_builder import BarBuilder
from qm.data.ingestion.trade_handler import TradeHandler

logger = logging.getLogger(__name__)


class IngestionManager:
    """Top-level manager for real-time data ingestion.

    Manages the lifecycle of:
    - Exchange websocket connectors (Binance, Bybit)
    - Bar construction pipeline
    - Health monitoring
    """

    def __init__(self, event_bus: EventBus, config: dict[str, Any] | None = None) -> None:
        self._event_bus = event_bus
        self._config = config or {}
        self._connectors: list[BaseConnector] = []
        self._bar_builder: BarBuilder | None = None
        self._trade_handler: TradeHandler | None = None
        self._health_monitor: HealthMonitor | None = None

    async def start(self) -> None:
        """Initialize and start all data ingestion components."""
        # 1. Build bar builder
        self._bar_builder = BarBuilder(
            assets=SUPPORTED_ASSETS,
            timeframes=SUPPORTED_TIMEFRAMES,
        )

        # 2. Create trade handler
        self._trade_handler = TradeHandler(
            bar_builder=self._bar_builder,
            event_bus=self._event_bus,
        )

        # 3. Create exchange connectors
        exchanges = self._config.get("exchanges", ["binance"])
        for exchange_id in exchanges:
            connector = CcxtWebsocketConnector(
                exchange_id=exchange_id,
                api_key=get_secret(f"{exchange_id.upper()}_API_KEY", required=False),
                api_secret=get_secret(f"{exchange_id.upper()}_API_SECRET", required=False),
            )
            await connector.connect()

            # Register trade handler
            connector.on_trade(self._trade_handler.handle_trades)

            # Subscribe to all supported symbols
            symbols = list(EXCHANGE_SYMBOLS.values())
            await connector.subscribe_trades(symbols)

            self._connectors.append(connector)

        # 4. Start health monitoring
        self._health_monitor = HealthMonitor(
            connectors=self._connectors,
            event_bus=self._event_bus,
        )
        await self._health_monitor.start()

        logger.info(
            "Ingestion started",
            extra={
                "exchanges": exchanges,
                "assets": [a.value for a in SUPPORTED_ASSETS],
                "timeframes": [t.value for t in SUPPORTED_TIMEFRAMES],
            },
        )

    async def stop(self) -> None:
        """Gracefully shut down all ingestion components."""
        if self._health_monitor:
            await self._health_monitor.stop()

        # Flush any in-progress bars
        if self._bar_builder:
            flushed = self._bar_builder.flush_all()
            if flushed:
                logger.info(f"Flushed {len(flushed)} incomplete bars on shutdown")

        for connector in self._connectors:
            await connector.disconnect()

        self._connectors.clear()
        logger.info("Ingestion stopped")

    @property
    def is_healthy(self) -> bool:
        if self._health_monitor:
            return all(self._health_monitor.status().values())
        return False
