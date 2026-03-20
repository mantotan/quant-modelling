#!/usr/bin/env python
"""Live BTC Pulse model monitor -- 5m, 15m, 1h simultaneous.

Read-only terminal monitor: streams BTC ticks from TradingView WSS,
runs all 3 Pulse models on every poll, prints market situation and
model predictions with threshold crossing markers.

Usage:
    uv run scripts/monitor_pulse.py
    uv run scripts/monitor_pulse.py --no-polymarket   # simulated odds only
    uv run scripts/monitor_pulse.py --quiet            # threshold + bar events only
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import signal
import sys
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

import aiohttp
import lightgbm as lgb
import numpy as np
import polars as pl

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from qm.core.constants import TIMEFRAME_MINUTES
from qm.core.types import Asset, PolymarketMarket, Timeframe
from qm.data.connectors.http import create_connector
from qm.data.connectors.polymarket_ws import PolymarketWSFeed
from qm.data.ingestion.bar_builder import BarBuilder
from qm.data.storage.parquet import ParquetStore
from qm.execution.polymarket.market_scanner import MarketScanner
from qm.features.live_cache import LiveFeatureCache
from qm.features.pipeline import FeaturePipeline
from qm.model.calibration.calibrator import TimeAwareCalibrator

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("monitor")

# TradingView WSS
TV_WSS_URL = "wss://data.tradingview.com/socket.io/websocket"
TV_SYMBOL = "BINANCE:BTCUSDT"

# Poll interval (seconds)
POLL_INTERVAL = 1.0

# Timeframes to monitor
TIMEFRAMES = [Timeframe.M5, Timeframe.M15, Timeframe.H1]
TF_LABELS = {Timeframe.M5: "5m", Timeframe.M15: "15m", Timeframe.H1: "1h"}
BAR_SECONDS = {
    Timeframe.M5: 300.0,
    Timeframe.M15: 900.0,
    Timeframe.H1: 3600.0,
}

# Time thresholds from knobs
_KNOBS_PATH = Path("autoresearch/best_knobs.json")
if _KNOBS_PATH.exists():
    with open(_KNOBS_PATH) as _f:
        TIME_PCTS = json.loads(_f.read()).get("time_pcts", [0.80])
else:
    TIME_PCTS = [0.80]

# All timeframes have Polymarket markets (5m, 15m, 1h)
PM_TIMEFRAMES = {Timeframe.M5, Timeframe.M15, Timeframe.H1}


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="BTC Pulse Live Monitor")
    p.add_argument(
        "--no-polymarket", action="store_true",
        help="Skip Polymarket odds polling",
    )
    p.add_argument(
        "--quiet", action="store_true",
        help="Only print threshold crossings and bar completions",
    )
    p.add_argument(
        "--model-dir", default="data/models/pulse_v2",
        help="Model directory (default: data/models/pulse_v2)",
    )
    return p.parse_args()


# -- Model loading ----------------------------------------------------

def load_models(
    model_dir: Path,
) -> dict[Timeframe, tuple[lgb.Booster, TimeAwareCalibrator | None]]:
    """Load Pulse LightGBM model + calibrator for each timeframe."""
    models: dict[Timeframe, tuple[lgb.Booster, TimeAwareCalibrator | None]] = {}
    for tf in TIMEFRAMES:
        label = TF_LABELS[tf]
        model_path = model_dir / f"BTC_{label}" / "model.lgb"
        cal_path = model_dir / f"BTC_{label}" / "calibrator.pkl"

        if not model_path.exists():
            logger.error("No model at %s -- skipping %s", model_path, label)
            continue

        model = lgb.Booster(model_file=str(model_path))
        calibrator = None
        if cal_path.exists():
            calibrator = TimeAwareCalibrator()
            calibrator.load(cal_path)
        else:
            logger.warning("No calibrator for BTC_%s", label)

        models[tf] = (model, calibrator)
        logger.info("Loaded BTC_%s model (%d trees)", label, model.num_trees())

    return models


# -- Feature warm-up --------------------------------------------------

def warm_up_caches(
    caches: dict[Timeframe, LiveFeatureCache],
) -> None:
    """Populate each TF's feature cache from historical bars."""
    store = ParquetStore(base_dir=Path("data/raw/ohlcv"))
    pipeline = FeaturePipeline()

    for tf, cache in caches.items():
        label = TF_LABELS[tf]
        bars_df = store.read_bars(Asset.BTC, tf)
        if bars_df.is_empty():
            logger.warning("No OHLCV data for BTC_%s warm-up", label)
            continue

        n = min(500, len(bars_df))
        featured = pipeline.compute(bars_df.tail(n))
        last_row = featured.row(-1, named=True)
        cache_dict = {}
        for name in pipeline.feature_names:
            val = last_row.get(name)
            if val is not None:
                cache_dict[name] = float(val)

        cache.update_history(cache_dict)
        logger.info("Warm-up BTC_%s: cached %d features from %d bars", label, len(cache_dict), n)


