"""Polymarket CLOB tick recorder — captures orderbook ticks to Parquet.

Records real-time bid/ask/depth for UP and DOWN tokens across multiple
assets and timeframes. Designed for dutch accumulation backtesting.

Architecture:
  TickRecorder (orchestrator)
    ├── 3x MarketScanner (one per TF, discovers markets for all assets)
    ├── 12x StreamSlot (one per asset×TF, each runs a PolymarketWSFeed)
    └── 1x TickWriter (consumes tick queue, flushes to Parquet chunks)

Usage:
    recorder = TickRecorder(
        assets={Asset.BTC, Asset.ETH, Asset.SOL, Asset.XRP},
        timeframes={Timeframe.M5, Timeframe.M15, Timeframe.H1},
        base_dir=Path("data/raw/polymarket_ticks"),
    )
    await recorder.run()
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import polars as pl

from qm.core.types import Asset, Timeframe
from qm.data.connectors.http import create_connector
from qm.data.connectors.polymarket_ws import PolymarketWSFeed
from qm.execution.polymarket.market_scanner import MarketScanner

logger = logging.getLogger(__name__)

TF_MAP = {"5m": Timeframe.M5, "15m": Timeframe.M15, "1h": Timeframe.H1}
TF_LABELS = {Timeframe.M5: "5m", Timeframe.M15: "15m", Timeframe.H1: "1h"}

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
}


@dataclass(frozen=True, slots=True)
class TickSnapshot:
    """One orderbook snapshot for both UP and DOWN tokens."""

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
        }


class StreamSlot:
    """Manages one WSS connection for a single asset×timeframe market.

    Discovers markets via MarketScanner, subscribes PolymarketWSFeed,
    snapshots the orderbook on every update, pushes to shared queue.
    """

    def __init__(
        self,
        asset: Asset,
        timeframe: Timeframe,
        tick_queue: asyncio.Queue,
        connector_factory=None,
        heartbeat_s: float = 30.0,
    ) -> None:
        self.asset = asset
        self.timeframe = timeframe
        self.tick_queue = tick_queue
        self._connector_factory = connector_factory or create_connector
        self._heartbeat_s = heartbeat_s
        self.feed: PolymarketWSFeed | None = None
        self._feed_task: asyncio.Task | None = None
        self._subscribed_cid: str = ""
        self._tick_count: int = 0

    async def run(
        self, scanner: MarketScanner, running_flag: list[bool],
    ) -> None:
        """Main loop: discover market, subscribe, snapshot, repeat."""
        label = f"{self.asset.value}/{TF_LABELS[self.timeframe]}"
        logger.info("StreamSlot %s starting", label)

        while running_flag[0]:
            try:
                # 1. Discover active market
                market = await scanner.get_active_market(self.asset)
                if market is None:
                    await asyncio.sleep(5.0)
                    continue

                # 2. Subscribe if new market
                if market.condition_id != self._subscribed_cid:
                    await self._resubscribe(market, running_flag)

                # 3. Wait for book update or heartbeat timeout
                if self.feed is None:
                    await asyncio.sleep(1.0)
                    continue

                is_heartbeat = False
                try:
                    await asyncio.wait_for(
                        self.feed.book_updated.wait(),
                        timeout=self._heartbeat_s,
                    )
                    self.feed.book_updated.clear()
                except asyncio.TimeoutError:
                    is_heartbeat = True

                # 4. Snapshot and push
                tick = self._snapshot(is_heartbeat)
                if tick is not None:
                    await self.tick_queue.put(tick)
                    self._tick_count += 1

                # 5. Near bar end? Invalidate scanner cache
                remaining = (market.window_end - datetime.now(UTC)).total_seconds()
                if remaining < 2:
                    await asyncio.sleep(max(0, remaining + 0.5))
                    scanner._cache_time = 0

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning("StreamSlot %s error: %s", label, e)
                await asyncio.sleep(5.0)

        # Cleanup
        if self.feed:
            self.feed.stop()
        logger.info("StreamSlot %s stopped (%d ticks)", label, self._tick_count)

    async def _resubscribe(
        self, market, running_flag: list[bool],
    ) -> None:
        """Stop old feed, create new one, subscribe to market tokens."""
        label = f"{self.asset.value}/{TF_LABELS[self.timeframe]}"

        if self.feed and self._feed_task:
            self.feed.stop()
            self._feed_task.cancel()

        self.feed = PolymarketWSFeed(connector_factory=self._connector_factory)
        self._feed_task = asyncio.create_task(
            self.feed.connect_and_run(
                market.token_id_up, market.token_id_down, running_flag,
            ),
        )
        self._subscribed_cid = market.condition_id
        logger.info(
            "StreamSlot %s subscribed: %s (ends %s)",
            label, market.condition_id[:16],
            market.window_end.strftime("%H:%M:%S"),
        )
        await asyncio.sleep(1.0)  # wait for initial book snapshot

    def _snapshot(self, is_heartbeat: bool) -> TickSnapshot | None:
        """Read current book state and create a TickSnapshot."""
        if self.feed is None:
            return None
        book_up = self.feed.get_book("up")
        book_dn = self.feed.get_book("down")
        if book_up is None or book_dn is None:
            return None
        # Skip if no real data yet
        if book_up.best_bid <= 0 and book_up.best_ask >= 1.0:
            return None

        return TickSnapshot(
            ts=datetime.now(UTC),
            asset=self.asset.value,
            timeframe=TF_LABELS[self.timeframe],
            condition_id=self._subscribed_cid,
            bid_up=book_up.best_bid,
            ask_up=book_up.best_ask,
            bid_dn=book_dn.best_bid,
            ask_dn=book_dn.best_ask,
            mid_up=book_up.mid,
            spread_up=book_up.spread,
            spread_dn=book_dn.spread,
            depth_bid_up=book_up.bids.get(book_up.best_bid, 0.0),
            depth_ask_up=book_up.asks.get(book_up.best_ask, 0.0),
            depth_bid_dn=book_dn.bids.get(book_dn.best_bid, 0.0),
            depth_ask_dn=book_dn.asks.get(book_dn.best_ask, 0.0),
            is_heartbeat=is_heartbeat,
        )


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
            drained = 0
            while not tick_queue.empty():
                try:
                    tick = tick_queue.get_nowait()
                    self._buffer.append(tick.to_dict())
                    drained += 1
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


class TickRecorder:
    """Orchestrator: manages 12 stream slots + 1 writer."""

    def __init__(
        self,
        assets: set[Asset],
        timeframes: set[Timeframe],
        base_dir: Path,
        heartbeat_s: float = 30.0,
        flush_interval: float = 60.0,
        flush_size: int = 1000,
    ) -> None:
        self._running_flag: list[bool] = [True]
        self._tick_queue: asyncio.Queue = asyncio.Queue()
        self._connector_factory = create_connector

        # One scanner per timeframe (each scans all assets)
        self._scanners: dict[Timeframe, MarketScanner] = {}
        for tf in timeframes:
            self._scanners[tf] = MarketScanner(
                assets=assets,
                timeframe=tf,
                connector_factory=self._connector_factory,
                min_time_remaining_sec=5.0,
            )

        # One slot per asset × timeframe
        self._slots: list[StreamSlot] = []
        for asset in sorted(assets, key=lambda a: a.value):
            for tf in sorted(timeframes, key=lambda t: t.value):
                self._slots.append(StreamSlot(
                    asset=asset,
                    timeframe=tf,
                    tick_queue=self._tick_queue,
                    connector_factory=self._connector_factory,
                    heartbeat_s=heartbeat_s,
                ))

        self._writer = TickWriter(
            base_dir=base_dir,
            flush_interval=flush_interval,
            flush_size=flush_size,
        )

        logger.info(
            "TickRecorder: %d assets × %d timeframes = %d streams → %s",
            len(assets), len(timeframes), len(self._slots), base_dir,
        )

    async def run(self) -> None:
        """Start all streams and writer, run until stopped."""
        # Start writer
        asyncio.create_task(self._writer.run(self._tick_queue, self._running_flag))

        # Start stream slots (stagger to avoid Gamma API burst)
        for slot in self._slots:
            scanner = self._scanners[slot.timeframe]
            asyncio.create_task(slot.run(scanner, self._running_flag))
            await asyncio.sleep(0.5)

        logger.info("All %d streams started", len(self._slots))

        # Periodic stats
        while self._running_flag[0]:
            await asyncio.sleep(60)
            active = sum(
                1 for s in self._slots
                if s.feed and s.feed._connected.is_set()
            )
            total_ticks = sum(s._tick_count for s in self._slots)
            logger.info(
                "Recorder: %d/%d active, %d total ticks, %d flushes, %d buffered",
                active, len(self._slots), total_ticks,
                self._writer._flush_count, len(self._writer._buffer),
            )

    def stop(self) -> None:
        """Signal all tasks to stop."""
        self._running_flag[0] = False
        logger.info("TickRecorder stopping...")
