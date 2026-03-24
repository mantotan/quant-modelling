"""Tick Parquet writer — shared between tick recorder and live paper trader.

Writes TickSnapshot objects to Hive-partitioned Parquet chunks:
  data/raw/polymarket_ticks/asset={A}/timeframe={TF}/date={D}/ticks_XXXXXX.parquet
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import polars as pl

logger = logging.getLogger(__name__)

TICK_SCHEMA = {
    "ts": pl.Datetime("us", "UTC"),
    "asset": pl.Utf8,
    "timeframe": pl.Utf8,
    "condition_id": pl.Utf8,
    "bid_up": pl.Float64,
    "ask_up": pl.Float64,
    "bid_dn": pl.Float64,
    "ask_dn": pl.Float64,
    "mid_up": pl.Float64,
    "spread_up": pl.Float64,
    "spread_dn": pl.Float64,
    "depth_bid_up": pl.Float64,
    "depth_ask_up": pl.Float64,
    "depth_bid_dn": pl.Float64,
    "depth_ask_dn": pl.Float64,
    "is_heartbeat": pl.Boolean,
    "is_stale": pl.Boolean,
    "spot_price": pl.Float64,
    "window_start": pl.Datetime("us", "UTC"),
    "window_end": pl.Datetime("us", "UTC"),
    "elapsed_pct": pl.Float64,
    "cal_prob": pl.Float64,
    "is_inference": pl.Boolean,
    # PartialBar snapshot (populated on inference ticks only, null otherwise)
    "pb_open": pl.Float64,
    "pb_high": pl.Float64,
    "pb_low": pl.Float64,
    "pb_close": pl.Float64,
    "pb_volume": pl.Float64,
    "pb_trade_count": pl.Int64,
    "pb_elapsed_s": pl.Float64,
    "pb_remaining_s": pl.Float64,
    # BTC cross-asset PartialBar (for non-BTC models, inference ticks only)
    "btc_open": pl.Float64,
    "btc_high": pl.Float64,
    "btc_low": pl.Float64,
    "btc_close": pl.Float64,
    "btc_volume": pl.Float64,
    "btc_trade_count": pl.Int64,
    "btc_elapsed_s": pl.Float64,
    "btc_remaining_s": pl.Float64,
}


@dataclass(frozen=True, slots=True)
class TickSnapshot:
    """One orderbook snapshot for both UP and DOWN tokens + spot price."""

    ts: datetime
    asset: str
    timeframe: str
    condition_id: str
    bid_up: float
    ask_up: float
    bid_dn: float
    ask_dn: float
    mid_up: float
    spread_up: float
    spread_dn: float
    depth_bid_up: float
    depth_ask_up: float
    depth_bid_dn: float
    depth_ask_dn: float
    is_heartbeat: bool
    is_stale: bool
    spot_price: float
    window_start: datetime
    window_end: datetime
    elapsed_pct: float = 0.0
    cal_prob: float = 0.5
    is_inference: bool = False
    # PartialBar snapshot (populated on inference ticks only)
    pb_open: float | None = None
    pb_high: float | None = None
    pb_low: float | None = None
    pb_close: float | None = None
    pb_volume: float | None = None
    pb_trade_count: int | None = None
    pb_elapsed_s: float | None = None
    pb_remaining_s: float | None = None
    # BTC cross-asset PartialBar (for non-BTC models)
    btc_open: float | None = None
    btc_high: float | None = None
    btc_low: float | None = None
    btc_close: float | None = None
    btc_volume: float | None = None
    btc_trade_count: int | None = None
    btc_elapsed_s: float | None = None
    btc_remaining_s: float | None = None

    def to_dict(self) -> dict:
        return {
            "ts": self.ts,
            "asset": self.asset,
            "timeframe": self.timeframe,
            "condition_id": self.condition_id,
            "bid_up": self.bid_up,
            "ask_up": self.ask_up,
            "bid_dn": self.bid_dn,
            "ask_dn": self.ask_dn,
            "mid_up": self.mid_up,
            "spread_up": self.spread_up,
            "spread_dn": self.spread_dn,
            "depth_bid_up": self.depth_bid_up,
            "depth_ask_up": self.depth_ask_up,
            "depth_bid_dn": self.depth_bid_dn,
            "depth_ask_dn": self.depth_ask_dn,
            "is_heartbeat": self.is_heartbeat,
            "is_stale": self.is_stale,
            "spot_price": self.spot_price,
            "window_start": self.window_start,
            "window_end": self.window_end,
            "elapsed_pct": self.elapsed_pct,
            "cal_prob": self.cal_prob,
            "is_inference": self.is_inference,
            "pb_open": self.pb_open,
            "pb_high": self.pb_high,
            "pb_low": self.pb_low,
            "pb_close": self.pb_close,
            "pb_volume": self.pb_volume,
            "pb_trade_count": self.pb_trade_count,
            "pb_elapsed_s": self.pb_elapsed_s,
            "pb_remaining_s": self.pb_remaining_s,
            "btc_open": self.btc_open,
            "btc_high": self.btc_high,
            "btc_low": self.btc_low,
            "btc_close": self.btc_close,
            "btc_volume": self.btc_volume,
            "btc_trade_count": self.btc_trade_count,
            "btc_elapsed_s": self.btc_elapsed_s,
            "btc_remaining_s": self.btc_remaining_s,
        }


class TickWriter:
    """Consumes TickSnapshots from a queue and writes to Parquet chunks.

    Writes per-flush numbered chunk files (ticks_000001.parquet, etc.)
    to avoid expensive read+concat+write on each flush.
    Polars reads all chunks natively: pl.read_parquet("dir/ticks_*.parquet")
    """

    def __init__(
        self,
        base_dir: Path,
        flush_interval: float = 60.0,
        flush_size: int = 1000,
    ) -> None:
        self._base_dir = base_dir
        self._flush_interval = flush_interval
        self._flush_size = flush_size
        self._buffer: list[dict] = []
        self._flush_count: int = 0
        self._last_flush: float = time.time()

    async def run(
        self, tick_queue: asyncio.Queue, running_flag: list[bool],
    ) -> None:
        """Consumer loop: drain queue, buffer, flush periodically."""
        logger.info("TickWriter started (flush every %ds or %d ticks)",
                     int(self._flush_interval), self._flush_size)

        while running_flag[0]:
            # Drain queue
            while not tick_queue.empty():
                try:
                    tick = tick_queue.get_nowait()
                    self._buffer.append(tick.to_dict())
                except asyncio.QueueEmpty:
                    break

            # Flush if needed
            now = time.time()
            if (
                len(self._buffer) >= self._flush_size
                or (self._buffer and now - self._last_flush >= self._flush_interval)
            ):
                self._flush()

            await asyncio.sleep(0.5)

        # Final flush on shutdown
        self._flush()
        logger.info("TickWriter stopped (%d flushes total)", self._flush_count)

    def _flush(self) -> None:
        """Write buffered ticks to per-chunk Parquet files."""
        if not self._buffer:
            return

        try:
            df = pl.DataFrame(self._buffer, schema=TICK_SCHEMA)

            # Group by (asset, timeframe) and write per-date chunk files
            for (asset, tf), group in df.group_by(["asset", "timeframe"]):
                date_str = group["ts"][0].strftime("%Y-%m-%d")
                out_dir = self._base_dir / f"asset={asset}" / f"timeframe={tf}" / f"date={date_str}"
                out_dir.mkdir(parents=True, exist_ok=True)

                existing = sorted(out_dir.glob("ticks_*.parquet"))
                chunk_num = len(existing)
                path = out_dir / f"ticks_{chunk_num:06d}.parquet"
                group.write_parquet(path)

            n = len(self._buffer)
            self._buffer.clear()
            self._flush_count += 1
            self._last_flush = time.time()
            logger.info("Flushed %d ticks (chunk #%d)", n, self._flush_count)

        except Exception as e:
            logger.warning("Flush failed: %s (buffer retained, %d ticks)", e, len(self._buffer))
