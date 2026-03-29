"""ccxt Pro websocket connector for exchange trade data.

Subscribes to raw trades via watch_trades() and streams them to handlers.
Builds OHLCV from raw trades (not exchange bars) for precise alignment.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import ccxt.pro

from qm.data.connectors.base import BaseConnector

logger = logging.getLogger(__name__)


class CcxtWebsocketConnector(BaseConnector):
    """Async websocket connector using ccxt Pro.

    Subscribes to raw trade streams for specified symbols and forwards
    trade data to registered handlers. Auto-reconnects on failure with
    exponential backoff.
    """

    def __init__(
        self,
        exchange_id: str,
        api_key: str | None = None,
        api_secret: str | None = None,
        heartbeat_timeout: float = 30.0,
    ) -> None:
        super().__init__(name=f"ccxt-{exchange_id}", heartbeat_timeout=heartbeat_timeout)
        self._exchange_id = exchange_id
        self._api_key = api_key
        self._api_secret = api_secret
        self._exchange: Any | None = None
        self._tasks: list[asyncio.Task[None]] = []

    async def connect(self) -> None:
        """Initialize the ccxt Pro exchange instance."""
        exchange_class = getattr(ccxt.pro, self._exchange_id)
        config: dict[str, Any] = {
            "enableRateLimit": True,
            "options": {"defaultType": "spot"},
        }
        if self._api_key:
            config["apiKey"] = self._api_key
        if self._api_secret:
            config["secret"] = self._api_secret

        self._exchange = exchange_class(config)
        self._running = True
        logger.info("Connected", extra={"exchange": self._exchange_id})

    async def disconnect(self) -> None:
        """Cancel all trade loops and close the exchange connection."""
        self._running = False
        for task in self._tasks:
            task.cancel()

        # Wait for tasks to finish
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()

        if self._exchange:
            await self._exchange.close()
            self._exchange = None

        self._healthy = False
        logger.info("Disconnected", extra={"exchange": self._exchange_id})

    async def subscribe_trades(self, symbols: list[str]) -> None:
        """Start a trade watch loop per symbol."""
        if not self._exchange:
            msg = "Must call connect() before subscribe_trades()"
            raise RuntimeError(msg)

        for symbol in symbols:
            task = asyncio.create_task(
                self._trade_loop(symbol),
                name=f"trades-{self._exchange_id}-{symbol}",
            )
            self._tasks.append(task)

        logger.info(
            "Subscribed to trades",
            extra={"exchange": self._exchange_id, "symbols": symbols},
        )

    async def _trade_loop(self, symbol: str) -> None:
        """Continuous loop watching trades for a single symbol.

        On network error: reconnect with exponential backoff.
        On any other error: log and continue.
        """
        while self._running:
            try:
                if self._exchange is None:
                    break
                trades = await self._exchange.watch_trades(symbol)
                self._record_heartbeat(symbol)
                await self._notify_trade_handlers(symbol, trades)

            except ccxt.NetworkError as e:
                if not self._running:
                    break
                delay = self._backoff_seconds()
                logger.warning(
                    "Network error, reconnecting",
                    extra={
                        "exchange": self._exchange_id,
                        "symbol": symbol,
                        "error": str(e),
                        "backoff_s": delay,
                    },
                )
                self._healthy = False
                await asyncio.sleep(delay)

            except asyncio.CancelledError:
                break

            except Exception:
                if not self._running:
                    break
                logger.exception(
                    "Unexpected error in trade loop",
                    extra={"exchange": self._exchange_id, "symbol": symbol},
                )
                await asyncio.sleep(1.0)

    async def fetch_recent_trades(self, symbol: str, limit: int = 1000) -> list[dict[str, Any]]:
        """REST fallback: fetch recent trades to fill gaps after reconnection."""
        if not self._exchange:
            msg = "Exchange not connected"
            raise RuntimeError(msg)
        return await self._exchange.fetch_trades(symbol, limit=limit)
