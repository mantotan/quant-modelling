#!/usr/bin/env python
"""Download derivatives metrics from Binance Vision.

Downloads OI, long/short ratios, and taker ratios at 5-minute granularity.

Usage:
    python scripts/download_derivatives.py
    python scripts/download_derivatives.py --assets BTC,ETH
    python scripts/download_derivatives.py --start 2024-01-01
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
from qm.data.historical.binance_vision import BinanceVisionDownloader
from qm.data.storage.parquet import ParquetStore

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


def parse_assets(s: str) -> list[Asset]:
    mapping = {"BTC": Asset.BTC, "ETH": Asset.ETH, "SOL": Asset.SOL, "XRP": Asset.XRP}
    return [mapping[a.strip().upper()] for a in s.split(",") if a.strip().upper() in mapping]


async def main() -> None:
    parser = argparse.ArgumentParser(description="Download derivatives metrics from Binance Vision")
    parser.add_argument("--assets", type=str, default="BTC,ETH,SOL,XRP")
    parser.add_argument("--start", type=str, default=None, help="Start date YYYY-MM-DD (default: 2020-09-01)")
    parser.add_argument("--end", type=str, default=None, help="End date YYYY-MM-DD (default: yesterday)")
    parser.add_argument("--concurrent", type=int, default=4)
    args = parser.parse_args()

    assets = parse_assets(args.assets)
    start_date = date.fromisoformat(args.start) if args.start else None
    end_date = date.fromisoformat(args.end) if args.end else None

    # Metrics store uses separate base dir (no timeframe partition)
    metrics_store = ParquetStore(base_dir=Path("data/raw/metrics"))
    # Klines store for the downloader (not used for metrics, but required by constructor)
    klines_store = ParquetStore(base_dir=Path("data/raw/ohlcv"))

    downloader = BinanceVisionDownloader(
        parquet_store=klines_store,
        max_concurrent=args.concurrent,
    )

    logger.info("=" * 60)
    logger.info("Binance Vision Derivatives Metrics Download")
    logger.info("=" * 60)
    logger.info("Assets: %s", [a.value for a in assets])
    logger.info("Start:  %s", start_date or "2020-09-01")
    logger.info("End:    %s", end_date or "yesterday")

    t0 = time.time()
    stats = await downloader.download_metrics(
        metrics_store=metrics_store,
        assets=assets,
        start_date=start_date,
        end_date=end_date,
    )
    elapsed = time.time() - t0

    logger.info("=" * 60)
    logger.info("Download complete in %.1f seconds", elapsed)
    logger.info("Stats: %s", stats)
    logger.info("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
