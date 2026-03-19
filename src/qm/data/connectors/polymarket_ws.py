"""Polymarket CLOB websocket: real-time orderbook + trade feed.

Subscribes to wss://ws-subscriptions-clob.polymarket.com/ws/market
for live bid/ask/trade data on specific token IDs.
No authentication required.

Usage:
    feed = PolymarketWSFeed()
    await feed.connect()
    await feed.subscribe(token_id_up, token_id_down)
    # feed.best_bid, feed.best_ask, feed.mid, feed.spread updated in real-time
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field

import aiohttp

logger = logging.getLogger(__name__)

WS_URL = "wss://ws-subscriptions-clob.polymarket.com/ws/market"
PING_INTERVAL = 10.0  # Send PING every 10s per docs


@dataclass
class TokenBook:
    """Live orderbook state for one token."""

    token_id: str
    best_bid: float = 0.0
    best_ask: float = 1.0
    last_trade: float = 0.5
    bids: dict[float, float] = field(default_factory=dict)  # price → size
    asks: dict[float, float] = field(default_factory=dict)

    @property
    def mid(self) -> float:
        if self.best_bid > 0 and self.best_ask < 1:
            return (self.best_bid + self.best_ask) / 2
        return self.last_trade

    @property
    def spread(self) -> float:
        if self.best_bid > 0 and self.best_ask < 1:
            return self.best_ask - self.best_bid
        return 0.02  # default spread when no orderbook

    def apply_book(self, bids: list[dict], asks: list[dict]) -> None:
        """Apply a full orderbook snapshot."""
        self.bids.clear()
        self.asks.clear()
        for b in bids:
            price = float(b["price"])
            size = float(b["size"])
            if size > 0:
                self.bids[price] = size
        for a in asks:
            price = float(a["price"])
            size = float(a["size"])
            if size > 0:
                self.asks[price] = size
        self._update_bbo()

    def apply_price_change(
        self, price: float, size: float, side: str,
    ) -> None:
        """Apply incremental price level update."""
        book = self.bids if side == "BUY" else self.asks
        if size <= 0:
            book.pop(price, None)
        else:
            book[price] = size
        self._update_bbo()

    def _update_bbo(self) -> None:
        """Recompute best bid/ask from orderbook."""
        if self.bids:
            self.best_bid = max(self.bids.keys())
        else:
            self.best_bid = 0.0
        if self.asks:
            self.best_ask = min(self.asks.keys())
        else:
            self.best_ask = 1.0


class PolymarketWSFeed:
    """Real-time Polymarket CLOB orderbook feed.

    Maintains live TokenBook for Up and Down tokens.
    Exposes mid_up, spread, best_bid_up, best_ask_up for the scanner.
    """

    def __init__(self) -> None:
        self._books: dict[str, TokenBook] = {}
        self._ws: aiohttp.ClientWebSocketResponse | None = None
        self._session: aiohttp.ClientSession | None = None
        self._running = False
        self._connected = asyncio.Event()
        self._token_id_up: str | None = None
        self._token_id_down: str | None = None

    @property
    def mid_up(self) -> float:
        if self._token_id_up and self._token_id_up in self._books:
            return self._books[self._token_id_up].mid
        return 0.5

    @property
    def spread(self) -> float:
        if self._token_id_up and self._token_id_up in self._books:
            return self._books[self._token_id_up].spread
        return 0.02

    @property
    def best_bid_up(self) -> float:
        if self._token_id_up and self._token_id_up in self._books:
            return self._books[self._token_id_up].best_bid
        return 0.0

    @property
    def best_ask_up(self) -> float:
        if self._token_id_up and self._token_id_up in self._books:
            return self._books[self._token_id_up].best_ask
        return 1.0

    async def connect_and_run(
        self,
        token_id_up: str,
        token_id_down: str,
        running_flag: list[bool],
    ) -> None:
        """Connect, subscribe, and process messages until stopped.

        Auto-reconnects on disconnect.
        """
        self._token_id_up = token_id_up
        self._token_id_down = token_id_down
        self._books[token_id_up] = TokenBook(token_id=token_id_up)
        self._books[token_id_down] = TokenBook(token_id=token_id_down)
        self._running = True

        while running_flag[0] and self._running:
            try:
                await self._run_once(token_id_up, token_id_down, running_flag)
            except Exception:
                logger.warning("Polymarket WS disconnected, reconnecting in 5s...")
                self._connected.clear()
                await asyncio.sleep(5.0)

    async def _run_once(
        self,
        token_id_up: str,
        token_id_down: str,
        running_flag: list[bool],
    ) -> None:
        self._session = aiohttp.ClientSession()
        try:
            self._ws = await self._session.ws_connect(
                WS_URL, heartbeat=PING_INTERVAL,
            )

            # Subscribe to both tokens
            sub_msg = json.dumps({
                "assets_ids": [token_id_up, token_id_down],
                "type": "market",
                "initial_dump": True,
                "level": 2,
            })
            await self._ws.send_str(sub_msg)
            logger.info(
                "Polymarket WS subscribed: up=%s... down=%s...",
                token_id_up[:16], token_id_down[:16],
            )
            self._connected.set()

            # Start heartbeat
            ping_task = asyncio.create_task(self._ping_loop())

            try:
                async for msg in self._ws:
                    if not running_flag[0]:
                        break
                    if msg.type == aiohttp.WSMsgType.TEXT:
                        if msg.data == "PONG":
                            continue
                        self._handle_message(msg.data)
                    elif msg.type in (
                        aiohttp.WSMsgType.CLOSED,
                        aiohttp.WSMsgType.ERROR,
                    ):
                        break
            finally:
                ping_task.cancel()
                await self._ws.close()
        finally:
            await self._session.close()
            self._session = None

    async def _ping_loop(self) -> None:
        while self._running:
            try:
                if self._ws and not self._ws.closed:
                    await self._ws.send_str("PING")
            except Exception:
                pass
            await asyncio.sleep(PING_INTERVAL)

    def _handle_message(self, raw: str) -> None:
        """Parse and apply a websocket message."""
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return

        # Can be a single event or array of events
        events = data if isinstance(data, list) else [data]

        for event in events:
            event_type = event.get("event_type", "")
            asset_id = event.get("asset_id", "")

            if asset_id not in self._books:
                continue

            book = self._books[asset_id]

            if event_type == "book":
                book.apply_book(
                    event.get("bids", []),
                    event.get("asks", []),
                )
                logger.debug(
                    "Book snapshot %s...: bid=%.3f ask=%.3f spread=%.4f",
                    asset_id[:12], book.best_bid, book.best_ask, book.spread,
                )

            elif event_type == "price_change":
                for pc in event.get("price_changes", []):
                    book.apply_price_change(
                        float(pc["price"]),
                        float(pc["size"]),
                        pc.get("side", "BUY"),
                    )

            elif event_type == "last_trade_price":
                book.last_trade = float(event.get("price", book.last_trade))

    def stop(self) -> None:
        self._running = False
        self._connected.clear()
