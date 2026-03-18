#!/usr/bin/env python
"""Record live Polymarket odds for crypto 5m binary markets.

Polls the Gamma API every 15 seconds and stores snapshots.
Run this continuously to build ground truth odds data for Pulse model.

Usage:
    # Dev mode (Parquet fallback, no TimescaleDB needed):
    python scripts/record_polymarket.py --parquet-dir data/raw/polymarket_snapshots

    # Production mode (TimescaleDB):
    python scripts/record_polymarket.py

    # Custom assets and interval:
    python scripts/record_polymarket.py --assets BTC,ETH --poll-interval 10
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import signal
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from qm.core.types import Asset
from qm.data.connectors.polymarket_recorder import PolymarketOddsRecorder

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Record Polymarket odds")
    parser.add_argument(
        "--assets", type=str, default="BTC,ETH,SOL,XRP",
        help="Comma-separated assets (default: BTC,ETH,SOL,XRP)",
    )
    parser.add_argument(
        "--poll-interval", type=float, default=15.0,
        help="Seconds between polls (default: 15)",
    )
    parser.add_argument(
        "--parquet-dir", type=str, default=None,
        help="Parquet output dir for dev mode (default: use TimescaleDB)",
    )
    parser.add_argument(
        "--db-url", type=str, default=None,
        help="TimescaleDB URL (default: from TIMESCALEDB_URL env var)",
    )
    return parser.parse_args()


def parse_assets(s: str) -> list[Asset]:
    mapping = {"BTC": Asset.BTC, "ETH": Asset.ETH, "SOL": Asset.SOL, "XRP": Asset.XRP}
    return [mapping[a.strip().upper()] for a in s.split(",") if a.strip().upper() in mapping]


async def main() -> None:
    args = parse_args()
    assets = parse_assets(args.assets)

    timescale = None
    parquet_dir = None

    if args.parquet_dir:
        parquet_dir = Path(args.parquet_dir)
        parquet_dir.mkdir(parents=True, exist_ok=True)
        logger.info("Storage: Parquet (%s)", parquet_dir)
    elif args.db_url:
        from qm.data.storage.timescale import TimescaleWriter
        timescale = TimescaleWriter(args.db_url)
        await timescale.connect()
        await timescale.init_schema()
        logger.info("Storage: TimescaleDB")
    else:
        # Try env var, fall back to parquet
        import os
        db_url = os.environ.get("TIMESCALEDB_URL")
        if db_url:
            from qm.data.storage.timescale import TimescaleWriter
            timescale = TimescaleWriter(db_url)
            await timescale.connect()
            await timescale.init_schema()
            logger.info("Storage: TimescaleDB (from env)")
        else:
            parquet_dir = Path("data/raw/polymarket_snapshots")
            parquet_dir.mkdir(parents=True, exist_ok=True)
            logger.info("Storage: Parquet fallback (%s) -- set TIMESCALEDB_URL for DB mode", parquet_dir)

    recorder = PolymarketOddsRecorder(
        timescale=timescale,
        parquet_dir=parquet_dir,
        poll_interval=args.poll_interval,
        assets=assets,
    )

    # Handle graceful shutdown
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, recorder.stop)
        except NotImplementedError:
            # Windows doesn't support add_signal_handler
            pass

    try:
        await recorder.run()
    except KeyboardInterrupt:
        recorder.stop()
        logger.info("Interrupted by user")
    finally:
        if timescale:
            await timescale.close()


if __name__ == "__main__":
    asyncio.run(main())
