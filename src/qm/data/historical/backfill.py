"""Historical data backfill via ccxt REST API.

Downloads OHLCV candles for multiple assets and timeframes going back
as far as exchange history allows. Idempotent via upsert.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

import ccxt.async_support as ccxt_async

from qm.core.constants import EXCHANGE_SYMBOLS, TIMEFRAME_MINUTES
from qm.core.types import Asset, Bar, Timeframe

logger = logging.getLogger(__name__)

# Rate limits per exchange (requests per minute)
RATE_LIMITS: dict[str, float] = {
    "binance": 1200,
    "bybit": 120,
}


async def backfill_ohlcv(
    exchange_id: str,
    asset: Asset,
    timeframe: Timeframe,
    start: datetime,
    end: datetime | None = None,
    api_key: str | None = None,
    api_secret: str | None = None,
) -> list[Bar]:
    """Download historical OHLCV data for a single asset/timeframe.

    Args:
        exchange_id: ccxt exchange identifier (e.g., 'binance')
        asset: Asset to download
        timeframe: Candle timeframe
        start: Start datetime (UTC)
        end: End datetime (UTC), defaults to now
        api_key: Optional API key
        api_secret: Optional API secret

    Returns:
        List of Bar objects, sorted by time ascending.
    """
    if end is None:
        end = datetime.now(timezone.utc)

    symbol = EXCHANGE_SYMBOLS[asset]
    tf_str = timeframe.value

    config: dict = {"enableRateLimit": True}
    if api_key:
        config["apiKey"] = api_key
    if api_secret:
        config["secret"] = api_secret

    exchange = getattr(ccxt_async, exchange_id)(config)

    bars: list[Bar] = []
    since_ms = int(start.timestamp() * 1000)
    end_ms = int(end.timestamp() * 1000)

    # Adaptive rate limiting
    request_delay = 60.0 / RATE_LIMITS.get(exchange_id, 60)
    batch_size = 1000  # most exchanges support up to 1000 candles per request

    try:
        while since_ms < end_ms:
            try:
                candles = await exchange.fetch_ohlcv(
                    symbol, tf_str, since=since_ms, limit=batch_size
                )
            except ccxt_async.RateLimitExceeded:
                logger.warning("Rate limited, backing off")
                await asyncio.sleep(request_delay * 5)
                continue

            if not candles:
                break

            for c in candles:
                ts = datetime.fromtimestamp(c[0] / 1000, tz=timezone.utc)
                if ts.timestamp() * 1000 >= end_ms:
                    break
                bars.append(
                    Bar(
                        timestamp=ts,
                        asset=asset,
                        timeframe=timeframe,
                        open=float(c[1]),
                        high=float(c[2]),
                        low=float(c[3]),
                        close=float(c[4]),
                        volume=float(c[5]),
                        trade_count=0,  # not available from REST
                        vwap=(float(c[2]) + float(c[3]) + float(c[4])) / 3,  # approx
                    )
                )

            # Move cursor forward
            last_ts = candles[-1][0]
            if last_ts <= since_ms:
                break  # no progress, avoid infinite loop
            since_ms = last_ts + 1

            await asyncio.sleep(request_delay)

            if len(bars) % 5000 == 0 and bars:
                logger.info(
                    f"Backfill progress: {len(bars)} bars",
                    extra={"asset": asset.value, "timeframe": tf_str},
                )

    finally:
        await exchange.close()

    logger.info(
        f"Backfill complete: {len(bars)} bars",
        extra={
            "asset": asset.value,
            "timeframe": tf_str,
            "start": start.isoformat(),
            "end": end.isoformat(),
        },
    )

    return bars
