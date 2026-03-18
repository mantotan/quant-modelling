"""Deribit implied volatility downloader.

Downloads historical IV data from the Deribit public API.
No authentication required for public market data endpoints.

API endpoint: GET /api/v2/public/get_historical_volatility
Rate limit: 20 requests/second (public, unauthenticated)

The IV data is stored as Hive-partitioned Parquet at
data/raw/options_iv/asset=X/date=Y/data.parquet

Note: Deribit only supports BTC and ETH options. SOL/XRP will be
skipped gracefully.
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

DERIBIT_API_BASE = "https://www.deribit.com/api/v2"

# Deribit only has options for BTC and ETH
SUPPORTED_ASSETS: dict[Asset, str] = {
    Asset.BTC: "BTC",
    Asset.ETH: "ETH",
}

# Earliest data availability (approximate)
ASSET_START_DATES: dict[Asset, date] = {
    Asset.BTC: date(2019, 1, 1),
    Asset.ETH: date(2019, 6, 1),
}


class DeribitIVDownloader:
    """Downloads historical implied volatility from Deribit public API.

    Usage:
        store = ParquetStore(Path("data/raw/options_iv"))
        downloader = DeribitIVDownloader(store)
        stats = await downloader.download_all([Asset.BTC, Asset.ETH])
    """

    def __init__(
        self,
        store: ParquetStore,
        max_concurrent: int = 2,
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
        """Download historical IV for supported assets.

        Args:
            assets: Assets to download. Unsupported assets are skipped.
            start_date: Start date. Defaults to asset-specific start.
            end_date: End date. Defaults to yesterday.

        Returns:
            Dict with keys: downloaded, skipped, failed, rows.
        """
        assets = assets or list(SUPPORTED_ASSETS.keys())
        end_date = end_date or (date.today() - timedelta(days=1))
        stats: dict[str, int] = {
            "downloaded": 0, "skipped": 0, "failed": 0, "rows": 0,
        }

        async with aiohttp.ClientSession(timeout=self._timeout) as session:
            for asset in assets:
                if asset not in SUPPORTED_ASSETS:
                    logger.info(
                        "Skipping %s — Deribit only supports BTC/ETH options",
                        asset.value,
                    )
                    stats["skipped"] += 1
                    continue

                sym_start = start_date or ASSET_START_DATES.get(
                    asset, date(2019, 1, 1)
                )
                logger.info(
                    "Downloading IV for %s from %s to %s",
                    asset.value, sym_start, end_date,
                )
                asset_stats = await self._download_asset(
                    session, asset, sym_start, end_date
                )
                for k in stats:
                    stats[k] += asset_stats.get(k, 0)

        logger.info(
            "IV download complete: %d downloaded, %d skipped, %d failed, %d rows",
            stats["downloaded"], stats["skipped"], stats["failed"], stats["rows"],
        )
        return stats

    async def _download_asset(
        self,
        session: aiohttp.ClientSession,
        asset: Asset,
        start_date: date,
        end_date: date,
    ) -> dict[str, int]:
        """Download historical volatility for a single asset."""
        stats: dict[str, int] = {
            "downloaded": 0, "skipped": 0, "failed": 0, "rows": 0,
        }
        currency = SUPPORTED_ASSETS[asset]

        async with self._semaphore:
            try:
                records = await self._fetch_historical_vol(
                    session, currency
                )
            except Exception:
                logger.exception(
                    "Failed to fetch IV for %s", asset.value,
                )
                stats["failed"] += 1
                return stats

        if not records:
            logger.info("No IV data for %s", asset.value)
            return stats

        df = self._parse_records(records, start_date, end_date)
        if df.is_empty():
            logger.info("No IV records in date range for %s", asset.value)
            return stats

        stats["downloaded"] = 1
        stats["rows"] = len(df)
        self._store.write_metrics(df, asset)
        logger.info("Stored %d IV records for %s", len(df), asset.value)
        return stats

    async def _fetch_historical_vol(
        self,
        session: aiohttp.ClientSession,
        currency: str,
    ) -> list[list]:
        """Fetch historical volatility from Deribit public API."""
        url = f"{DERIBIT_API_BASE}/public/get_historical_volatility"
        params = {"currency": currency}

        for attempt in range(3):
            try:
                async with session.get(url, params=params) as resp:
                    if resp.status == 429:
                        retry_after = int(
                            resp.headers.get("Retry-After", "5")
                        )
                        logger.warning(
                            "Rate limited, sleeping %ds", retry_after,
                        )
                        await asyncio.sleep(retry_after)
                        continue
                    resp.raise_for_status()
                    data = await resp.json()
                    return data.get("result", [])
            except (TimeoutError, aiohttp.ClientError) as e:
                backoff = 2 ** attempt
                logger.warning(
                    "Attempt %d failed for %s: %s, retrying in %ds",
                    attempt + 1, currency, e, backoff,
                )
                await asyncio.sleep(backoff)

        msg = f"Failed to fetch IV for {currency} after 3 attempts"
        raise RuntimeError(msg)

    @staticmethod
    def _parse_records(
        records: list[list],
        start_date: date,
        end_date: date,
    ) -> pl.DataFrame:
        """Parse Deribit historical volatility response.

        API returns: [[timestamp_ms, value], ...] where value is
        annualised IV as a percentage (e.g., 80.5 = 80.5%).

        Output columns: time (Datetime UTC), iv_index (Float64)
        """
        if not records:
            return pl.DataFrame()

        rows = []
        start_dt = datetime(
            start_date.year, start_date.month, start_date.day, tzinfo=UTC,
        )
        end_dt = datetime(
            end_date.year, end_date.month, end_date.day, 23, 59, 59,
            tzinfo=UTC,
        )

        for record in records:
            if len(record) < 2:
                continue
            ts_ms, iv_value = record[0], record[1]
            ts = datetime.fromtimestamp(ts_ms / 1000, tz=UTC)
            if ts < start_dt or ts > end_dt:
                continue
            rows.append({
                "time": ts,
                "iv_index": float(iv_value) / 100.0,  # convert % to decimal
            })

        if not rows:
            return pl.DataFrame()

        df = pl.DataFrame(rows)
        df = df.cast({
            "time": pl.Datetime("us", "UTC"),
            "iv_index": pl.Float64,
        })
        return df.unique(subset=["time"]).sort("time")
