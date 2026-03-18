"""Bulk historical klines downloader from data.binance.vision.

Downloads monthly/daily ZIP archives of futures USDT-M klines,
extracts CSV, validates, converts to Polars DataFrame, saves as Parquet.

Much faster than ccxt REST pagination:
- Static file hosting (no rate limits)
- Monthly archives (1 file vs 28-31 daily files)
- Parallel downloads via aiohttp
"""

from __future__ import annotations

import asyncio
import hashlib
import io
import logging
import tempfile
import zipfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import aiohttp
import polars as pl

from qm.core.types import Asset, Timeframe
from qm.data.storage.parquet import ParquetStore

logger = logging.getLogger(__name__)

BASE_URL = "https://data.binance.vision/data/futures/um"

# Symbol mapping: our Asset enum → Binance futures symbol
ASSET_TO_SYMBOL: dict[Asset, str] = {
    Asset.BTC: "BTCUSDT",
    Asset.ETH: "ETHUSDT",
    Asset.SOL: "SOLUSDT",
    Asset.XRP: "XRPUSDT",
}

# Earliest available date per symbol (futures launch dates)
SYMBOL_START_DATES: dict[str, date] = {
    "BTCUSDT": date(2019, 9, 8),
    "ETHUSDT": date(2019, 11, 27),
    "SOLUSDT": date(2021, 7, 26),
    "XRPUSDT": date(2020, 1, 6),
}

# Binance Vision klines CSV columns (12 fields)
CSV_COLUMNS = [
    "open_time", "open", "high", "low", "close", "volume",
    "close_time", "quote_volume", "trade_count",
    "taker_buy_volume", "taker_buy_quote_volume", "ignore",
]

# Our output schema
OUTPUT_DTYPES: dict[str, pl.DataType] = {
    "time": pl.Datetime("us", "UTC"),
    "open": pl.Float64,
    "high": pl.Float64,
    "low": pl.Float64,
    "close": pl.Float64,
    "volume": pl.Float64,
    "quote_volume": pl.Float64,
    "trade_count": pl.Int64,
    "taker_buy_volume": pl.Float64,
    "vwap": pl.Float64,
}


