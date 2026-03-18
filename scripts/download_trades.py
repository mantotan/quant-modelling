#!/usr/bin/env python
"""Download historical aggTrades from Binance Vision.

Provides real tick-by-tick trade data for constructing honest
intra-bar training samples (no interpolation needed).

Usage:
    python scripts/download_trades.py --assets BTC --start 2026-01-01
    python scripts/download_trades.py --assets BTC,ETH --start 2024-01-01
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
from qm.data.historical.binance_vision import BinanceAggTradesDownloader
from qm.data.storage.parquet import ParquetStore

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Download Binance aggTrades")
    parser.add_argument(
        "--assets", type=str, default="BTC",
        help="Comma-separated assets (default: BTC)",
    )
    parser.add_argument(
        "--start", type=str, default="2026-01-01",
        help="Start date YYYY-MM-DD (default: 2026-01-01)",
    )
    parser.add_argument(
        "--end", type=str, default=None,
        help="End date YYYY-MM-DD (default: yesterday)",
    )
    parser.add_argument(
        "--data-dir", type=str, default="data/raw/trades",
        help="Output directory (default: data/raw/trades)",
    )
    parser.add_argument(
        "--concurrent", type=int, default=4,
        help="Max concurrent downloads (default: 4)",
    )
    return parser.parse_args()


def parse_assets(s: str) -> list[Asset]:
    mapping = {"BTC": Asset.BTC, "ETH": Asset.ETH, "SOL": Asset.SOL, "XRP": Asset.XRP}
    return [mapping[a.strip().upper()] for a in s.split(",") if a.strip().upper() in mapping]


async def main() -> None:
    args = parse_args()
    assets = parse_assets(args.assets)
    start_date = date.fromisoformat(args.start)
    end_date = date.fromisoformat(args.end) if args.end else None

    store = ParquetStore(base_dir=Path(args.data_dir))
    downloader = BinanceAggTradesDownloader(
        trades_store=store,
        max_concurrent=args.concurrent,
    )

    logger.info("=" * 60)
    logger.info("Binance AggTrades Download")
    logger.info("=" * 60)
    logger.info("Assets:  %s", [a.value for a in assets])
    logger.info("Start:   %s", start_date)
    logger.info("End:     %s", end_date or "yesterday")
    logger.info("Output:  %s", args.data_dir)
    logger.info("=" * 60)

    t0 = time.time()
    stats = await downloader.download_all(
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