# -- TradingView WSS -------------------------------------------------

def _tv_encode(msg: str) -> str:
    return f"~m~{len(msg)}~m~{msg}"


def _tv_decode(raw: str) -> list[str]:
    msgs: list[str] = []
    i = 0
    while i < len(raw):
        if raw[i : i + 3] == "~m~":
            i += 3
            j = raw.index("~m~", i)
            length = int(raw[i:j])
            i = j + 3
            msgs.append(raw[i : i + length])
            i += length
        else:
            break
    return msgs


async def price_feed(
    bar_builder: BarBuilder,
    completed_bars: asyncio.Queue,
    running_flag: list[bool],
) -> None:
    """Stream BTC ticks from TradingView WSS into BarBuilder."""
    import random
    import string

    logger.info("Price feed starting: %s", TV_SYMBOL)

    while running_flag[0]:
        try:
            async with aiohttp.ClientSession() as session:
                ws = await session.ws_connect(
                    TV_WSS_URL,
                    headers={"Origin": "https://www.tradingview.com"},
                    heartbeat=30.0,
                )
                qs = "qs_" + "".join(random.choices(string.ascii_lowercase, k=12))

                await ws.send_str(_tv_encode(json.dumps(
                    {"m": "set_auth_token", "p": ["unauthorized_user_token"]},
                )))
                await ws.send_str(_tv_encode(json.dumps(
                    {"m": "quote_create_session", "p": [qs]},
                )))
                await ws.send_str(_tv_encode(json.dumps(
                    {"m": "quote_set_fields", "p": [qs, "lp", "volume"]},
                )))
                await ws.send_str(_tv_encode(json.dumps(
                    {"m": "quote_add_symbols", "p": [qs, TV_SYMBOL]},
                )))

                logger.info("Price feed connected: %s", TV_SYMBOL)
                tick_count = 0

                async for msg in ws:
                    if not running_flag[0]:
                        break
                    if msg.type != aiohttp.WSMsgType.TEXT:
                        continue
                    for m in _tv_decode(msg.data):
                        if m.startswith("~h~"):
                            await ws.send_str(_tv_encode(m))
                            continue
                        try:
                            d = json.loads(m)
                        except json.JSONDecodeError:
                            continue
                        if d.get("m") != "qsd":
                            continue
                        v = d.get("p", [None, {}])[1].get("v", {})
                        lp = v.get("lp")
                        if lp is None:
                            continue
                        vol = v.get("volume", 0)
                        now = datetime.now(UTC)
                        bars = bar_builder.on_trade(
                            Asset.BTC, float(lp), float(vol) * 0.0001, now,
                        )
                        # Queue completed bars for cache updates
                        for bar in bars:
                            await completed_bars.put(bar)
                        tick_count += 1
                        if tick_count == 1:
                            logger.info("First tick: BTC $%.2f", lp)

                await ws.close()
        except Exception:
            logger.warning("Price feed disconnected, reconnecting in 5s...")
            await asyncio.sleep(5.0)


# -- Polymarket odds (WSS primary, REST fallback) ---------------------

async def polymarket_feed(
    tf: Timeframe,
    scanner: MarketScanner,
    ws_feeds: dict[Timeframe, PolymarketWSFeed],
    pm_markets: dict[Timeframe, PolymarketMarket],
    running_flag: list[bool],
) -> None:
    """Manage WSS orderbook feed for a timeframe, with REST fallback.

    Discovers markets via scanner (REST), subscribes WSS for live orderbook.
    Also stores REST-polled market in pm_markets as fallback odds source.
    Switches at bar boundaries using window_end timing.
    """
    label = TF_LABELS[tf]
    ws_task: asyncio.Task | None = None
    subscribed_cid = ""

    async def _subscribe(market) -> None:
        nonlocal ws_task, subscribed_cid
        old_feed = ws_feeds.get(tf)
        if old_feed and ws_task is not None:
            old_feed.stop()
            ws_task.cancel()

        new_feed = PolymarketWSFeed(connector_factory=create_connector)
        ws_feeds[tf] = new_feed
        ws_task = asyncio.create_task(
            new_feed.connect_and_run(
                market.token_id_up, market.token_id_down, running_flag,
            ),
        )
        subscribed_cid = market.condition_id
        logger.info(
            "PM %s subscribed: %s (ends %s)",
            label, subscribed_cid[:16],
            market.window_end.strftime("%H:%M:%S"),
        )
        await asyncio.sleep(1.0)

    while running_flag[0]:
        try:
            market = await scanner.get_active_market(Asset.BTC)

            if market:
                pm_markets[tf] = market
                if market.condition_id != subscribed_cid:
                    await _subscribe(market)
            else:
                pm_markets.pop(tf, None)

            if market and market.window_end:
                now = datetime.now(UTC)
                secs_to_end = (market.window_end - now).total_seconds()
                if secs_to_end > 2:
                    await asyncio.sleep(min(secs_to_end - 1, 30.0))
                else:
                    await asyncio.sleep(1.0)
                    scanner._cache_time = 0
            else:
                await asyncio.sleep(10.0)

        except Exception as e:
            logger.debug("PM %s error: %s", label, e)
            await asyncio.sleep(5.0)