class BinanceVisionDownloader:
    """Downloads bulk historical klines from data.binance.vision.

    Strategy:
    1. Monthly archives for complete past months (1 file vs ~30 daily files)
    2. Daily archives for current/recent incomplete month
    3. Checksum verification via companion .CHECKSUM files
    4. Parallel downloads (up to max_concurrent)
    """

    def __init__(
        self,
        parquet_store: ParquetStore,
        temp_dir: Path | None = None,
        max_concurrent: int = 4,
        timeout: int = 60,
    ) -> None:
        self._store = parquet_store
        self._temp_dir = temp_dir or Path(tempfile.mkdtemp(prefix="qm_binance_"))
        self._max_concurrent = max_concurrent
        self._timeout = aiohttp.ClientTimeout(total=timeout)
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._stats: dict[str, int] = {"downloaded": 0, "skipped": 0, "failed": 0, "bars": 0}

    async def download_all(
        self,
        assets: list[Asset] | None = None,
        timeframes: list[Timeframe] | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> dict[str, int]:
        """Download all data for specified assets and timeframes.

        Args:
            assets: Assets to download. Defaults to all supported.
            timeframes: Timeframes to download. Defaults to 5m, 15m, 1h.
            start_date: Override start date (otherwise uses symbol launch date).
            end_date: Override end date (otherwise uses yesterday).

        Returns:
            Stats dict with counts of downloaded/skipped/failed/bars.
        """
        assets = assets or list(ASSET_TO_SYMBOL.keys())
        timeframes = timeframes or [Timeframe.M5, Timeframe.M15, Timeframe.H1]
        end_date = end_date or (date.today() - timedelta(days=1))

        async with aiohttp.ClientSession(timeout=self._timeout) as session:
            for asset in assets:
                symbol = ASSET_TO_SYMBOL[asset]
                sym_start = start_date or SYMBOL_START_DATES.get(symbol, date(2020, 1, 1))

                for tf in timeframes:
                    logger.info(
                        "Downloading %s %s from %s to %s",
                        symbol, tf.value, sym_start, end_date,
                    )
                    await self._download_symbol_timeframe(
                        session, asset, symbol, tf, sym_start, end_date
                    )

        logger.info("Download complete: %s", self._stats)
        return self._stats

    async def _download_symbol_timeframe(
        self,
        session: aiohttp.ClientSession,
        asset: Asset,
        symbol: str,
        timeframe: Timeframe,
        start: date,
        end: date,
    ) -> None:
        """Download all data for one symbol/timeframe combination."""
        # Generate list of months to download
        months = _month_range(start, end)

        # Download months in parallel (bounded by semaphore)
        tasks = []
        for year, month in months:
            # Check if this is the current (incomplete) month
            month_end = _last_day_of_month(year, month)
            if month_end > end:
                # Current month: use daily downloads
                month_start = date(year, month, 1)
                actual_start = max(month_start, start)
                for d in _date_range(actual_start, min(month_end, end)):
                    tasks.append(
                        self._download_daily(session, asset, symbol, timeframe, d)
                    )
            else:
                # Complete month: use monthly archive
                tasks.append(
                    self._download_monthly(session, asset, symbol, timeframe, year, month)
                )

        # Execute with concurrency limit
        await asyncio.gather(*tasks, return_exceptions=True)

    async def _download_monthly(
        self,
        session: aiohttp.ClientSession,
        asset: Asset,
        symbol: str,
        timeframe: Timeframe,
        year: int,
        month: int,
    ) -> None:
        """Download a monthly ZIP archive."""
        ym = f"{year}-{month:02d}"
        filename = f"{symbol}-{timeframe.value}-{ym}.zip"
        url = f"{BASE_URL}/monthly/klines/{symbol}/{timeframe.value}/{filename}"

        async with self._semaphore:
            try:
                data = await self._fetch_with_checksum(session, url)
                if data is None:
                    # Monthly not available, fall back to daily
                    logger.debug("Monthly %s not available, trying daily", filename)
                    month_start = date(year, month, 1)
                    month_end = _last_day_of_month(year, month)
                    for d in _date_range(month_start, month_end):
                        await self._download_daily(session, asset, symbol, timeframe, d)
                    return

                df = self._parse_zip(data, symbol)
                if df is not None and not df.is_empty():
                    self._store.write_df(df, asset, timeframe)
                    self._stats["bars"] += len(df)
                    self._stats["downloaded"] += 1
                    logger.info("Downloaded %s: %d bars", filename, len(df))
                else:
                    self._stats["skipped"] += 1

            except Exception:
                logger.exception("Failed to download %s", filename)
                self._stats["failed"] += 1

    async def _download_daily(
        self,
        session: aiohttp.ClientSession,
        asset: Asset,
        symbol: str,
        timeframe: Timeframe,
        d: date,
    ) -> None:
        """Download a daily ZIP archive."""
        date_str = d.isoformat()
        filename = f"{symbol}-{timeframe.value}-{date_str}.zip"
        url = f"{BASE_URL}/daily/klines/{symbol}/{timeframe.value}/{filename}"

        async with self._semaphore:
            try:
                data = await self._fetch_with_checksum(session, url)
                if data is None:
                    self._stats["skipped"] += 1
                    return

                df = self._parse_zip(data, symbol)
                if df is not None and not df.is_empty():
                    self._store.write_df(df, asset, timeframe)
                    self._stats["bars"] += len(df)
                    self._stats["downloaded"] += 1
                else:
                    self._stats["skipped"] += 1

            except Exception:
                logger.exception("Failed to download %s", filename)
                self._stats["failed"] += 1

    async def _fetch_with_checksum(
        self,
        session: aiohttp.ClientSession,
        url: str,
    ) -> bytes | None:
        """Download ZIP and verify against .CHECKSUM companion file.

        Returns ZIP bytes, or None if 404 / checksum mismatch.
        """
        # Download ZIP
        async with session.get(url) as resp:
            if resp.status == 404:
                return None
            if resp.status != 200:
                logger.warning("HTTP %d for %s", resp.status, url)
                return None
            zip_data = await resp.read()

        # Download and verify checksum
        checksum_url = url + ".CHECKSUM"
        try:
            async with session.get(checksum_url) as resp:
                if resp.status == 200:
                    checksum_text = await resp.text()
                    expected_hash = checksum_text.strip().split()[0].lower()
                    actual_hash = hashlib.sha256(zip_data).hexdigest().lower()
                    if actual_hash != expected_hash:
                        logger.error(
                            "Checksum mismatch for %s: expected %s, got %s",
                            url, expected_hash[:12], actual_hash[:12],
                        )
                        return None
        except Exception:
            # Checksum file might not exist for older data — proceed without
            pass

        return zip_data

    def _parse_zip(self, zip_data: bytes, symbol: str) -> pl.DataFrame | None:
        """Extract CSV from ZIP and parse to Polars DataFrame."""
        try:
            with zipfile.ZipFile(io.BytesIO(zip_data)) as zf:
                csv_names = [n for n in zf.namelist() if n.endswith(".csv")]
                if not csv_names:
                    return None
                csv_data = zf.read(csv_names[0])
        except zipfile.BadZipFile:
            logger.error("Corrupt ZIP for %s", symbol)
            return None

        # Parse CSV with Polars (5-10x faster than Pandas)
        # Binance Vision CSVs have a header row with columns:
        # open_time,open,high,low,close,volume,close_time,quote_volume,count,...
        df = pl.read_csv(
            io.BytesIO(csv_data),
            has_header=True,
            schema_overrides={
                "open_time": pl.Int64,
                "open": pl.Float64,
                "high": pl.Float64,
                "low": pl.Float64,
                "close": pl.Float64,
                "volume": pl.Float64,
                "close_time": pl.Int64,
                "quote_volume": pl.Float64,
                "count": pl.Int64,
                "taker_buy_volume": pl.Float64,
                "taker_buy_quote_volume": pl.Float64,
                "ignore": pl.Utf8,
            },
        )
        # Rename 'count' to 'trade_count' (Binance uses 'count' in header)
        if "count" in df.columns:
            df = df.rename({"count": "trade_count"})

        # Convert timestamps: open_time is milliseconds since epoch
        df = df.with_columns(
            (pl.col("open_time") * 1000).cast(pl.Datetime("us")).dt.replace_time_zone("UTC").alias("time"),
        )

        # Compute approximate VWAP (quote_volume / volume)
        df = df.with_columns(
            (pl.col("quote_volume") / (pl.col("volume") + 1e-10)).alias("vwap"),
        )

        # Validate: remove rows where high < low
        before = len(df)
        df = df.filter(pl.col("high") >= pl.col("low"))
        dropped = before - len(df)
        if dropped > 0:
            logger.warning("Dropped %d bars with high < low for %s", dropped, symbol)

        return df.select([
            "time", "open", "high", "low", "close", "volume",
            "quote_volume", "trade_count", "taker_buy_volume", "vwap",
        ])

    async def download_metrics(
        self,
        metrics_store: ParquetStore,
        assets: list[Asset] | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> dict[str, int]:
        """Download derivatives metrics (OI, L/S ratios, taker ratios) from Binance Vision.

        Metrics are daily ZIPs at 5-minute granularity. No monthly archives available.
        Timestamps are shifted by -5 minutes to align with kline open_time.

        Args:
            metrics_store: ParquetStore with base_dir for metrics (e.g., data/raw/metrics).
            assets: Assets to download. Defaults to all supported.
            start_date: Start date. Defaults to 2020-09-01 (earliest available).
            end_date: End date. Defaults to yesterday.
        """
        assets = assets or list(ASSET_TO_SYMBOL.keys())
        start_date = start_date or date(2020, 9, 1)
        end_date = end_date or (date.today() - timedelta(days=1))

        stats: dict[str, int] = {"downloaded": 0, "skipped": 0, "failed": 0, "rows": 0}

        async with aiohttp.ClientSession(timeout=self._timeout) as session:
            for asset in assets:
                symbol = ASSET_TO_SYMBOL[asset]
                sym_start = max(start_date, SYMBOL_START_DATES.get(symbol, date(2020, 9, 1)))
                logger.info("Downloading metrics for %s from %s to %s", symbol, sym_start, end_date)

                tasks = []
                for d in _date_range(sym_start, end_date):
                    tasks.append(
                        self._download_metrics_day(session, metrics_store, asset, symbol, d, stats)
                    )
                await asyncio.gather(*tasks, return_exceptions=True)

        logger.info("Metrics download complete: %s", stats)
        return stats

    async def _download_metrics_day(
        self,
        session: aiohttp.ClientSession,
        metrics_store: ParquetStore,
        asset: Asset,
        symbol: str,
        d: date,
        stats: dict[str, int],
    ) -> None:
        """Download one day of metrics data."""
        date_str = d.isoformat()
        filename = f"{symbol}-metrics-{date_str}.zip"
        url = f"{BASE_URL}/daily/metrics/{symbol}/{filename}"

        async with self._semaphore:
            try:
                data = await self._fetch_with_checksum(session, url)
                if data is None:
                    stats["skipped"] += 1
                    return

                df = self._parse_metrics_zip(data, symbol)
                if df is not None and not df.is_empty():
                    metrics_store.write_metrics(df, asset)
                    stats["rows"] += len(df)
                    stats["downloaded"] += 1
                else:
                    stats["skipped"] += 1
            except Exception:
                logger.exception("Failed to download metrics %s", filename)
                stats["failed"] += 1

    def _parse_metrics_zip(self, zip_data: bytes, symbol: str) -> pl.DataFrame | None:
        """Parse metrics ZIP CSV to Polars DataFrame.

        Shifts timestamps by -5 minutes to align with kline open_time:
        metrics at 00:05 → aligned to kline at 00:00.
        """
        try:
            with zipfile.ZipFile(io.BytesIO(zip_data)) as zf:
                csv_names = [n for n in zf.namelist() if n.endswith(".csv")]
                if not csv_names:
                    return None
                csv_data = zf.read(csv_names[0])
        except zipfile.BadZipFile:
            logger.error("Corrupt metrics ZIP for %s", symbol)
            return None

        df = pl.read_csv(
            io.BytesIO(csv_data),
            has_header=True,
            schema_overrides={
                "create_time": pl.Utf8,
                "symbol": pl.Utf8,
                "sum_open_interest": pl.Float64,
                "sum_open_interest_value": pl.Float64,
                "count_toptrader_long_short_ratio": pl.Float64,
                "sum_toptrader_long_short_ratio": pl.Float64,
                "count_long_short_ratio": pl.Float64,
                "sum_taker_long_short_vol_ratio": pl.Float64,
            },
        )

        # Parse timestamp and shift by -5 minutes to align with kline open_time
        df = df.with_columns(
            pl.col("create_time")
            .str.to_datetime("%Y-%m-%d %H:%M:%S")
            .dt.replace_time_zone("UTC")
            .alias("time")
            - pl.duration(minutes=5),
        )

        # Drop symbol and create_time, keep metrics columns + aligned time
        return df.select([
            "time",
            "sum_open_interest",
            "sum_open_interest_value",
            "count_toptrader_long_short_ratio",
            "sum_toptrader_long_short_ratio",
            "count_long_short_ratio",
            "sum_taker_long_short_vol_ratio",
        ])



# ── Helper functions ────────────────────────────────────────────────

def _month_range(start: date, end: date) -> list[tuple[int, int]]:
    """Generate (year, month) tuples from start to end, inclusive."""
    months = []
    current = date(start.year, start.month, 1)
    while current <= end:
        months.append((current.year, current.month))
        if current.month == 12:
            current = date(current.year + 1, 1, 1)
        else:
            current = date(current.year, current.month + 1, 1)
    return months


def _last_day_of_month(year: int, month: int) -> date:
    """Get the last day of a given month."""
    if month == 12:
        return date(year + 1, 1, 1) - timedelta(days=1)
    return date(year, month + 1, 1) - timedelta(days=1)


def _date_range(start: date, end: date) -> list[date]:
    """Generate list of dates from start to end, inclusive."""
    dates = []
    current = start
    while current <= end:
        dates.append(current)
        current += timedelta(days=1)
    return dates


# ── Shared download helper ─────────────────────────────────────────

async def fetch_with_checksum(
    session: aiohttp.ClientSession,
    url: str,
) -> bytes | None:
    """Download ZIP and verify against .CHECKSUM companion file.

    Extracted as module-level function for reuse by multiple downloaders.
    Returns ZIP bytes, or None if 404 / checksum mismatch.
    """
    async with session.get(url) as resp:
        if resp.status == 404:
            return None
        if resp.status != 200:
            logger.warning("HTTP %d for %s", resp.status, url)
            return None
        zip_data = await resp.read()

    checksum_url = url + ".CHECKSUM"
    try:
        async with session.get(checksum_url) as resp:
            if resp.status == 200:
                checksum_text = await resp.text()
                expected_hash = checksum_text.strip().split()[0].lower()
                actual_hash = hashlib.sha256(zip_data).hexdigest().lower()
                if actual_hash != expected_hash:
                    logger.error(
                        "Checksum mismatch for %s: expected %s, got %s",
                        url, expected_hash[:12], actual_hash[:12],
                    )
                    return None
    except Exception:
        pass  # Checksum file might not exist for older data

    return zip_data


# ── AggTrades Downloader ───────────────────────────────────────────

# AggTrades CSV columns (from Binance Vision documentation)
AGGTRADES_COLUMNS = [
    "agg_trade_id", "price", "quantity",
    "first_trade_id", "last_trade_id",
    "timestamp", "is_buyer_maker",
]


class BinanceAggTradesDownloader:
    """Downloads aggregated trades from data.binance.vision.

    AggTrades give real tick-by-tick price data for constructing
    honest intra-bar snapshots (no interpolation needed).

    URL: https://data.binance.vision/data/futures/um/daily/aggTrades/{SYMBOL}/
    Only daily archives available (no monthly for aggTrades).
    """

    def __init__(
        self,
        trades_store: ParquetStore,
        max_concurrent: int = 4,
        timeout: int = 120,
    ) -> None:
        self._store = trades_store
        self._max_concurrent = max_concurrent
        self._timeout = aiohttp.ClientTimeout(total=timeout)
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._stats: dict[str, int] = {
            "downloaded": 0, "skipped": 0, "failed": 0, "trades": 0,
        }

    async def download_all(
        self,
        assets: list[Asset] | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> dict[str, int]:
        """Download aggTrades for specified assets and date range.

        Args:
            assets: Assets to download. Defaults to all supported.
            start_date: Start date (inclusive).
            end_date: End date (inclusive, default: yesterday).

        Returns:
            Stats dict with download counts.
        """
        assets = assets or list(ASSET_TO_SYMBOL.keys())
        end_date = end_date or (date.today() - timedelta(days=1))

        async with aiohttp.ClientSession(timeout=self._timeout) as session:
            for asset in assets:
                symbol = ASSET_TO_SYMBOL[asset]
                sym_start = start_date or SYMBOL_START_DATES.get(symbol, date(2020, 1, 1))

                # Check which dates we already have
                existing_dates = set(self._store.list_trade_dates(asset))

                dates = _date_range(sym_start, end_date)
                to_download = [d for d in dates if d.isoformat() not in existing_dates]

                logger.info(
                    "AggTrades %s: %d dates to download (%d already exist), %s to %s",
                    symbol, len(to_download), len(existing_dates),
                    sym_start, end_date,
                )

                tasks = [
                    self._download_daily(session, asset, symbol, d)
                    for d in to_download
                ]
                await asyncio.gather(*tasks, return_exceptions=True)

        logger.info("AggTrades download complete: %s", self._stats)
        return self._stats

    async def _download_daily(
        self,
        session: aiohttp.ClientSession,
        asset: Asset,
        symbol: str,
        d: date,
    ) -> None:
        """Download a daily aggTrades ZIP archive."""
        date_str = d.isoformat()
        filename = f"{symbol}-aggTrades-{date_str}.zip"
        url = f"{BASE_URL}/daily/aggTrades/{symbol}/{filename}"

        async with self._semaphore:
            try:
                data = await fetch_with_checksum(session, url)
                if data is None:
                    self._stats["skipped"] += 1
                    return

                df = self._parse_aggtrades_zip(data, symbol)
                if df is not None and not df.is_empty():
                    self._store.write_trades(df, asset)
                    self._stats["trades"] += len(df)
                    self._stats["downloaded"] += 1
                    logger.info(
                        "Downloaded %s: %d trades", filename, len(df),
                    )
                else:
                    self._stats["skipped"] += 1

            except Exception:
                logger.exception("Failed to download %s", filename)
                self._stats["failed"] += 1

    def _parse_aggtrades_zip(
        self, zip_data: bytes, symbol: str,
    ) -> pl.DataFrame | None:
        """Extract CSV from ZIP and parse aggTrades to Polars DataFrame."""
        try:
            with zipfile.ZipFile(io.BytesIO(zip_data)) as zf:
                csv_names = [n for n in zf.namelist() if n.endswith(".csv")]
                if not csv_names:
                    return None
                csv_data = zf.read(csv_names[0])
        except zipfile.BadZipFile:
            logger.error("Corrupt ZIP for %s aggTrades", symbol)
            return None

        df = pl.read_csv(
            io.BytesIO(csv_data),
            has_header=True,
            schema_overrides={
                "agg_trade_id": pl.Int64,
                "price": pl.Float64,
                "quantity": pl.Float64,
                "first_trade_id": pl.Int64,
                "last_trade_id": pl.Int64,
                "transact_time": pl.Int64,
                "is_buyer_maker": pl.Boolean,
            },
        )

        # Handle column name variations
        time_col = "transact_time" if "transact_time" in df.columns else "timestamp"
        if time_col not in df.columns:
            # Try positional: 6th column is timestamp
            cols = df.columns
            if len(cols) >= 6:
                time_col = cols[5]

        # Convert timestamp (ms) to datetime
        df = df.with_columns(
            (pl.col(time_col) * 1000)
            .cast(pl.Datetime("us"))
            .dt.replace_time_zone("UTC")
            .alias("time"),
        )

        # Select output columns
        out_cols = ["time", "price", "quantity", "is_buyer_maker", "agg_trade_id"]
        available = [c for c in out_cols if c in df.columns]
        return df.select(available)
