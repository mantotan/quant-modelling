#!/usr/bin/env python
"""Download historical funding rates from Binance.

Two backends:
  vision (default): Binance Vision monthly ZIPs (no API key, not blocked)
  api:              Binance Futures REST API (may be blocked by ISP/firewall)

Usage:
    python scripts/download_funding.py --source vision
    python scripts/download_funding.py --source vision --assets BTC,ETH
    python scripts/download_funding.py --source api --assets BTC,ETH
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
import time
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from qm.core.types import Asset
from qm.data.historical.funding_rate import (
    BinanceFundingRateDownloader,
    BinanceVisionFundingDownloader,
)
from qm.data.storage.parquet import ParquetStore

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Download historical funding rates from Binance",
    )
    p.add_argument(
        "--source", choices=["vision", "api"], default="vision",
        help="Download backend: vision (default, unblocked) or api (REST)",
    )
    p.add_argument(
        "--assets", type=str, default="BTC,ETH,SOL,XRP",
        help="Comma-separated asset list (default: BTC,ETH,SOL,XRP)",
    )
    p.add_argument(
        "--start", type=str, default=None,
        help="Start date YYYY-MM-DD (default: symbol launch date)",
    )
    p.add_argument(
        "--end", type=str, default=None,
        help="End date YYYY-MM-DD (default: last complete month / yesterday)",
    )
    p.add_argument(
        "--data-dir", type=str, default="data/raw/funding",
        help="Output directory (default: data/raw/funding)",
    )
    p.add_argument(
        "--concurrent", type=int, default=4,
        help="Max concurrent downloads (default: 4)",
    )
    return p.parse_args()


async def main() -> None:
    args = parse_args()

    assets = [Asset(a.strip()) for a in args.assets.split(",")]
    start_date = date.fromisoformat(args.start) if args.start else None
    end_date = date.fromisoformat(args.end) if args.end else None

    store = ParquetStore(Path(args.data_dir))

    if args.source == "vision":
        downloader = BinanceVisionFundingDownloader(
            store, max_concurrent=args.concurrent,
        )
        logger.info("Using Binance Vision backend (monthly ZIPs)")
    else:
        downloader = BinanceFundingRateDownloader(
            store, max_concurrent=args.concurrent,
        )
        logger.info("Using Binance REST API backend")

    t0 = time.monotonic()
    stats = await downloader.download_all(assets, start_date, end_date)
    elapsed = time.monotonic() - t0

    logger.info(
        "Done in %.1fs — %d downloaded, %d rows, %d skipped, %d failed",
        elapsed, stats["downloaded"], stats["rows"],
        stats["skipped"], stats["failed"],
    )


if __name__ == "__main__":
    asyncio.run(main())
