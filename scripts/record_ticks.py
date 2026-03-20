#!/usr/bin/env python
"""Record Polymarket CLOB orderbook ticks to Parquet.

Streams real-time bid/ask/depth for UP and DOWN tokens across
multiple assets and timeframes. Designed for dutch accumulation
backtesting — run continuously to build historical tick data.

Output: data/raw/polymarket_ticks/asset=BTC/timeframe=15m/date=YYYY-MM-DD/ticks_NNNNNN.parquet

Usage:
    uv run scripts/record_ticks.py
    uv run scripts/record_ticks.py --assets BTC,ETH --timeframes 5m,15m
    uv run scripts/record_ticks.py --output-dir data/raw/polymarket_ticks
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import signal
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from qm.core.types import Asset, Timeframe
from qm.data.connectors.tick_recorder import TickRecorder

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("record_ticks")

ASSET_MAP = {"BTC": Asset.BTC, "ETH": Asset.ETH, "SOL": Asset.SOL, "XRP": Asset.XRP}
TF_MAP = {"5m": Timeframe.M5, "15m": Timeframe.M15, "1h": Timeframe.H1}


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Polymarket CLOB Tick Recorder")
    p.add_argument(
        "--assets", default="BTC,ETH,SOL,XRP",
        help="Comma-separated assets (default: BTC,ETH,SOL,XRP)",
    )
    p.add_argument(
        "--timeframes", default="5m,15m,1h",
        help="Comma-separated timeframes (default: 5m,15m,1h)",
    )
    p.add_argument(
        "--output-dir", default="data/raw/polymarket_ticks",
        help="Output directory (default: data/raw/polymarket_ticks)",
    )
    p.add_argument(
        "--heartbeat-interval", type=float, default=30.0,
        help="Heartbeat interval in seconds (default: 30)",
    )
    p.add_argument(
        "--flush-interval", type=float, default=60.0,
        help="Max seconds between Parquet flushes (default: 60)",
    )
    p.add_argument(
        "--flush-size", type=int, default=1000,
        help="Max ticks before flush (default: 1000)",
    )
    return p.parse_args()


async def main_loop(args: argparse.Namespace) -> None:
    assets = {ASSET_MAP[a.strip()] for a in args.assets.split(",") if a.strip() in ASSET_MAP}
    timeframes = {TF_MAP[t.strip()] for t in args.timeframes.split(",") if t.strip() in TF_MAP}

    if not assets or not timeframes:
        logger.error("No valid assets or timeframes specified")
        return

    print("=" * 60)
    print("  Polymarket CLOB Tick Recorder")
    print("=" * 60)
    print(f"  Assets:     {', '.join(sorted(a.value for a in assets))}")
    print(f"  Timeframes: {', '.join(sorted(t.value for t in timeframes))}")
    print(f"  Streams:    {len(assets) * len(timeframes)}")
    print(f"  Output:     {args.output_dir}")
    print(f"  Flush:      every {args.flush_interval:.0f}s or {args.flush_size} ticks")
    print("=" * 60)

    recorder = TickRecorder(
        assets=assets,
        timeframes=timeframes,
        base_dir=Path(args.output_dir),
        heartbeat_s=args.heartbeat_interval,
        flush_interval=args.flush_interval,
        flush_size=args.flush_size,
    )

    def handle_shutdown(sig_num, frame):
        logger.info("Shutdown signal received")
        recorder.stop()

    signal.signal(signal.SIGINT, handle_shutdown)
    signal.signal(signal.SIGTERM, handle_shutdown)

    try:
        await recorder.run()
    except KeyboardInterrupt:
        recorder.stop()

    logger.info("Recorder stopped.")


def main() -> None:
    args = parse_args()
    asyncio.run(main_loop(args))


if __name__ == "__main__":
    main()
