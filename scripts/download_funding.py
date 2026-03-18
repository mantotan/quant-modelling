#!/usr/bin/env python
"""Download historical funding rates from Binance Futures API.

Usage:
    python scripts/download_funding.py
    python scripts/download_funding.py --assets BTC,ETH
    python scripts/download_funding.py --start 2022-01-01 --end 2025-12-31
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
import time
from datetime import date
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from qm.core.types import Asset
from qm.data.historical.funding_rate import BinanceFundingRateDownloader
from qm.data.storage.parquet import ParquetStore

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Download historical funding rates from Binance")
    parser.add_argument(
        "--assets", type=str, default="BTC,ETH,SOL,XRP",
        help="Comma-separated asset list (default: BTC,ETH,SOL,XRP)",
    )
    parser.add_argument(
        "--start", type=str, default=None,
        help="Start date YYYY-MM-DD (default: symbol launch date)",
    )
    parser.add_argument(
        "--end", type=str, default=None,
        help="End date YYYY-MM-DD (default: yesterday)",
    )
    parser.add_argument(
        "--data-dir", type=str, default="data/raw/funding",
        help="Output directory for Parquet files (default: data/raw/funding)",
    )
    parser.add_argument(
        "--concurrent", type=int, default=4,
        help="Max concurrent API requests (default: 4)",
    )
    return parser.parse_args()


async def main() -> None:
    args = parse_args()

    assets = [Asset(a.strip()) for a in args.assets.split(",")]
    start_date = date.fromisoformat(args.start) if args.start else None
    end_date = date.fromisoformat(args.end) if args.end else None

    store = ParquetStore(Path(args.data_dir))
    downloader = BinanceFundingRateDownloader(
        store, max_concurrent=args.concurrent
    )

    t0 = time.monotonic()
    stats = await downloader.download_all(assets, start_date, end_date)
    elapsed = time.monotonic() - t0

    logger.info(
        "Done in %.1fs — %d API pages, %d rows, %d skipped, %d failed",
        elapsed, stats["downloaded"], stats["rows"],
        stats["skipped"], stats["failed"],
    )


if __name__ == "__main__":
    asyncio.run(main())
