"""Binance perpetual funding rate downloader.

Downloads historical funding rates from the Binance Futures REST API.
Funding rates are published every 8 hours (00:00, 08:00, 16:00 UTC).

API endpoint: GET /fapi/v1/fundingRate
Rate limit: 2400 requests/minute on /fapi/v1/*

Storage: Hive-partitioned Parquet at data/raw/funding/asset=X/date=Y/data.parquet
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, date, datetime, timedelta

import aiohttp
import polars as pl

from qm.core.types import Asset
from qm.data.storage.parquet import ParquetStore  # noqa: TC001

logger = logging.getLogger(__name__)

BINANCE_FAPI_BASE = "https://fapi.binance.com"

# Binance futures symbol mapping (reuse from binance_vision but avoid circular import)
ASSET_TO_SYMBOL: dict[Asset, str] = {
    Asset.BTC: "BTCUSDT",
    Asset.ETH: "ETHUSDT",
    Asset.SOL: "SOLUSDT",
    Asset.XRP: "XRPUSDT",
}

# Earliest funding rate data per symbol (approximate)
SYMBOL_START_DATES: dict[str, date] = {
    "BTCUSDT": date(2019, 9, 10),
    "ETHUSDT": date(2019, 11, 29),
    "SOLUSDT": date(2021, 7, 27),
    "XRPUSDT": date(2020, 1, 7),
}

# Max records per API call
MAX_LIMIT = 1000

# Funding events per day (every 8h)
EVENTS_PER_DAY = 3


class BinanceFundingRateDownloader:
    """Downloads historical funding rates from Binance Futures REST API.

    Funding rates are published every 8h. The API returns up to 1000 records
    per call, paginated by startTime/endTime.

    Usage:
        store = ParquetStore(Path("data/raw/funding"))
        downloader = BinanceFundingRateDownloader(store)
        stats = await downloader.download_all([Asset.BTC, Asset.ETH])
    """

    def __init__(
        self,
        store: ParquetStore,
        max_concurrent: int = 4,
        timeout_seconds: float = 30.0,
    ) -> None:
        self._store = store
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._timeout = aiohttp.ClientTimeout(total=timeout_seconds)

    async def download_all(
        self,
        assets: list[Asset] | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> dict[str, int]:
        """Download funding rates for all specified assets.

        Args:
            assets: List of assets to download. Defaults to all supported.
            start_date: Start date. Defaults to symbol launch date.
            end_date: End date. Defaults to yesterday.

        Returns:
            Dict with keys: downloaded, skipped, failed, rows.
        """
        assets = assets or list(ASSET_TO_SYMBOL.keys())
        end_date = end_date or (date.today() - timedelta(days=1))

        stats: dict[str, int] = {"downloaded": 0, "skipped": 0, "failed": 0, "rows": 0}

        async with aiohttp.ClientSession(timeout=self._timeout) as session:
            for asset in assets:
                symbol = ASSET_TO_SYMBOL[asset]
                sym_start = start_date or SYMBOL_START_DATES.get(
                    symbol, date(2020, 1, 1)
                )

                logger.info(
                    "Downloading funding rates for %s (%s) from %s to %s",
                    asset.value, symbol, sym_start, end_date,
                )

                asset_stats = await self._download_symbol(
                    session, asset, symbol, sym_start, end_date
                )
                for k in stats:
                    stats[k] += asset_stats.get(k, 0)

        logger.info(
            "Funding rate download complete: %d downloaded, %d skipped, %d failed, %d rows",
            stats["downloaded"], stats["skipped"], stats["failed"], stats["rows"],
        )
        return stats

    async def _download_symbol(
        self,
        session: aiohttp.ClientSession,
        asset: Asset,
        symbol: str,
        start_date: date,
        end_date: date,
    ) -> dict[str, int]:
        """Download all funding rates for a single symbol via pagination."""
        stats: dict[str, int] = {"downloaded": 0, "skipped": 0, "failed": 0, "rows": 0}

        start_ms = int(
            datetime(start_date.year, start_date.month, start_date.day, tzinfo=UTC)
            .timestamp() * 1000
        )
        end_ms = int(
            datetime(end_date.year, end_date.month, end_date.day, 23, 59, 59, tzinfo=UTC)
            .timestamp() * 1000
        )

        current_start = start_ms
        all_rows: list[dict] = []

        while current_start < end_ms:
            async with self._semaphore:
                try:
                    records = await self._fetch_page(
                        session, symbol, current_start, end_ms
                    )
                except Exception:
                    logger.exception(
                        "Failed to fetch funding rates for %s at %d",
                        symbol, current_start,
                    )
                    stats["failed"] += 1
                    # Skip forward by ~1000 records worth of time (8h * 1000 = ~333 days)
                    current_start += 8 * 3600 * 1000 * MAX_LIMIT
                    continue

                if not records:
                    break

                all_rows.extend(records)
                stats["downloaded"] += 1

                # Move past the last record's timestamp
                last_ts = records[-1]["fundingTime"]
                current_start = last_ts + 1

                # If we got fewer than MAX_LIMIT, we've reached the end
                if len(records) < MAX_LIMIT:
                    break

        if not all_rows:
            logger.info("No funding rate data for %s", symbol)
            return stats

        df = self._parse_records(all_rows)
        stats["rows"] = len(df)

        # Write to ParquetStore using write_metrics (asset/date partitioning)
        self._store.write_metrics(df, asset)
        logger.info("Stored %d funding rate records for %s", len(df), asset.value)

        return stats

    async def _fetch_page(
        self,
        session: aiohttp.ClientSession,
        symbol: str,
        start_ms: int,
        end_ms: int,
    ) -> list[dict]:
        """Fetch one page of funding rate data with retry."""
        url = f"{BINANCE_FAPI_BASE}/fapi/v1/fundingRate"
        params = {
            "symbol": symbol,
            "startTime": start_ms,
            "endTime": end_ms,
            "limit": MAX_LIMIT,
        }

        for attempt in range(3):
            try:
                async with session.get(url, params=params) as resp:
                    if resp.status == 429:
                        retry_after = int(resp.headers.get("Retry-After", "60"))
                        logger.warning("Rate limited, sleeping %ds", retry_after)
                        await asyncio.sleep(retry_after)
                        continue
                    resp.raise_for_status()
                    return await resp.json()
            except (TimeoutError, aiohttp.ClientError) as e:
                backoff = 2 ** attempt
                logger.warning(
                    "Attempt %d failed for %s: %s, retrying in %ds",
                    attempt + 1, symbol, e, backoff,
                )
                await asyncio.sleep(backoff)

        raise RuntimeError(f"Failed to fetch funding rates for {symbol} after 3 attempts")

    @staticmethod
    def _parse_records(records: list[dict]) -> pl.DataFrame:
        """Parse Binance funding rate API response into a Polars DataFrame.

        API returns: [{"symbol": "BTCUSDT", "fundingTime": 1569801600000,
                       "fundingRate": "0.00010000", "markPrice": "8310.17514214"}, ...]

        Output columns: time (Datetime UTC), funding_rate (Float64), mark_price (Float64)
        """
        rows = []
        for r in records:
            rows.append({
                "time": datetime.fromtimestamp(r["fundingTime"] / 1000, tz=UTC),
                "funding_rate": float(r["fundingRate"]),
                "mark_price": float(r.get("markPrice", 0)) if r.get("markPrice") else None,
            })

        df = pl.DataFrame(rows)
        if df.is_empty():
            return df

        # Ensure correct types
        df = df.cast({
            "time": pl.Datetime("us", "UTC"),
            "funding_rate": pl.Float64,
        })

        # Deduplicate by time
        df = df.unique(subset=["time"]).sort("time")

        return df
