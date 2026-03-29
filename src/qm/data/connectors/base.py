"""Base connector interface and shared utilities."""

from __future__ import annotations

import asyncio
import logging
import time
from abc import ABC, abstractmethod
from collections.abc import Callable, Coroutine
from typing import Any

logger = logging.getLogger(__name__)

TradeCallback = Callable[..., Coroutine[Any, Any, None]]


class BaseConnector(ABC):
    """Base class for all exchange/data source connectors.

    Provides:
    - Health monitoring via heartbeat tracking
    - Exponential backoff reconnection
    - Handler registration for trade/book events
    """

    def __init__(self, name: str, heartbeat_timeout: float = 30.0) -> None:
        self.name = name
        self._running = False
        self._healthy = False
        self._heartbeat_timeout = heartbeat_timeout
        self._last_msg_time: dict[str, float] = {}
        self._trade_handlers: list[TradeCallback] = []
        self._backoff_attempt = 0
        self._max_backoff = 60.0

    @abstractmethod
    async def connect(self) -> None: ...

    @abstractmethod
    async def disconnect(self) -> None: ...

    @abstractmethod
    async def subscribe_trades(self, symbols: list[str]) -> None: ...

    def on_trade(self, handler: TradeCallback) -> None:
        """Register a handler to be called on each trade batch."""
        self._trade_handlers.append(handler)

    def is_healthy(self) -> bool:
        """Check if all subscribed symbols have recent data."""
        if not self._last_msg_time:
            return False
        now = time.monotonic()
        return all(
            now - t < self._heartbeat_timeout
            for t in self._last_msg_time.values()
        )

    def _record_heartbeat(self, symbol: str) -> None:
        self._last_msg_time[symbol] = time.monotonic()
        self._healthy = True
        self._backoff_attempt = 0

    def _backoff_seconds(self) -> float:
        """Exponential backoff: 1, 2, 4, 8, ... capped at max_backoff."""
        delay = min(2 ** self._backoff_attempt, self._max_backoff)
        self._backoff_attempt += 1
        return delay

    async def _notify_trade_handlers(
        self, symbol: str, trades: list[dict[str, Any]]
    ) -> None:
        for handler in self._trade_handlers:
            try:
                await handler(symbol, trades)
            except Exception:
                logger.exception(
                    "Trade handler error",
                    extra={"connector": self.name, "symbol": symbol},
                )
