#!/usr/bin/env python
"""Dutch Accumulation Paper Trader.

Streams asset ticks + Polymarket orderbook, runs Pulse model, and displays
a real-time alpha panel for dutch book scalping (buy both UP + DOWN sides
via limit orders, hold to resolution, profit if total cost < $1).

Alphas displayed:
  - Model P(UP) raw + calibrated, edge per side
  - Full 4-price panel: bid/ask for UP and DOWN
  - Dutch cost (ask_UP + ask_DN) and guaranteed profit
  - Book depth at BBO (how much size you'd compete with)
  - Mid-price velocity (directional drift over 30s window)
  - Time remaining to resolution (seconds)
  - Limit order placement zone (bid+1c for each side)

Usage:
    uv run scripts/monitor_pulse.py
    uv run scripts/monitor_pulse.py --no-polymarket   # simulated odds only
    uv run scripts/monitor_pulse.py --timeframe 5m    # override TF
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import signal
import sys
import time
from collections import deque
from datetime import UTC, datetime, timedelta
from pathlib import Path

import aiohttp
import lightgbm as lgb
import numpy as np
import polars as pl
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from qm.core.constants import TIMEFRAME_MINUTES
from qm.core.types import Asset, PolymarketMarket, Timeframe
from qm.data.connectors.http import create_connector
from qm.data.connectors.polymarket_ws import PolymarketWSFeed
from qm.data.ingestion.bar_builder import BarBuilder
from qm.data.storage.parquet import ParquetStore
from qm.execution.polymarket.market_scanner import MarketScanner
from qm.features.live_cache import CrossAssetLiveFeatureCache, LiveFeatureCache
from qm.features.pipeline import FeaturePipeline
from qm.model.calibration.calibrator import TimeAwareCalibrator
from qm.strategy.dutch.engine import DutchAccumulationEngine, DutchConfig
from qm.strategy.dutch.fill_simulator import LimitOrderSimulator
from qm.strategy.dutch.summary_logger import DutchSummaryLogger

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("monitor")

# TradingView WSS
TV_WSS_URL = "wss://data.tradingview.com/socket.io/websocket"
TV_SYMBOLS = {
    "BTC": "BINANCE:BTCUSDT",
    "ETH": "BINANCE:ETHUSDT",
    "SOL": "BINANCE:SOLUSDT",
    "XRP": "BINANCE:XRPUSDT",
}

# Asset mapping
ASSET_MAP = {"BTC": Asset.BTC, "ETH": Asset.ETH, "SOL": Asset.SOL, "XRP": Asset.XRP}

# Poll interval (seconds)
POLL_INTERVAL = 1.0

# Display timezone
DISPLAY_TZ = ZoneInfo("Asia/Bangkok")  # GMT+7

# TF config
TF_MAP = {"5m": Timeframe.M5, "15m": Timeframe.M15, "1h": Timeframe.H1}
TF_LABELS = {Timeframe.M5: "5m", Timeframe.M15: "15m", Timeframe.H1: "1h"}
BAR_SECONDS = {Timeframe.M5: 300.0, Timeframe.M15: 900.0, Timeframe.H1: 3600.0}

# Time thresholds from knobs
_KNOBS_PATH = Path("autoresearch/best_knobs.json")
if _KNOBS_PATH.exists():
    with open(_KNOBS_PATH) as _f:
        TIME_PCTS = json.loads(_f.read()).get("time_pcts", [0.80])
else:
    TIME_PCTS = [0.80]

# Mid velocity tracking window
MID_HISTORY_SECS = 30.0


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Dutch Accumulation Paper Trader")
    p.add_argument(
        "--asset", default="BTC", choices=["BTC", "ETH", "SOL", "XRP"],
        help="Asset to trade (default: BTC)",
    )
    p.add_argument(
        "--no-polymarket", action="store_true",
        help="Skip Polymarket odds polling",
    )
    p.add_argument(
        "--timeframe", default="15m", choices=["5m", "15m", "1h"],
        help="Timeframe to monitor (default: 15m)",
    )
    p.add_argument(
        "--model-dir", default="data/models/pulse_v2",
        help="Model directory (default: data/models/pulse_v2)",
    )
    p.add_argument(
        "--dutch", action="store_true",
        help="Enable dutch accumulation paper trading",
    )
    p.add_argument(
        "--dutch-budget", type=float, default=200.0,
        help="Per-bar budget in USD (default: 200)",
    )
    p.add_argument(
        "--dutch-order-size", type=float, default=5.0,
        help="Per-order size in USD (default: 5)",
    )
    p.add_argument(
        "--dutch-tick-log", action="store_true",
        help="Enable per-tick JSONL logging (verbose)",
    )
    p.add_argument(
        "--dutch-max-side-frac", type=float, default=0.55,
        help="Max fraction of budget per side (default: 0.55)",
    )
    p.add_argument(
        "--dutch-max-per-prediction", type=float, default=100.0,
        help="Max spend per model prediction cycle (default: 100)",
    )
    p.add_argument(
        "--dutch-vwap-tol", type=float, default=0.10,
        help="Price improvement tolerance vs avg fill (default: 0.10)",
    )
    # --dutch-max-hedge-ask removed in V6 (no hedge tier)
    return p.parse_args()


# -- Model loading ----------------------------------------------------

def load_model(
    model_dir: Path, asset_label: str, tf_label: str,
) -> tuple[lgb.Booster, TimeAwareCalibrator | None]:
    """Load Pulse LightGBM or specialist model + calibrator."""
    from qm.model.specialist import SpecialistModelRouter, load_pulse_model

    sub_dir = model_dir / f"{asset_label}_{tf_label}"
    model = load_pulse_model(sub_dir)

    calibrator = None
    if not isinstance(model, SpecialistModelRouter):
        cal_path = sub_dir / "calibrator.pkl"
        if cal_path.exists():
            calibrator = TimeAwareCalibrator()
            calibrator.load(cal_path)
        else:
            logger.warning("No calibrator for %s_%s", asset_label, tf_label)

    logger.info("Loaded %s_%s model (%d trees)", asset_label, tf_label, model.num_trees())
    return model, calibrator


# -- Feature warm-up --------------------------------------------------

def warm_up_cache(
    cache: LiveFeatureCache, asset: Asset, tf: Timeframe,
) -> None:
    """Populate feature cache from historical bars."""
    store = ParquetStore(base_dir=Path("data/raw/ohlcv"))
    pipeline = FeaturePipeline()
    bars_df = store.read_bars(asset, tf)
    if bars_df.is_empty():
        logger.warning("No OHLCV data for %s/%s warm-up", asset.value, TF_LABELS[tf])
        return

    n = min(500, len(bars_df))
    featured = pipeline.compute(bars_df.tail(n))
    last_row = featured.row(-1, named=True)
    cache_dict = {}
    for name in pipeline.feature_names:
        val = last_row.get(name)
        if val is not None:
            cache_dict[name] = float(val)

    cache.update_history(cache_dict)
    logger.info("Warm-up %s/%s: cached %d features from %d bars", asset.value, TF_LABELS[tf], len(cache_dict), n)


def warm_up_btc(cache: CrossAssetLiveFeatureCache, tf: Timeframe) -> None:
    """Warm up BTC historical features for cross-asset cache."""
    store = ParquetStore(base_dir=Path("data/raw/ohlcv"))
    pipeline = FeaturePipeline()
    btc_bars = store.read_bars(Asset.BTC, tf)
    if btc_bars.is_empty():
        logger.warning("No BTC OHLCV data for cross-asset warm-up")
        return
    featured = pipeline.compute(btc_bars.tail(500))
    last_row = featured.row(-1, named=True)
    btc_cache = {
        n: float(v) for n in pipeline.feature_names
        if (v := last_row.get(n)) is not None
    }
    cache.update_btc_history(btc_cache)
    logger.info("BTC warm-up: cached %d features for cross-asset", len(btc_cache))


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
    asset_enum: Asset,
    tv_symbol: str,
    bar_builder: BarBuilder,
    completed_bars: asyncio.Queue,
    running_flag: list[bool],
) -> None:
    """Stream asset ticks from TradingView WSS into BarBuilder."""
    import random
    import string

    logger.info("Price feed starting: %s", tv_symbol)

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
                    {"m": "quote_add_symbols", "p": [qs, tv_symbol]},
                )))

                logger.info("Price feed connected: %s", tv_symbol)
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
                            asset_enum, float(lp), float(vol) * 0.0001, now,
                        )
                        for bar in bars:
                            await completed_bars.put(bar)
                        tick_count += 1
                        if tick_count == 1:
                            logger.info("First tick: %s $%.2f", asset_enum.value, lp)

                await ws.close()
        except Exception:
            logger.warning("Price feed disconnected, reconnecting in 5s...")
            await asyncio.sleep(5.0)


# -- Polymarket feed --------------------------------------------------

async def polymarket_feed(
    asset_enum: Asset,
    tf: Timeframe,
    scanner: MarketScanner,
    ws_feeds: dict[Timeframe, PolymarketWSFeed],
    pm_markets: dict[Timeframe, PolymarketMarket],
    running_flag: list[bool],
) -> None:
    """Manage WSS orderbook feed, switching at bar boundaries."""
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
            market = await scanner.get_active_market(asset_enum)

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


# -- Mid velocity tracker ---------------------------------------------

class MidTracker:
    """Track mid-price history for velocity computation."""

    def __init__(self, window_secs: float = 30.0) -> None:
        self._window = window_secs
        self._history: deque[tuple[float, float]] = deque()  # (timestamp, mid)

    def update(self, mid: float) -> None:
        now = time.time()
        self._history.append((now, mid))
        # Prune old entries
        cutoff = now - self._window * 2
        while self._history and self._history[0][0] < cutoff:
            self._history.popleft()

    def velocity(self) -> float | None:
        """Change in mid over the last window_secs. Positive = UP getting more expensive."""
        if len(self._history) < 2:
            return None
        now = time.time()
        cutoff = now - self._window
        # Find the oldest sample within window
        old_mid = None
        for ts, mid in self._history:
            if ts >= cutoff:
                old_mid = mid
                break
        if old_mid is None:
            return None
        current_mid = self._history[-1][1]
        return current_mid - old_mid


# -- Output formatting -----------------------------------------------

def format_price(p: float) -> str:
    if p >= 1000:
        return f"{p:,.0f}"
    return f"{p:.2f}"


def format_bar(pct: float, width: int = 20) -> str:
    filled = min(width, max(0, round(pct / 100 * width)))
    return "[" + "#" * filled + "." * (width - filled) + "]"


def print_alpha_panel(
    asset_label: str,
    price: float,
    partial,
    tf_label: str,
    raw_prob: float,
    cal_prob: float,
    ws_feed: PolymarketWSFeed | None,
    has_book: bool,
    mid_vel: float | None,
    pred_us: float,
) -> None:
    """Print the dutch scalping alpha panel."""
    now = datetime.now(UTC)
    now_str = now.strftime("%H:%M:%S UTC")
    elapsed_pct = partial.elapsed_seconds / (partial.remaining_seconds + partial.elapsed_seconds + 1e-10)
    remaining = partial.remaining_seconds
    w_start = partial.window_start.astimezone(DISPLAY_TZ).strftime("%H:%M")
    w_end = partial.window_end.astimezone(DISPLAY_TZ).strftime("%H:%M")

    # Header
    print(f"\033[2J\033[H", end="")  # clear screen
    print(f"{'=' * 78}")
    print(f"  {asset_label} DUTCH SCALPING MONITOR | ${format_price(price)} | {now_str}")
    print(f"  {tf_label} Window: {w_start}-{w_end}  |  "
          f"Time left: {remaining:.0f}s  |  Bar: {elapsed_pct*100:.0f}% {format_bar(elapsed_pct*100)}")
    print(f"{'=' * 78}")

    # Model predictions
    side = "UP" if cal_prob > 0.5 else "DN"
    confidence = abs(cal_prob - 0.5) * 200  # 0-100% scale
    print(f"\n  MODEL  |  Raw: {raw_prob:.4f}  Cal: {cal_prob:.4f}  "
          f"Side: {side}  Confidence: {confidence:.1f}%")

    # 4-price panel + depth
    if has_book and ws_feed:
        book_up = ws_feed.get_book("up")
        book_dn = ws_feed.get_book("down")

        bid_up = ws_feed.best_bid_up
        ask_up = ws_feed.best_ask_up
        bid_dn = ws_feed.best_bid_down
        ask_dn = ws_feed.best_ask_down
        spread_up = ask_up - bid_up
        spread_dn = ask_dn - bid_dn

        depth_ask_up = book_up.depth_at_bbo() if book_up else 0
        depth_ask_dn = book_dn.depth_at_bbo() if book_dn else 0
        depth3_ask_up = book_up.total_depth("ask", 3) if book_up else 0
        depth3_ask_dn = book_dn.total_depth("ask", 3) if book_dn else 0

        # Edge per side
        edge_up = cal_prob - ask_up          # model says UP more likely than ask price
        edge_dn = (1 - cal_prob) - ask_dn    # model says DN more likely than ask price

        print(f"\n  {'SIDE':<4} | {'Bid':>7} | {'Ask':>7} | {'Spread':>7} | "
              f"{'BBO sh':>9} | {'3L sh':>9} | {'Model':>7} | {'Edge':>7}")
        print(f"  {'-'*4}-+-{'-'*7}-+-{'-'*7}-+-{'-'*7}-+-"
              f"{'-'*9}-+-{'-'*9}-+-{'-'*7}-+-{'-'*7}")
        print(f"  {'UP':<4} | {bid_up:>7.4f} | {ask_up:>7.4f} | {spread_up:>7.4f} | "
              f"{depth_ask_up:>9.0f} | {depth3_ask_up:>9.0f} | {cal_prob:>7.4f} | {edge_up:>+7.3f}")
        print(f"  {'DN':<4} | {bid_dn:>7.4f} | {ask_dn:>7.4f} | {spread_dn:>7.4f} | "
              f"{depth_ask_dn:>9.0f} | {depth3_ask_dn:>9.0f} | {1-cal_prob:>7.4f} | {edge_dn:>+7.3f}")

        # Dutch book analysis
        dutch_taker = ask_up + ask_dn
        dutch_profit_taker = 1.0 - dutch_taker

        # Limit order dutch: place at bid+1c on each side
        limit_up = bid_up + 0.01
        limit_dn = bid_dn + 0.01
        dutch_maker = limit_up + limit_dn
        dutch_profit_maker = 1.0 - dutch_maker

        print(f"\n  DUTCH ANALYSIS")
        print(f"  {'-'*72}")
        print(f"  Taker (market):  ask_UP + ask_DN = {ask_up:.4f} + {ask_dn:.4f} = "
              f"{dutch_taker:.4f}  profit = {dutch_profit_taker:+.4f}"
              f"  {'PROFIT' if dutch_profit_taker > 0 else '  LOSS'}")
        print(f"  Maker (limit) :  (bid+1c)+(bid+1c) = {limit_up:.4f} + {limit_dn:.4f} = "
              f"{dutch_maker:.4f}  profit = {dutch_profit_maker:+.4f}"
              f"  {'PROFIT' if dutch_profit_maker > 0 else '  LOSS'}")

        # Which side is the better entry RIGHT NOW based on model?
        if edge_up > edge_dn and edge_up > 0:
            rec = f"Model favors UP (edge +{edge_up:.3f}). Buy UP first, wait for DN dip."
        elif edge_dn > edge_up and edge_dn > 0:
            rec = f"Model favors DN (edge +{edge_dn:.3f}). Buy DN first, wait for UP dip."
        elif edge_up > 0 and edge_dn > 0:
            rec = f"Both sides have edge! Dutch now."
        else:
            rec = f"No edge on either side. Wait."
        print(f"\n  >> {rec}")

        # Book depth detail (top 3 levels each side)
        print(f"\n  BOOK DEPTH (top 3 asks)")
        print(f"  {'UP asks':<35} | {'DN asks':<35}")
        print(f"  {'-'*35}-+-{'-'*35}")
        up_levels = book_up.top_levels("ask", 3) if book_up else []
        dn_levels = book_dn.top_levels("ask", 3) if book_dn else []
        for i in range(3):
            up_str = f"  {up_levels[i][0]:.4f} x {up_levels[i][1]:>8.0f} sh" if i < len(up_levels) else "  --"
            dn_str = f"  {dn_levels[i][0]:.4f} x {dn_levels[i][1]:>8.0f} sh" if i < len(dn_levels) else "  --"
            print(f"  {up_str:<35} | {dn_str:<35}")

    else:
        print(f"\n  [Polymarket orderbook not connected — waiting for WSS data]")
        edge_up = cal_prob - 0.5
        edge_dn = (1 - cal_prob) - 0.5
        print(f"  Model edge (vs 0.50):  UP={edge_up:+.3f}  DN={edge_dn:+.3f}")

    # Mid velocity
    print(f"\n  DYNAMICS")
    print(f"  {'-'*72}")
    if mid_vel is not None:
        direction = "UP getting expensive" if mid_vel > 0 else "DN getting cheap" if mid_vel < 0 else "flat"
        print(f"  Mid velocity (30s): {mid_vel:+.4f}  ({direction})")
    else:
        print(f"  Mid velocity (30s): -- (collecting data)")

    # OHLC
    print(f"  Spot OHLC: O={format_price(partial.open)} "
          f"H={format_price(partial.high_so_far)} "
          f"L={format_price(partial.low_so_far)} "
          f"C={format_price(partial.current_price)} "
          f"Vol={partial.volume_so_far:.4f}")

    # Footer
    print(f"\n  Pred: {pred_us:.0f}us | Thresholds: {[f'{t*100:.0f}%' for t in TIME_PCTS]}")
    print(f"{'=' * 78}")


def print_threshold(
    tf_label: str, pct: float, raw: float, cal: float,
    ask_up: float | None, ask_dn: float | None,
    edge_up: float | None, edge_dn: float | None,
) -> None:
    """Print highlighted threshold crossing."""
    ask_str = f"Ask UP={ask_up:.4f} DN={ask_dn:.4f}" if ask_up is not None else "Ask=--"
    print(
        f"\n>>> {tf_label} THRESHOLD {pct*100:.0f}% -- "
        f"Raw={raw:.4f} Cal={cal:.4f} "
        f"{ask_str} Edge UP={edge_up:+.3f} DN={edge_dn:+.3f} <<<"
        if edge_up is not None else
        f"\n>>> {tf_label} THRESHOLD {pct*100:.0f}% -- "
        f"Raw={raw:.4f} Cal={cal:.4f} (no market) <<<"
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


def print_dutch_panel(
    asset_label: str,
    price: float,
    partial,
    tf_label: str,
    cal_prob: float,
    ws_feed: PolymarketWSFeed | None,
    has_book: bool,
    mid_vel: float | None,
    pred_us: float,
    engine_snap: dict,
    sim_stats,
    session_stats: dict,
) -> None:
    """Print the dutch accumulation live panel."""
    now_str = datetime.now(UTC).strftime("%H:%M:%S UTC")
    elapsed_pct = partial.elapsed_seconds / (partial.remaining_seconds + partial.elapsed_seconds + 1e-10)
    remaining = partial.remaining_seconds
    w_start = partial.window_start.astimezone(DISPLAY_TZ).strftime("%H:%M")
    w_end = partial.window_end.astimezone(DISPLAY_TZ).strftime("%H:%M")

    print(f"\033[2J\033[H", end="")
    print(f"{'=' * 78}")
    print(f"  {asset_label} DUTCH ACCUMULATION | ${format_price(price)} | {now_str}")
    print(f"  {tf_label} {w_start}-{w_end}  |  {remaining:.0f}s left  |  "
          f"{elapsed_pct*100:.0f}% {format_bar(elapsed_pct*100)}")
    print(f"{'=' * 78}")

    budget_spent = engine_snap["total_cost"]
    budget_total = engine_snap.get("budget_remaining", 0) + budget_spent
    print(f"\n  MODEL P(UP)={cal_prob:.4f}  |  Budget: ${budget_spent:.2f}/${budget_total:.2f} spent")

    # Inventory table
    s_up = engine_snap["shares_up"]
    s_dn = engine_snap["shares_dn"]
    c_up = engine_snap["cost_up"]
    c_dn = engine_snap["cost_dn"]
    matched = engine_snap["matched"]
    avg_pc = engine_snap["avg_pair_cost"]
    unm_up = engine_snap["unmatched_up"]
    unm_dn = engine_snap["unmatched_dn"]

    print(f"\n  {'INVENTORY':<14} {'Shares':>8} {'Cost':>9} {'Avg Price':>10}")
    if s_up > 0:
        print(f"  {'UP':<14} {s_up:>8.1f} ${c_up:>8.2f} {c_up/s_up:>10.4f}" if s_up > 0 else "")
    if s_dn > 0:
        print(f"  {'DN':<14} {s_dn:>8.1f} ${c_dn:>8.2f} {c_dn/s_dn:>10.4f}" if s_dn > 0 else "")
    if matched > 0:
        matched_cost = avg_pc * matched
        profit_str = f"profit ${matched - matched_cost:.2f}" if avg_pc < 1.0 else "LOSS"
        print(f"  {'Matched':<14} {matched:>8.1f} ${matched_cost:>8.2f} {avg_pc:>10.4f}/pair  {profit_str}")
    if unm_up > 0:
        print(f"  {'Unmatched UP':<14} {unm_up:>8.1f}")
    if unm_dn > 0:
        print(f"  {'Unmatched DN':<14} {unm_dn:>8.1f}")
    if s_up == 0 and s_dn == 0:
        print(f"  (empty)")

    # Projected P/L
    if matched > 0 or unm_up > 0 or unm_dn > 0:
        tc = engine_snap["total_cost"]
        payout_up = matched + unm_up  # if UP wins
        payout_dn = matched + unm_dn  # if DN wins
        risk_budget = engine_snap.get("risk_budget", 0)
        worst_loss = engine_snap.get("worst_case_loss", 0)
        print(f"\n  PROJECTED P/L  (risk={worst_loss:.1f}/{risk_budget:.1f})")
        print(f"  If UP: ${payout_up:.2f} - ${tc:.2f} = ${payout_up - tc:+.2f}")
        print(f"  If DN: ${payout_dn:.2f} - ${tc:.2f} = ${payout_dn - tc:+.2f}")

        conv_up = engine_snap.get("conviction_up", 0.5)
        conv_dn = engine_snap.get("conviction_dn", 0.5)
        eff_pc = engine_snap.get("effective_max_pc", 1.03)
        print(f"\n  CONVICTION  UP={conv_up:.2f}  DN={conv_dn:.2f}  max_pc={eff_pc:.3f}")

    # Pair cost
    pair_cost_live = engine_snap.get("pair_cost_live", 0)
    if pair_cost_live > 0:
        print(f"\n  PAIR COST  {pair_cost_live:.4f}")

    # Market data
    if has_book and ws_feed:
        print(f"\n  MARKET   bid_UP={ws_feed.best_bid_up:.4f} ask_UP={ws_feed.best_ask_up:.4f}"
              f" | bid_DN={ws_feed.best_bid_down:.4f} ask_DN={ws_feed.best_ask_down:.4f}")
        cheap_up = cal_prob - ws_feed.best_ask_up
        cheap_dn = (1 - cal_prob) - ws_feed.best_ask_down
        vel_str = f"{mid_vel:+.4f}" if mid_vel is not None else "--"
        print(f"  SCORES   cheap_UP={cheap_up:+.3f}  cheap_DN={cheap_dn:+.3f}  velocity={vel_str}/30s")
    else:
        print(f"\n  [Waiting for Polymarket orderbook...]")

    # Fill stats
    if sim_stats:
        print(f"\n  FILLS    placed={sim_stats.placed} filled={sim_stats.filled} "
              f"partial={sim_stats.partial} chased={sim_stats.chased} "
              f"cancelled={sim_stats.cancelled} avg_ticks={sim_stats.avg_fill_ticks:.1f}")

    # Last decisions
    decisions = engine_snap.get("last_decisions", [])
    if decisions:
        print(f"\n  LAST DECISIONS")
        for d in decisions[-5:]:
            print(f"  {d}")

    # Session stats
    w = session_stats.get("wins", 0)
    l = session_stats.get("losses", 0)
    pnl = session_stats.get("total_pnl", 0)
    avg_pc_s = session_stats.get("avg_pair_cost", 0)
    if w + l > 0:
        print(f"\n  SESSION: {w}W {l}L  PnL=${pnl:.2f}  avg_pair={avg_pc_s:.3f}")

    print(f"\n  Pred: {pred_us:.0f}us")
    print(f"{'=' * 78}")


# -- State persistence ------------------------------------------------

DUTCH_KNOBS_DIR = Path("autoresearch/dutch")


def _resolve_dutch_knobs(asset_label: str, tf_label: str) -> Path:
    """Per-pair knobs first, then shared fallback."""
    pair_path = DUTCH_KNOBS_DIR / f"knobs_{asset_label}_{tf_label}.json"
    if pair_path.exists():
        return pair_path
    return DUTCH_KNOBS_DIR / "knobs.json"


def load_dutch_config(
    args: argparse.Namespace, asset_label: str, tf_label: str, tf: Timeframe,
) -> tuple[DutchConfig, dict]:
    """Load DutchConfig from per-pair knobs (if exists), CLI args as fallback.

    Resolution order: knobs_{ASSET}_{TF}.json → knobs.json → CLI defaults.
    Returns (config, sim_kwargs) where sim_kwargs are for LimitOrderSimulator.
    """
    kwargs: dict = {
        "bar_budget": args.dutch_budget,
        "order_size": args.dutch_order_size,
        "max_side_fraction": args.dutch_max_side_frac,
        "max_per_prediction": args.dutch_max_per_prediction,
        "vwap_tolerance": args.dutch_vwap_tol,
        "bar_seconds": BAR_SECONDS[tf],
    }
    sim_kwargs: dict = {}

    knobs_path = _resolve_dutch_knobs(asset_label, tf_label)
    if knobs_path.exists():
        with open(knobs_path) as f:
            knobs = json.load(f)
        for key, val in knobs.items():
            if key.startswith("_") or key == "fill_simulator":
                continue
            if key in DutchConfig.__dataclass_fields__ and key != "bar_seconds":
                kwargs[key] = val
        sim_kwargs = knobs.get("fill_simulator", {})
        logger.info("Dutch config loaded from %s", knobs_path)

    return DutchConfig(**kwargs), sim_kwargs


def _save_dutch_state(state_file: Path, session: dict, pending: list) -> None:
    """Save dutch session state for crash recovery (per-TF)."""
    try:
        state = {
            "session": {k: v for k, v in session.items() if not k.startswith("_")},
            "pending_count": len(pending),
            "saved_at": datetime.now(UTC).isoformat(),
        }
        state_file.parent.mkdir(parents=True, exist_ok=True)
        with open(state_file, "w") as f:
            json.dump(state, f, indent=2)
    except Exception as e:
        logger.warning("Failed to save dutch state: %s", e)


# -- Main loop --------------------------------------------------------

async def main_loop(args: argparse.Namespace) -> None:
    model_dir = Path(args.model_dir)
    tf = TF_MAP[args.timeframe]
    tf_label = args.timeframe

    # -- Asset resolution -----------------------------------------
    asset_label = args.asset
    asset_enum = ASSET_MAP[asset_label]
    tv_symbol = TV_SYMBOLS[asset_label]

    dutch_mode = getattr(args, "dutch", False)

    print("=" * 60)
    if dutch_mode:
        print(f"  {asset_label} Dutch Accumulation Paper Trader")
    else:
        print(f"  {asset_label} Dutch Scalping Alpha Monitor")
    print("=" * 60)
    print(f"  Asset:       {asset_label}")
    print(f"  Timeframe:   {tf_label}")
    print(f"  Polymarket:  {'OFF' if args.no_polymarket else 'ON (WSS orderbook)'}")
    if dutch_mode:
        print(f"  Dutch:       ON (budget=${args.dutch_budget:.0f}, order=${args.dutch_order_size:.0f})")
    print(f"  Poll:        {POLL_INTERVAL*1000:.0f}ms")
    print(f"  Thresholds:  {[f'{t*100:.0f}%' for t in TIME_PCTS]}")
    print("=" * 60)

    # -- Load model -----------------------------------------------
    model, calibrator = load_model(model_dir, asset_label, tf_label)

    # -- Feature cache (reordered to model) -----------------------
    cache_dir = model_dir / f"{asset_label}_{tf_label}"
    feat_cache = LiveFeatureCache.from_model_dir(
        cache_dir, asset=asset_enum, timeframe=tf,
    )

    # -- Warm-up --------------------------------------------------
    warm_up_cache(feat_cache, asset_enum, tf)

    # -- BTC cross-asset feed (non-BTC models only) ---------------
    btc_bar_builder: BarBuilder | None = None
    btc_completed_bars: asyncio.Queue | None = None
    if isinstance(feat_cache, CrossAssetLiveFeatureCache):
        warm_up_btc(feat_cache, tf)
        btc_bar_builder = BarBuilder(assets=[Asset.BTC], timeframes=[tf])
        btc_completed_bars = asyncio.Queue()

    # -- BarBuilder (single TF) -----------------------------------
    bar_builder = BarBuilder(assets=[asset_enum], timeframes=[tf])
    completed_bars: asyncio.Queue = asyncio.Queue()

    # -- Polymarket feed ------------------------------------------
    ws_feeds: dict[Timeframe, PolymarketWSFeed] = {}
    pm_markets: dict[Timeframe, PolymarketMarket] = {}

    if not args.no_polymarket:
        scanner = MarketScanner(
            assets={asset_enum}, timeframe=tf,
            connector_factory=create_connector,
            min_time_remaining_sec=5.0,
        )
        scanner._cache_ttl = 2.0

    # -- Mid velocity tracker -------------------------------------
    mid_tracker = MidTracker(window_secs=MID_HISTORY_SECS)

    # -- Dutch accumulation setup ---------------------------------
    dutch_engine: DutchAccumulationEngine | None = None
    dutch_sim: LimitOrderSimulator | None = None
    dutch_logger: DutchSummaryLogger | None = None
    dutch_session: dict = {"wins": 0, "losses": 0, "total_pnl": 0.0, "avg_pair_cost": 0.0, "bars": 0}
    dutch_pending_resolutions: list[dict] = []
    dutch_bar_condition_id: str = ""

    if dutch_mode:
        dutch_config, sim_kwargs = load_dutch_config(args, asset_label, tf_label, tf)
        dutch_engine = DutchAccumulationEngine(dutch_config)
        dutch_sim = LimitOrderSimulator(**sim_kwargs) if sim_kwargs else LimitOrderSimulator()
        logger.info(
            "Dutch V7.3 config: budget=$%.0f, order=$%.0f, pair_cost<%.2f, "
            "conv_skip=%.2f, conv_size=%.2f, onesided_cap=$%.0f",
            dutch_config.bar_budget, dutch_config.order_size,
            dutch_config.max_marginal_pair_cost,
            dutch_config.conviction_buy_skip,
            dutch_config.conviction_size_floor,
            dutch_config.max_onesided_cost,
        )
        dutch_logger = DutchSummaryLogger(
            base_dir=Path("data/dutch_paper"),
            asset=asset_label,
            timeframe=tf_label,
        )
        dutch_engine.set_event_callback(dutch_logger.log_event)
        # Load persisted session state (per-asset-TF to avoid collision)
        dutch_state_file = Path(f"data/dutch_paper/state_{asset_label}_{tf_label}.json")
        if dutch_state_file.exists():
            try:
                with open(dutch_state_file) as f:
                    saved = json.load(f)
                if "session" in saved:
                    dutch_session.update(saved["session"])
                    logger.info("Restored dutch session: %dW %dL PnL=$%.2f",
                                dutch_session["wins"], dutch_session["losses"],
                                dutch_session["total_pnl"])
            except Exception as e:
                logger.warning("Failed to load dutch state: %s", e)
        logger.info("Dutch accumulation enabled: budget=$%.0f, order=$%.0f, edge>%.2f",
                     args.dutch_budget, args.dutch_order_size, dutch_config.cheap_threshold)

    # -- Start background tasks -----------------------------------
    running_flag = [True]

    asyncio.create_task(price_feed(asset_enum, tv_symbol, bar_builder, completed_bars, running_flag))

    if btc_bar_builder is not None and btc_completed_bars is not None:
        asyncio.create_task(price_feed(
            Asset.BTC, "BINANCE:BTCUSDT", btc_bar_builder,
            btc_completed_bars, running_flag,
        ))
        logger.info("BTC cross-asset price feed started")

    if not args.no_polymarket:
        asyncio.create_task(
            polymarket_feed(
                asset_enum, tf, scanner, ws_feeds, pm_markets, running_flag,
            ),
        )

    # -- Threshold tracking ---------------------------------------
    last_triggered: set[float] = set()
    current_bar_id: int = 0
    last_price: float = 0.0

    # -- Feature pipeline for live cache updates ------------------
    pipeline = FeaturePipeline()
    recent_bars: list = []

    def handle_shutdown(sig_num, frame):
        logger.info("Shutdown signal received")
        running_flag[0] = False

    signal.signal(signal.SIGINT, handle_shutdown)
    signal.signal(signal.SIGTERM, handle_shutdown)

    # -- Timing cadences for event-driven loop --------------------
    last_model_time = 0.0
    last_display_time = 0.0
    last_state_save = time.time()
    MODEL_INTERVAL = 1.0      # model inference every 1s
    DISPLAY_INTERVAL = 0.5    # display update every 0.5s
    STATE_SAVE_INTERVAL = 300.0  # state persistence every 5 min
    cal_prob = 0.5
    raw_prob = 0.5
    pred_us = 0.0

    logger.info("Starting main loop (%s)... waiting for ticks",
                "event-driven" if dutch_mode else f"{POLL_INTERVAL*1000:.0f}ms polling")

    while running_flag[0]:
        # -- WAIT: event-driven (dutch) or polling (non-dutch) ----
        ws_feed = ws_feeds.get(tf)
        if dutch_mode and ws_feed and ws_feed._connected.is_set():
            try:
                await asyncio.wait_for(ws_feed.book_updated.wait(), timeout=1.0)
                ws_feed.book_updated.clear()
            except asyncio.TimeoutError:
                pass
        else:
            await asyncio.sleep(POLL_INTERVAL)

        # -- Process completed bars -------------------------------
        while not completed_bars.empty():
            bar = completed_bars.get_nowait()
            if bar.timeframe != tf:
                continue
            print_bar_complete(bar)

            # Update feature cache
            recent_bars.append(bar)
            recent_bars[:] = recent_bars[-500:]

            bars_data = {
                "time": [b.timestamp for b in recent_bars],
                "open": [b.open for b in recent_bars],
                "high": [b.high for b in recent_bars],
                "low": [b.low for b in recent_bars],
                "close": [b.close for b in recent_bars],
                "volume": [b.volume for b in recent_bars],
                "trade_count": [b.trade_count for b in recent_bars],
                "vwap": [b.vwap for b in recent_bars],
            }
            if len(recent_bars) >= 20:
                try:
                    bars_df = pl.DataFrame(bars_data)
                    featured = pipeline.compute(bars_df)
                    last_row = featured.row(-1, named=True)
                    cache_dict = {
                        name: float(val)
                        for name in pipeline.feature_names
                        if (val := last_row.get(name)) is not None
                    }
                    feat_cache.update_history(cache_dict)
                    logger.debug("Updated feature cache (%d features)", len(cache_dict))
                except Exception as e:
                    logger.warning("Feature cache update failed: %s", e)

        # -- Get partial bar --------------------------------------
        partial = bar_builder.get_partial_bar(asset_enum, tf)
        if partial is None:
            continue

        last_price = partial.current_price
        bar_id = int(partial.window_start.timestamp())
        elapsed_pct = partial.elapsed_seconds / (BAR_SECONDS[tf] + 1e-10)

        # Reset thresholds on new bar
        if bar_id != current_bar_id:
            # Dutch: finalize previous bar
            if dutch_mode and dutch_engine and current_bar_id != 0:
                # Cancel unfilled orders and release pending sell reservations
                cancelled = dutch_sim.cancel_all()
                for order in cancelled:
                    dutch_engine.on_order_cancelled(order)
                # Create summary (outcome pending — will be filled by resolution)
                summary = dutch_engine.resolve("")
                summary.fill_stats = {
                    "orders_placed": dutch_sim.stats.placed,
                    "orders_filled": dutch_sim.stats.filled,
                    "partial_fills": dutch_sim.stats.partial,
                    "would_fill_count": dutch_sim.stats.would_fill,
                    "avg_fill_ticks": round(dutch_sim.stats.avg_fill_ticks, 1),
                    "chased": dutch_sim.stats.chased,
                    "cancelled": dutch_sim.stats.cancelled,
                    "expired": dutch_sim.stats.expired,
                }
                # Queue for resolution via Gamma API
                if dutch_bar_condition_id:
                    dutch_pending_resolutions.append({
                        "condition_id": dutch_bar_condition_id,
                        "summary": summary,
                        "bar_id": current_bar_id,
                    })
                    logger.info(
                        "Dutch bar %d queued for resolution (matched=%.1f, cost=$%.2f)",
                        current_bar_id, summary.inventory.get("matched", 0),
                        summary.cost.get("total", 0),
                    )
                # Reset for new bar
                dutch_engine.reset()
                dutch_sim.reset()

            # Set up new bar
            if dutch_mode and dutch_engine:
                pm_market = pm_markets.get(tf)
                cid = pm_market.condition_id if pm_market else ""
                dutch_bar_condition_id = cid
                w_s = partial.window_start.astimezone(DISPLAY_TZ).strftime("%H:%M")
                w_e = partial.window_end.astimezone(DISPLAY_TZ).strftime("%H:%M")
                dutch_engine.set_bar_info(
                    bar_id=bar_id,
                    condition_id=cid,
                    window_start=w_s,
                    window_end=w_e,
                )

            current_bar_id = bar_id
            last_triggered = set()

        # -- Model inference at 1Hz (expensive ~1ms) ---------------
        now = time.time()
        if now - last_model_time >= MODEL_INTERVAL:
            # Inject BTC context from parallel BarBuilder (cross-asset)
            if btc_bar_builder is not None and isinstance(feat_cache, CrossAssetLiveFeatureCache):
                btc_partial = btc_bar_builder.get_partial_bar(Asset.BTC, tf)
                if btc_partial is not None:
                    feat_cache.set_btc_partial(btc_partial)

            t0 = time.perf_counter_ns()
            features = feat_cache.get_features(partial)
            raw_prob = float(model.predict(features.reshape(1, -1))[0])
            cal_prob = raw_prob
            if calibrator:
                cal_prob = float(calibrator.transform(
                    np.array([raw_prob]),
                    np.array([elapsed_pct]),
                )[0])
            pred_us = (time.perf_counter_ns() - t0) / 1000
            last_model_time = now

        # -- Check market data ------------------------------------
        pm_market = pm_markets.get(tf)
        ws_feed = ws_feeds.get(tf)

        # Verify market matches current bar by deriving bar start from window_end
        # (Gamma API startDate is market creation time, NOT bar boundary)
        market_matches = True
        if pm_market and pm_market.window_end:
            bar_secs = int(BAR_SECONDS[tf])
            market_bar_start = int(pm_market.window_end.timestamp()) - bar_secs
            if market_bar_start != bar_id:
                market_matches = False

        has_book = (
            market_matches
            and ws_feed is not None
            and ws_feed._connected.is_set()
            and ws_feed.best_bid_up > 0
            and ws_feed.best_ask_up < 1
        )

        # Update mid tracker
        if has_book and ws_feed:
            mid_tracker.update(ws_feed.mid_up)

        mid_vel = mid_tracker.velocity()

        # -- Check threshold crossings ----------------------------
        for threshold in TIME_PCTS:
            if threshold in last_triggered:
                continue
            if elapsed_pct >= threshold:
                last_triggered.add(threshold)
                if has_book and ws_feed:
                    print_threshold(
                        tf_label, threshold, raw_prob, cal_prob,
                        ws_feed.best_ask_up, ws_feed.best_ask_down,
                        cal_prob - ws_feed.best_ask_up,
                        (1 - cal_prob) - ws_feed.best_ask_down,
                    )
                else:
                    print_threshold(
                        tf_label, threshold, raw_prob, cal_prob,
                        None, None, None, None,
                    )

        # -- Dutch tick processing ----------------------------------
        if dutch_mode and dutch_engine and dutch_sim:
            book_up = ws_feed.get_book("up") if ws_feed and has_book else None
            book_dn = ws_feed.get_book("down") if ws_feed and has_book else None

            # Engine decides orders
            orders = dutch_engine.on_tick(elapsed_pct, cal_prob, book_up, book_dn)
            # V7.5: Cancel pending orders on flip kill (matches sweep behavior).
            # cancel_all() is a no-op after first call per bar (returns []).
            if dutch_engine.flip_killed and not orders:
                for c_order in dutch_sim.cancel_all():
                    dutch_engine.on_order_cancelled(c_order)
            for order in orders:
                dutch_sim.place(order)

            # Simulator processes fills
            fills = dutch_sim.on_tick(elapsed_pct, book_up, book_dn)
            for fill in fills:
                dutch_engine.on_fill(fill.order, fill.fill_price, fill.filled_shares)

            # Optional tick logging
            if getattr(args, "dutch_tick_log", False) and dutch_logger:
                dutch_logger.log_tick(bar_id, {
                    "time_pct": round(elapsed_pct, 4),
                    "cal_prob": round(cal_prob, 4),
                    "has_book": has_book,
                    "snap": dutch_engine.snapshot(),
                    "pending_orders": len(dutch_sim.pending_orders),
                })

        # -- Check dutch pending resolutions (every 30s) -----------
        if (
            dutch_mode
            and dutch_pending_resolutions
            and not args.no_polymarket
            and time.time() - dutch_session.get("_last_resolution_check", 0) >= 30.0
        ):
            dutch_session["_last_resolution_check"] = time.time()
            for item in dutch_pending_resolutions[:]:
                try:
                    status = await scanner.get_market_status(
                        item["condition_id"], asset=asset_enum,
                    )
                    if status and status.get("resolved", False):
                        outcome_str = status.get("outcome", "")
                        outcome = "UP" if outcome_str.lower() in ("up", "yes") else "DN"
                        summary = item["summary"]
                        summary.compute_pnl(outcome)
                        if dutch_logger:
                            dutch_logger.log_bar(summary)
                        profit = summary.pnl.get("profit", 0)
                        pair_cost = summary.cost.get("avg_pair_cost", 1.0)
                        dutch_session["total_pnl"] += profit
                        dutch_session["bars"] += 1
                        dutch_session["_sum_pair_cost"] = (
                            dutch_session.get("_sum_pair_cost", 0) + pair_cost
                        )
                        dutch_session["avg_pair_cost"] = (
                            dutch_session["_sum_pair_cost"] / dutch_session["bars"]
                        )
                        if profit >= 0:
                            dutch_session["wins"] += 1
                        else:
                            dutch_session["losses"] += 1
                        dutch_pending_resolutions.remove(item)
                        logger.info(
                            "Dutch bar %d resolved %s: PnL=$%.2f (matched=%.1f, pair_cost=%.3f)",
                            item["bar_id"], outcome, profit,
                            summary.inventory.get("matched", 0), pair_cost,
                        )
                except Exception as e:
                    logger.debug("Resolution check failed: %s", e)
            # Cap pending list to prevent unbounded growth
            if len(dutch_pending_resolutions) > 20:
                dropped = len(dutch_pending_resolutions) - 20
                dutch_pending_resolutions[:] = dutch_pending_resolutions[-20:]
                logger.warning("Dropped %d stale pending resolutions", dropped)

        # -- Display at cadence ------------------------------------
        now_disp = time.time()
        if now_disp - last_display_time >= DISPLAY_INTERVAL:
            last_display_time = now_disp
            if dutch_mode and dutch_engine:
                print_dutch_panel(
                    asset_label=asset_label,
                    price=last_price,
                    partial=partial,
                    tf_label=tf_label,
                    cal_prob=cal_prob,
                    ws_feed=ws_feed,
                    has_book=has_book,
                    mid_vel=mid_vel,
                    pred_us=pred_us,
                    engine_snap=dutch_engine.snapshot(),
                    sim_stats=dutch_sim.stats if dutch_sim else None,
                    session_stats=dutch_session,
                )
            else:
                print_alpha_panel(
                    asset_label=asset_label,
                    price=last_price,
                    partial=partial,
                    tf_label=tf_label,
                    raw_prob=raw_prob,
                    cal_prob=cal_prob,
                    ws_feed=ws_feed,
                    has_book=has_book,
                    mid_vel=mid_vel,
                    pred_us=pred_us,
                )

        # -- State persistence (every 5 min) -----------------------
        if dutch_mode and now_disp - last_state_save >= STATE_SAVE_INTERVAL:
            last_state_save = now_disp
            _save_dutch_state(dutch_state_file, dutch_session, dutch_pending_resolutions)

    # -- Shutdown -------------------------------------------------
    logger.info("Shutting down...")
    if dutch_mode:
        _save_dutch_state(dutch_state_file, dutch_session, dutch_pending_resolutions)
    if dutch_logger:
        dutch_logger.close()
    for feed in ws_feeds.values():
        feed.stop()
    logger.info("Monitor stopped.")


def main() -> None:
    args = parse_args()
    asyncio.run(main_loop(args))


if __name__ == "__main__":
    main()
