#!/usr/bin/env python
"""Download historical klines from Binance Vision and validate.

Usage:
    python scripts/download_historical.py
    python scripts/download_historical.py --assets BTC,ETH --timeframes 5m,15m
    python scripts/download_historical.py --start 2024-01-01

Run this in background while coding — takes 15-30 minutes.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
import time
from datetime import date, timedelta
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from qm.core.types import Asset, Timeframe
from qm.data.historical.binance_vision import BinanceVisionDownloader, ASSET_TO_SYMBOL
from qm.data.quality.reconciler import run_full_reconciliation
from qm.data.storage.parquet import ParquetStore

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Download historical klines from Binance Vision")
    parser.add_argument(
        "--assets", type=str, default="BTC,ETH,SOL,XRP",
        help="Comma-separated asset list (default: BTC,ETH,SOL,XRP)",
    )
    parser.add_argument(
        "--timeframes", type=str, default="5m,15m,1h",
        help="Comma-separated timeframes (default: 5m,15m,1h)",
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
        "--data-dir", type=str, default="data/raw/ohlcv",
        help="Output directory for Parquet files",
    )
    parser.add_argument(
        "--validate", action="store_true", default=True,
        help="Run reconciliation after download (default: True)",
    )
    parser.add_argument(
        "--no-validate", action="store_false", dest="validate",
    )
    parser.add_argument(
        "--concurrent", type=int, default=4,
        help="Max concurrent downloads (default: 4)",
    )
    return parser.parse_args()


def parse_assets(s: str) -> list[Asset]:
    mapping = {"BTC": Asset.BTC, "ETH": Asset.ETH, "SOL": Asset.SOL, "XRP": Asset.XRP}
    return [mapping[a.strip().upper()] for a in s.split(",") if a.strip().upper() in mapping]


def parse_timeframes(s: str) -> list[Timeframe]:
    mapping = {"1m": Timeframe.M1, "5m": Timeframe.M5, "15m": Timeframe.M15, "1h": Timeframe.H1}
    return [mapping[t.strip()] for t in s.split(",") if t.strip() in mapping]


async def main() -> None:
    args = parse_args()

    assets = parse_assets(args.assets)
    timeframes = parse_timeframes(args.timeframes)
    start_date = date.fromisoformat(args.start) if args.start else None
    end_date = date.fromisoformat(args.end) if args.end else None
    data_dir = Path(args.data_dir)

    logger.info("=" * 60)
    logger.info("Binance Vision Historical Data Download")
    logger.info("=" * 60)
    logger.info("Assets:     %s", [a.value for a in assets])
    logger.info("Timeframes: %s", [t.value for t in timeframes])
    logger.info("Start:      %s", start_date or "symbol launch date")
    logger.info("End:        %s", end_date or "yesterday")
    logger.info("Output:     %s", data_dir)
    logger.info("Concurrent: %d", args.concurrent)
    logger.info("=" * 60)

    store = ParquetStore(base_dir=data_dir)
    downloader = BinanceVisionDownloader(
        parquet_store=store,
        max_concurrent=args.concurrent,
    )

    t0 = time.time()
    stats = await downloader.download_all(
        assets=assets,
        timeframes=timeframes,
        start_date=start_date,
        end_date=end_date,
    )
    elapsed = time.time() - t0

    logger.info("=" * 60)
    logger.info("Download complete in %.1f seconds", elapsed)
    logger.info("Stats: %s", stats)
    logger.info("=" * 60)

    # Validation
    if args.validate:
        logger.info("Running data reconciliation...")
        all_passed = True

        for asset in assets:
            for tf in timeframes:
                bars_df = store.read_bars(asset, tf)
                if bars_df.is_empty():
                    logger.warning("No data for %s/%s — skipping validation", asset.value, tf.value)
                    continue

                # Cross-timeframe check: 1m→5m, 5m→15m
                bars_coarse = None
                coarse_tf = None
                cross_tf_pairs = {Timeframe.M1: Timeframe.M5, Timeframe.M5: Timeframe.M15, Timeframe.M15: Timeframe.H1}
                if tf in cross_tf_pairs:
                    target_coarse = cross_tf_pairs[tf]
                    bars_coarse_df = store.read_bars(asset, target_coarse)
                    if not bars_coarse_df.is_empty():
                        bars_coarse = bars_coarse_df
                        coarse_tf = target_coarse

                report = run_full_reconciliation(
                    bars_df, asset, tf,
                    bars_coarse=bars_coarse,
                    coarse_tf=coarse_tf,
                )

                if report.status == "FAIL":
                    all_passed = False
                    logger.error("FAIL: %s", report)
                elif report.status == "WARN":
                    logger.warning("WARN: %s", report)
                else:
                    logger.info("PASS: %s", report)

        if all_passed:
            logger.info("All reconciliation checks passed!")
        else:
            logger.error("Some reconciliation checks failed — investigate before training")


if __name__ == "__main__":
    asyncio.run(main())