# -- Output formatting -----------------------------------------------

def format_price(p: float) -> str:
    """Format price compactly."""
    if p >= 1000:
        return f"{p:,.0f}"
    return f"{p:.2f}"


def print_table(
    price: float,
    rows: list[dict],
    pm_odds: dict[Timeframe, tuple[float, float]],
    pred_us: float,
) -> None:
    """Print the combined table for all timeframes."""
    now_str = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S UTC")
    header = f"--- BTC ${format_price(price)} | {now_str} "
    print(f"\n{header}{'-' * max(0, 80 - len(header))}")
    print(
        f" {'TF':<4} | {'Bar%':>5} | {'O/H/L/C':<25} | "
        f"{'Raw':>6} | {'Cal':>6} | {'Mkt':>6} | {'Edge':>7} | Side"
    )

    for r in rows:
        ohlc = (
            f"{format_price(r['open'])}/{format_price(r['high'])}/"
            f"{format_price(r['low'])}/{format_price(r['close'])}"
        )
        if r['mkt_prob'] is not None:
            mkt_str = f"{r['mkt_prob']:>.4f}"
            edge_str = f"{r['edge']:+.3f}"
        else:
            mkt_str = "   -- "
            edge_str = "    -- "
        side_str = r.get("side", "--")
        print(
            f" {r['label']:<4} | {r['pct']:>4.1f}% | {ohlc:<25} | "
            f"{r['raw_prob']:>.4f} | {r['cal_prob']:>.4f} | "
            f"{mkt_str} | {edge_str} | {side_str}"
        )

    # Market odds footer
    mkt_parts = []
    for tf in TIMEFRAMES:
        label = TF_LABELS[tf]
        if tf in pm_odds:
            mid, spread = pm_odds[tf]
            mkt_parts.append(f"{label}={mid:.2f}/{spread:.2f}")
        else:
            mkt_parts.append(f"{label}=--")
    print(f" Mkt: {' '.join(mkt_parts)} | Pred: {pred_us:.0f}us")


def print_threshold(
    tf_label: str, pct: float, raw: float, cal: float,
    mkt: float | None, edge: float | None, side: str,
) -> None:
    """Print highlighted threshold crossing."""
    mkt_str = f"Mkt={mkt:.4f}" if mkt is not None else "Mkt=--"
    edge_str = f"Edge={edge:+.3f}" if edge is not None else "Edge=--"
    print(
        f"\n>>> {tf_label} THRESHOLD {pct*100:.0f}% -- "
        f"Raw={raw:.4f} Cal={cal:.4f} {mkt_str} "
        f"{edge_str} -> {side} <<<"
    )


def print_bar_complete(bar) -> None:
    """Print bar completion summary."""
    label = TF_LABELS.get(bar.timeframe, bar.timeframe.value)
    start = bar.timestamp.strftime("%H:%M")
    end_dt = bar.timestamp + timedelta(minutes=TIMEFRAME_MINUTES[bar.timeframe])
    end = end_dt.strftime("%H:%M")
    print(
        f"\n=== {label} BAR COMPLETE {start}-{end} | "
        f"O={format_price(bar.open)} H={format_price(bar.high)} "
        f"L={format_price(bar.low)} C={format_price(bar.close)} | "
        f"Vol={bar.volume:.4f} Trades={bar.trade_count} ==="
    )


# -- Main loop --------------------------------------------------------

