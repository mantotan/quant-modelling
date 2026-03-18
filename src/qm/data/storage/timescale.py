"""TimescaleDB async writer using asyncpg.

Handles bulk inserts, schema initialization, and connection pooling.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from urllib.parse import urlparse

import asyncpg

from qm.core.types import Bar
from qm.data.storage.schemas import (
    INIT_SEQUENCE,
    INSERT_AUDIT,
    INSERT_POLYMARKET_SNAPSHOT,
    INSERT_TRADE,
    UPSERT_OHLCV,
)

logger = logging.getLogger(__name__)


def _sanitize_dsn(dsn: str) -> str:
    """Remove credentials from DSN for safe logging."""
    try:
        parsed = urlparse(dsn)
        return f"{parsed.scheme}://*:*@{parsed.hostname}:{parsed.port}{parsed.path}"
    except Exception:
        return "***"


def _require_pool(pool: asyncpg.Pool | None) -> asyncpg.Pool:
    """Runtime check that pool is connected. Never use assert for this."""
    if pool is None:
        raise RuntimeError("TimescaleDB not connected. Call connect() first.")
    return pool


class TimescaleWriter:
    """Async TimescaleDB writer with connection pooling.

    Usage:
        writer = TimescaleWriter(dsn)
        await writer.connect()
        await writer.write_bar(bar)
        await writer.close()
    """

    def __init__(self, dsn: str, min_pool: int = 5, max_pool: int = 20) -> None:
        self._dsn = dsn
        self._min_pool = min_pool
        self._max_pool = max_pool
        self._pool: asyncpg.Pool | None = None

    async def connect(self) -> None:
        """Create connection pool and initialize schema."""
        self._pool = await asyncpg.create_pool(
            self._dsn,
            min_size=self._min_pool,
            max_size=self._max_pool,
        )
        await self._init_schema()
        logger.info("TimescaleDB connected", extra={"dsn": _sanitize_dsn(self._dsn)})

    async def close(self) -> None:
        if self._pool:
            await self._pool.close()
            self._pool = None

    async def _init_schema(self) -> None:
        """Run all schema initialization SQL."""
        pool = _require_pool(self._pool)
        async with pool.acquire() as conn:
            for sql in INIT_SEQUENCE:
                try:
                    await conn.execute(sql)
                except Exception as e:
                    # Retention/compression policies may fail if already set or
                    # TimescaleDB extension not loaded — log at WARNING for
                    # DDL (CREATE TABLE) and DEBUG for policies
                    is_policy = "policy" in sql.lower() or "compress" in sql.lower()
                    level = logging.DEBUG if is_policy else logging.WARNING
                    logger.log(level, "Schema init: %s", e)

    async def write_bar(self, bar: Bar, exchange: str = "aggregated") -> None:
        """Write a single OHLCV bar. Idempotent via upsert."""
        pool = _require_pool(self._pool)
        await pool.execute(
            UPSERT_OHLCV,
            bar.timestamp,
            bar.asset.value,
            bar.timeframe.value,
            exchange,
            bar.open,
            bar.high,
            bar.low,
            bar.close,
            bar.volume,
            bar.trade_count,
            bar.vwap,
        )

    async def write_bars(self, bars: list[Bar], exchange: str = "aggregated") -> None:
        """Batch write multiple OHLCV bars."""
        if not bars:
            return
        pool = _require_pool(self._pool)
        records = [
            (
                b.timestamp, b.asset.value, b.timeframe.value, exchange,
                b.open, b.high, b.low, b.close, b.volume, b.trade_count, b.vwap,
            )
            for b in bars
        ]
        async with pool.acquire() as conn:
            await conn.executemany(UPSERT_OHLCV, records)

    async def write_trade(
        self,
        time: datetime,
        asset: str,
        exchange: str,
        price: float,
        size: float,
        side: str | None,
        trade_id: str | None,
    ) -> None:
        """Write a single raw trade."""
        pool = _require_pool(self._pool)
        await pool.execute(
            INSERT_TRADE,
            time, asset, exchange, price, size, side, trade_id,
        )

    async def write_audit(
        self,
        event_type: str,
        asset: str | None = None,
        market_type: str | None = None,
        signal_id: str | None = None,
        details: str = "{}",
        time: datetime | None = None,
    ) -> None:
        """Write an audit log entry. Append-only."""
        pool = _require_pool(self._pool)
        ts = time or datetime.now(timezone.utc)
        await pool.execute(
            INSERT_AUDIT, ts, event_type, asset, market_type, signal_id, details,
        )

    async def write_polymarket_snapshot(
        self,
        time: datetime,
        condition_id: str,
        token_id_up: str,
        token_id_down: str,
        asset: str,
        market_type: str,
        window_start: datetime,
        window_end: datetime,
        mid_up: float | None,
        mid_down: float | None,
        spread_up: float | None,
        volume: float | None,
    ) -> None:
        """Write a Polymarket odds snapshot."""
        pool = _require_pool(self._pool)
        await pool.execute(
            INSERT_POLYMARKET_SNAPSHOT,
            time, condition_id, token_id_up, token_id_down,
            asset, market_type, window_start, window_end,
            mid_up, mid_down, spread_up, volume,
        )

    async def health_check(self) -> bool:
        """Quick connectivity check."""
        if not self._pool:
            return False
        try:
            async with self._pool.acquire() as conn:
                await conn.fetchval("SELECT 1")
            return True
        except Exception:
            return False
