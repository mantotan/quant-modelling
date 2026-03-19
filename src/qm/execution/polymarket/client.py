"""Polymarket CLOB client wrapper with retry, rate limiting, and secret redaction.

Wraps py_clob_client.ClobClient with production-grade error handling.
Requires L2 authentication (API key + secret + passphrase).
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any

from py_clob_client.client import ClobClient
from py_clob_client.clob_types import (
    ApiCreds,
    OrderArgs,
    OrderType,
)

logger = logging.getLogger(__name__)

CLOB_HOST = "https://clob.polymarket.com"
CHAIN_ID = 137  # Polygon mainnet

# Rate limit: max 10 requests per second
_MIN_REQUEST_INTERVAL = 0.1
_MAX_RETRIES = 3


class PolymarketClient:
    """Production wrapper around py_clob_client.ClobClient.

    Features:
    - Automatic L2 auth from env vars
    - Retry with exponential backoff
    - Rate limiting (10 req/sec)
    - Secret redaction in all logs

    Env vars:
        POLYMARKET_API_KEY: CLOB API key
        POLYMARKET_API_SECRET: CLOB API secret
        POLYMARKET_PASSPHRASE: CLOB API passphrase
        POLYMARKET_PRIVATE_KEY: Ethereum private key for signing
        POLYMARKET_FUNDER_ADDRESS: Funder address
    """

    def __init__(self) -> None:
        private_key = os.environ.get("POLYMARKET_PRIVATE_KEY", "")
        api_key = os.environ.get("POLYMARKET_API_KEY", "")
        api_secret = os.environ.get("POLYMARKET_API_SECRET", "")
        passphrase = os.environ.get("POLYMARKET_PASSPHRASE", "")
        funder = os.environ.get("POLYMARKET_FUNDER_ADDRESS", "")

        if not private_key:
            logger.warning(
                "POLYMARKET_PRIVATE_KEY not set — client will be L0 only "
                "(no order placement)",
            )

        creds = None
        if api_key and api_secret and passphrase:
            creds = ApiCreds(
                api_key=api_key,
                api_secret=api_secret,
                api_passphrase=passphrase,
            )

        self._client = ClobClient(
            host=CLOB_HOST,
            chain_id=CHAIN_ID,
            key=private_key or None,
            creds=creds,
            funder=funder or None,
        )
        self._last_request_time = 0.0

        auth_level = "L0"
        if private_key:
            auth_level = "L1"
        if creds:
            auth_level = "L2"
        logger.info(
            "Polymarket client initialized (%s auth, funder=%s)",
            auth_level, _redact(funder),
        )

    def _rate_limit(self) -> None:
        """Enforce minimum interval between requests."""
        now = time.monotonic()
        elapsed = now - self._last_request_time
        if elapsed < _MIN_REQUEST_INTERVAL:
            time.sleep(_MIN_REQUEST_INTERVAL - elapsed)
        self._last_request_time = time.monotonic()

    def _retry(self, fn, *args, **kwargs) -> Any:
        """Retry with exponential backoff."""
        for attempt in range(_MAX_RETRIES):
            try:
                self._rate_limit()
                return fn(*args, **kwargs)
            except Exception as e:
                if attempt == _MAX_RETRIES - 1:
                    logger.error(
                        "Request failed after %d attempts: %s",
                        _MAX_RETRIES, e,
                    )
                    raise
                backoff = 2 ** attempt
                logger.warning(
                    "Request failed (attempt %d/%d): %s, retrying in %ds",
                    attempt + 1, _MAX_RETRIES, e, backoff,
                )
                time.sleep(backoff)
        return None  # unreachable

    # ── Order operations ────────────────────────────────────────

    def create_and_post_order(
        self,
        token_id: str,
        price: float,
        size: float,
        side: str,
        order_type: OrderType = OrderType.GTC,
        post_only: bool = True,
    ) -> dict:
        """Create, sign, and post a limit order.

        Args:
            token_id: Polymarket token ID (Up or Down).
            price: Limit price (0.01-0.99).
            size: Number of shares.
            side: "BUY" or "SELL".
            order_type: GTC (default), FOK, or GTD.
            post_only: If True, reject if would cross spread (maker only).

        Returns:
            Order response dict from Polymarket API.
        """
        order_args = OrderArgs(
            token_id=token_id,
            price=price,
            size=size,
            side=side,
        )
        signed_order = self._retry(
            self._client.create_order, order_args,
        )
        result = self._retry(
            self._client.post_order,
            signed_order, order_type, post_only,
        )
        logger.info(
            "Order posted: %s %s %.0f shares @ %.4f (%s)",
            side, token_id[:12], size, price,
            "post-only" if post_only else "crossing ok",
        )
        return result

    def cancel_order(self, order_id: str) -> dict:
        """Cancel a single order by ID."""
        result = self._retry(
            self._client.cancel_orders, [order_id],
        )
        logger.info("Cancelled order %s", order_id)
        return result

    def cancel_all(self) -> dict:
        """Cancel all open orders."""
        result = self._retry(self._client.cancel_all)
        logger.info("Cancelled all orders")
        return result

    def get_order(self, order_id: str) -> dict:
        """Get order status by ID."""
        return self._retry(self._client.get_order, order_id)

    def get_open_orders(self) -> list[dict]:
        """Get all open orders."""
        result = self._retry(self._client.get_orders)
        return result if isinstance(result, list) else []

    # ── Market data ─────────────────────────────────────────────

    def get_order_book(self, token_id: str) -> dict:
        """Get L2 orderbook for a token."""
        return self._retry(self._client.get_order_book, token_id)

    def get_mid_price(self, token_id: str) -> float | None:
        """Get mid-point price for a token."""
        try:
            result = self._retry(
                self._client.get_midpoint, token_id,
            )
            return float(result.get("mid", 0))
        except Exception:
            return None

    def get_spread(self, token_id: str) -> float | None:
        """Get spread for a token."""
        try:
            result = self._retry(
                self._client.get_spread, token_id,
            )
            return float(result.get("spread", 0))
        except Exception:
            return None

    # ── Account ─────────────────────────────────────────────────

    def derive_api_key(self) -> ApiCreds | None:
        """Derive API key from private key (L1 → L2 upgrade)."""
        try:
            creds = self._retry(self._client.derive_api_key)
            self._client.creds = creds
            logger.info("Derived API key: %s", _redact(creds.api_key))
            return creds
        except Exception as e:
            logger.error("Failed to derive API key: %s", e)
            return None

    @property
    def inner(self) -> ClobClient:
        """Access the underlying py_clob_client for advanced operations."""
        return self._client


def _redact(s: str) -> str:
    """Redact sensitive strings for logging."""
    if not s or len(s) < 8:
        return "***"
    return s[:4] + "..." + s[-4:]