async def main_loop(args: argparse.Namespace) -> None:
    model_dir = Path(args.model_dir)

    print("=" * 60)
    print("  BTC Pulse Live Monitor")
    print("=" * 60)
    print(f"  Timeframes: 5m, 15m, 1h")
    print(f"  Polymarket: {'OFF' if args.no_polymarket else 'ON (5m/15m/1h)'}")
    print(f"  Mode:       {'quiet' if args.quiet else 'verbose'}")
    print(f"  Poll:       {POLL_INTERVAL*1000:.0f}ms")
    print(f"  Thresholds: {[f'{t*100:.0f}%' for t in TIME_PCTS]}")
    print("=" * 60)

    # -- Load models ----------------------------------------------
    models = load_models(model_dir)
    if not models:
        logger.error("No models loaded -- exiting")
        return

    for tf in TIMEFRAMES:
        if tf not in models:
            logger.warning("BTC_%s model not found -- will skip", TF_LABELS[tf])

    # -- Feature caches (one per TF, handles feature reordering) --
    feat_caches: dict[Timeframe, LiveFeatureCache] = {}
    for tf in TIMEFRAMES:
        if tf not in models:
            continue
        label = TF_LABELS[tf]
        cache_dir = model_dir / f"BTC_{label}"
        feat_caches[tf] = LiveFeatureCache.from_model_dir(
            cache_dir, asset=Asset.BTC, timeframe=tf,
        )

    # -- Warm-up --------------------------------------------------
    warm_up_caches(feat_caches)

    # -- BarBuilder (single instance, 3 TFs) ----------------------
    bar_builder = BarBuilder(assets=[Asset.BTC], timeframes=TIMEFRAMES)
    completed_bars: asyncio.Queue = asyncio.Queue()

    # -- Polymarket feeds (WSS primary, REST fallback) -----------
    ws_feeds: dict[Timeframe, PolymarketWSFeed] = {}
    pm_markets: dict[Timeframe, PolymarketMarket] = {}
    pm_scanners: dict[Timeframe, MarketScanner] = {}

    if not args.no_polymarket:
        for tf in PM_TIMEFRAMES:
            if tf in models:
                scanner = MarketScanner(
                    assets={Asset.BTC}, timeframe=tf,
                    connector_factory=create_connector,
                )
                scanner._cache_ttl = 2.0
                pm_scanners[tf] = scanner

    # -- Start background tasks -----------------------------------
    running_flag = [True]

    asyncio.create_task(price_feed(bar_builder, completed_bars, running_flag))

    for tf in pm_scanners:
        asyncio.create_task(
            polymarket_feed(
                tf, pm_scanners[tf], ws_feeds, pm_markets, running_flag,
            ),
        )

    # -- Threshold tracking ---------------------------------------
    last_triggered: dict[Timeframe, set[float]] = {tf: set() for tf in TIMEFRAMES}
    current_bar_id: dict[Timeframe, int] = {}
    last_print = 0.0
    last_price = 0.0

    # -- Feature pipeline for live cache updates ------------------
    pipeline = FeaturePipeline()
    recent_bars: dict[Timeframe, list] = {tf: [] for tf in TIMEFRAMES}

    def handle_shutdown(sig_num, frame):
        logger.info("Shutdown signal received")
        running_flag[0] = False

    signal.signal(signal.SIGINT, handle_shutdown)
    signal.signal(signal.SIGTERM, handle_shutdown)

    logger.info("Starting main loop (%.0fms polling)... waiting for ticks", POLL_INTERVAL * 1000)

    while running_flag[0]:
        await asyncio.sleep(POLL_INTERVAL)

        # -- Process completed bars -------------------------------
        while not completed_bars.empty():
            bar = completed_bars.get_nowait()
            tf = bar.timeframe
            print_bar_complete(bar)

            # Update feature cache for this TF
            if tf in feat_caches:
                recent_bars[tf].append(bar)
                recent_bars[tf] = recent_bars[tf][-500:]

                bars_data = {
                    "time": [b.timestamp for b in recent_bars[tf]],
                    "open": [b.open for b in recent_bars[tf]],
                    "high": [b.high for b in recent_bars[tf]],
                    "low": [b.low for b in recent_bars[tf]],
                    "close": [b.close for b in recent_bars[tf]],
                    "volume": [b.volume for b in recent_bars[tf]],
                    "trade_count": [b.trade_count for b in recent_bars[tf]],
                    "vwap": [b.vwap for b in recent_bars[tf]],
                }
                if len(recent_bars[tf]) >= 20:
                    try:
                        bars_df = pl.DataFrame(bars_data)
                        featured = pipeline.compute(bars_df)
                        last_row = featured.row(-1, named=True)
                        cache_dict = {
                            name: float(val)
                            for name in pipeline.feature_names
                            if (val := last_row.get(name)) is not None
                        }
                        feat_caches[tf].update_history(cache_dict)
                        logger.debug(
                            "Updated %s feature cache (%d features)",
                            TF_LABELS[tf], len(cache_dict),
                        )
                    except Exception as e:
                        logger.warning("Feature cache update failed for %s: %s", TF_LABELS[tf], e)

        # -- Predict for each TF ----------------------------------
        rows: list[dict] = []
        threshold_events: list[tuple] = []
        t0 = time.perf_counter_ns()

        for tf in TIMEFRAMES:
            if tf not in models:
                continue

            partial = bar_builder.get_partial_bar(Asset.BTC, tf)
            if partial is None:
                continue

            label = TF_LABELS[tf]
            bar_sec = BAR_SECONDS[tf]
            elapsed_pct = partial.elapsed_seconds / (bar_sec + 1e-10)
            last_price = partial.current_price

            # Reset thresholds on new bar
            bar_id = int(partial.window_start.timestamp())
            if bar_id != current_bar_id.get(tf):
                current_bar_id[tf] = bar_id
                last_triggered[tf] = set()

            # Compute features (reordered to match model) & predict
            model, calibrator = models[tf]
            features = feat_caches[tf].get_features(partial)
            raw_prob = float(model.predict(features.reshape(1, -1))[0])

            cal_prob = raw_prob
            if calibrator:
                cal_prob = float(calibrator.transform(
                    np.array([raw_prob]),
                    np.array([elapsed_pct]),
                )[0])

            # Market odds: prefer WSS orderbook, fall back to REST
            mkt_prob = None
            mkt_src = "none"
            ws_feed = ws_feeds.get(tf)
            if ws_feed and ws_feed._connected.is_set():
                mkt_prob = ws_feed.mid_up
                mkt_src = "ws"
            else:
                pm_market = pm_markets.get(tf)
                if pm_market:
                    mkt_prob = pm_market.mid_up
                    mkt_src = "rest"

            # Edge on the side we'd trade:
            #   UP side edge = cal_prob - mkt_prob (model thinks Up underpriced)
            #   DN side edge = (1-cal_prob) - (1-mkt_prob) = mkt_prob - cal_prob
            side = "UP" if cal_prob > 0.5 else "DN"
            if mkt_prob is not None:
                if side == "UP":
                    edge = cal_prob - mkt_prob
                else:
                    edge = mkt_prob - cal_prob
                if abs(edge) < 0.005:
                    side = "--"
                    edge = 0.0
            else:
                edge = None

            rows.append({
                "label": label,
                "pct": elapsed_pct * 100,
                "open": partial.open,
                "high": partial.high_so_far,
                "low": partial.low_so_far,
                "close": partial.current_price,
                "raw_prob": raw_prob,
                "cal_prob": cal_prob,
                "mkt_prob": mkt_prob,
                "mkt_src": mkt_src,
                "edge": edge,
                "side": side,
            })

            # Check threshold crossings
            for threshold in TIME_PCTS:
                if threshold in last_triggered[tf]:
                    continue
                if elapsed_pct >= threshold:
                    last_triggered[tf].add(threshold)
                    threshold_events.append(
                        (label, threshold, raw_prob, cal_prob, mkt_prob, edge, side),
                    )

        pred_us = (time.perf_counter_ns() - t0) / 1000

        if not rows:
            continue

        # -- Collect market odds for footer -----------------------
        pm_odds: dict[Timeframe, tuple[float, float]] = {}
        for tf in PM_TIMEFRAMES:
            ws_feed = ws_feeds.get(tf)
            if ws_feed and ws_feed._connected.is_set():
                pm_odds[tf] = (ws_feed.mid_up, ws_feed.spread)
            else:
                pm_market = pm_markets.get(tf)
                if pm_market:
                    pm_odds[tf] = (pm_market.mid_up, pm_market.spread)

        # -- Print output -----------------------------------------
        now = time.time()
        has_threshold = len(threshold_events) > 0

        # Print threshold events always
        for evt in threshold_events:
            print_threshold(*evt)

        # Print table on every poll (250ms) unless quiet
        if has_threshold or (not args.quiet and now - last_print >= POLL_INTERVAL):
            print_table(last_price, rows, pm_odds, pred_us)
            last_print = now

    # -- Shutdown -------------------------------------------------
    logger.info("Shutting down...")
    for feed in ws_feeds.values():
        feed.stop()
    logger.info("Monitor stopped.")


def main() -> None:
    args = parse_args()
    asyncio.run(main_loop(args))


if __name__ == "__main__":
    main()
