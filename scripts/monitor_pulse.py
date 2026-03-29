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
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

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

# State save interval
STATE_SAVE_INTERVAL = 300.0  # 5 minutes

# Display interval
DISPLAY_INTERVAL = 2.0


@dataclass
class TFState:
    """Per-timeframe state for multi-TF Dutch paper trading."""

    tf: Timeframe
    tf_label: str
    model: Any
    calibrator: Any
    feat_cache: LiveFeatureCache
    dutch_engine: DutchAccumulationEngine | None = None
    dutch_sim: LimitOrderSimulator | None = None
    dutch_logger: DutchSummaryLogger | None = None
    dutch_session: dict = field(default_factory=lambda: {
        "wins": 0, "losses": 0, "total_pnl": 0.0,
        "avg_pair_cost": 0.0, "bars": 0,
    })
    dutch_pending_resolutions: list = field(default_factory=list)
    dutch_bar_condition_id: str = ""
    # Divergence strategy (runs alongside Dutch)
    divergence_engine: Any = None
    divergence_sim: LimitOrderSimulator | None = None
    divergence_logger: DutchSummaryLogger | None = None
    divergence_session: dict = field(default_factory=lambda: {
        "wins": 0, "losses": 0, "total_pnl": 0.0, "bars": 0,
    })
    divergence_pending_resolutions: list = field(default_factory=list)
    # Live trading (Divergence on real CLOB)
    divergence_live_router: Any = None
    live_safety: Any = None
    live_trade_logger: Any = None
    scanner: MarketScanner | None = None
    ws_feeds: dict = field(default_factory=dict)
    pm_markets: dict = field(default_factory=dict)
    mid_tracker: Any = None  # MidTracker, initialized post-creation
    current_bar_id: int = 0
    last_triggered: set = field(default_factory=set)
    cal_prob: float = 0.5
    raw_prob: float = 0.5
    pred_us: float = 0.0
    last_model_time: float = 0.0
    dutch_state_file: Path | None = None
    recent_bars: list = field(default_factory=list)
    _market_matches: bool = True


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
        "--timeframes", default="5m,15m,1h",
        help="Comma-separated timeframes (default: 5m,15m,1h)",
    )
    p.add_argument(
        "--timeframe", default=None, choices=["5m", "15m", "1h"],
        help="Single timeframe (deprecated — use --timeframes)",
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
    p.add_argument(
        "--magnitude-gate", type=float, default=0.0,
        help="Skip ticks where |cal_prob - 0.5| < threshold (default: 0 = disabled)",
    )
    p.add_argument(
        "--divergence", action="store_true",
        help="Enable Divergence strategy alongside Dutch (model-vs-market edge trading)",
    )
    p.add_argument(
        "--div-min-edge", type=float, default=0.03,
        help="Minimum model-vs-market edge for Divergence (default: 0.03)",
    )
    p.add_argument(
        "--div-kelly", type=float, default=0.25,
        help="Kelly fraction for Divergence sizing (default: 0.25)",
    )
    p.add_argument(
        "--div-order-size", type=float, default=5.0,
        help="Per-order size for Divergence (default: 5.0)",
    )
    # Live trading
    p.add_argument(
        "--live", action="store_true",
        help="Enable LIVE Divergence trading on Polymarket CLOB (real money)",
    )
    p.add_argument(
        "--live-order-size", type=float, default=2.0,
        help="Max USD per order in live mode (default: 2.0)",
    )
    p.add_argument(
        "--live-max-daily-loss", type=float, default=50.0,
        help="Kill switch: stop live if daily loss exceeds this (default: 50)",
    )
    p.add_argument(
        "--dry-run", action="store_true",
        help="Live mode but orders not submitted to CLOB (dry-run verification)",
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
                            asset_enum, float(lp), 0.001, now,
                        )
                        for bar in bars:
                            await completed_bars.put(bar)
                            logger.info("BarBuilder completed: %s %s", bar.timeframe.value, bar.timestamp)
                        tick_count += 1
                        if tick_count == 1:
                            logger.info("First tick: %s $%.2f", asset_enum.value, lp)
                        if tick_count % 50 == 0:
                            logger.info("Price feed alive: %d ticks", tick_count)

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
                # Don't switch to a FUTURE bar while we're inside a current bar.
                # But DO allow switching if the new market is for the bar we're
                # actually in (fixes initial wrong-bar subscription after restart).
                current = pm_markets.get(tf)
                now_utc = datetime.now(UTC)
                skip = False
                if (current and current.window_end
                        and current.condition_id != market.condition_id
                        and now_utc < current.window_end):
                    # Current bar still active. Only switch if new market's
                    # window contains now (i.e. it's the bar we're actually in).
                    if market.window_end and market.window_end > now_utc:
                        bar_secs_check = int(BAR_SECONDS[tf])
                        new_bar_start = int(market.window_end.timestamp()) - bar_secs_check
                        new_bar_start_dt = datetime.fromtimestamp(new_bar_start, tz=UTC)
                        if now_utc < new_bar_start_dt:
                            skip = True  # New market is for a future bar
                if not skip:
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
    model_ready: bool = True,
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
    if model_ready:
        side = "UP" if cal_prob > 0.5 else "DN"
        confidence = abs(cal_prob - 0.5) * 200  # 0-100% scale
        print(f"\n  MODEL  |  Raw: {raw_prob:.4f}  Cal: {cal_prob:.4f}  "
              f"Side: {side}  Confidence: {confidence:.1f}%")
    else:
        print("\n  MODEL  |  -- (waiting for first prediction) --")

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
    model_ready: bool = True,
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
    if model_ready:
        model_str = f"P(UP)={cal_prob:.4f}"
    else:
        model_str = "P(UP)=-- (waiting)"
    print(f"\n  MODEL {model_str}  |  Budget: ${budget_spent:.2f}/${budget_total:.2f} spent")

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


# -- Helper functions for per-TF processing --------------------------


async def _finalize_dutch_bar(state: TFState) -> None:
    """Cancel orders, resolve bar, queue for resolution polling."""
    if not state.dutch_engine or not state.dutch_sim:
        return
    cancelled = state.dutch_sim.cancel_all()
    for order in cancelled:
        state.dutch_engine.on_order_cancelled(order)
    summary = state.dutch_engine.resolve("")
    summary.fill_stats = {
        "orders_placed": state.dutch_sim.stats.placed,
        "orders_filled": state.dutch_sim.stats.filled,
        "partial_fills": state.dutch_sim.stats.partial,
        "would_fill_count": state.dutch_sim.stats.would_fill,
        "avg_fill_ticks": round(state.dutch_sim.stats.avg_fill_ticks, 1),
        "chased": state.dutch_sim.stats.chased,
        "cancelled": state.dutch_sim.stats.cancelled,
        "expired": state.dutch_sim.stats.expired,
    }
    if state.dutch_bar_condition_id:
        state.dutch_pending_resolutions.append({
            "condition_id": state.dutch_bar_condition_id,
            "summary": summary,
            "bar_id": state.current_bar_id,
        })
        logger.info(
            "Dutch %s bar %d queued for resolution (matched=%.1f, cost=$%.2f)",
            state.tf_label, state.current_bar_id,
            summary.inventory.get("matched", 0),
            summary.cost.get("total", 0),
        )
    state.dutch_engine.reset()
    state.dutch_sim.reset()

    # Divergence bar finalization (parallel to Dutch)
    if state.divergence_engine and state.divergence_sim:
        div_cancelled = state.divergence_sim.cancel_all()
        for order in div_cancelled:
            state.divergence_engine.on_order_cancelled(order)
        div_summary = state.divergence_engine.resolve("")
        div_summary.fill_stats = {
            "orders_placed": state.divergence_sim.stats.placed,
            "orders_filled": state.divergence_sim.stats.filled,
        }
        if state.dutch_bar_condition_id:
            state.divergence_pending_resolutions.append({
                "condition_id": state.dutch_bar_condition_id,
                "summary": div_summary,
                "bar_id": state.current_bar_id,
            })
        state.divergence_engine.reset()
        state.divergence_sim.reset()

        # Cancel live CLOB orders at bar end
        if state.divergence_live_router:
            await state.divergence_live_router.cancel_all()
            if state.live_safety:
                state.live_safety.record_bar_end(state.tf_label)
                safety_path = Path(f"data/divergence_live/safety_{state.tf_label}.json")
                state.live_safety.save_state(safety_path)


def _setup_new_bar(
    state: TFState,
    bar_id: int,
    pm_market: PolymarketMarket | None,
    *,
    window_start_str: str | None = None,
    window_end_str: str | None = None,
) -> None:
    """Reset engine/sim and set bar info for a new bar."""
    if not state.dutch_engine:
        return
    cid = pm_market.condition_id if pm_market else ""
    state.dutch_bar_condition_id = cid
    w_s = window_start_str or str(bar_id)
    w_e = window_end_str or str(bar_id + int(BAR_SECONDS[state.tf]))
    state.dutch_engine.set_bar_info(
        bar_id=bar_id,
        condition_id=cid,
        window_start=w_s,
        window_end=w_e,
    )
    if state.divergence_engine:
        state.divergence_engine.set_bar_info(
            bar_id=bar_id,
            condition_id=cid,
            window_start=w_s,
            window_end=w_e,
        )
    if state.divergence_live_router and pm_market:
        state.divergence_live_router.set_market(pm_market)


def _run_inference(
    state: TFState, partial, elapsed_pct: float,
    btc_bar_builder: BarBuilder | None,
) -> None:
    """Run model prediction and update state probabilities."""
    from qm.strategy.dutch.tick_processor import run_inference

    btc_partial = None
    if btc_bar_builder is not None:
        btc_partial = btc_bar_builder.get_partial_bar(Asset.BTC, state.tf)

    t0 = time.perf_counter_ns()
    state.raw_prob, state.cal_prob, features = run_inference(
        state.model, state.calibrator, state.feat_cache,
        partial, elapsed_pct, btc_partial,
    )
    state.pred_us = (time.perf_counter_ns() - t0) / 1000
    state.last_model_time = time.time()
    state._last_inference_partial = partial  # Cache for tick recording
    state._last_inference_btc_partial = btc_partial  # Cache BTC cross-asset for recording
    state._last_inference_features = features  # Full feature vector for parity
    state._last_inference_elapsed_pct = elapsed_pct  # Exact elapsed_pct at inference time


def _dutch_tick(
    state: TFState, elapsed_pct: float, book_up, book_dn,
    args: argparse.Namespace, bar_id: int,
) -> None:
    """Run Dutch engine on_tick + simulator fills."""
    from qm.strategy.dutch.tick_processor import process_tick

    if not state.dutch_engine or not state.dutch_sim:
        return

    # Only process when model has run this bar
    if state.last_model_time > 0:
        # Magnitude gate: skip low-confidence ticks
        mag_gate = getattr(args, "magnitude_gate", 0.0)
        if mag_gate > 0 and abs(state.cal_prob - 0.5) < mag_gate:
            # Skip this tick — same as sweep replay behavior.
            # Engine still processes sells on non-gated ticks.
            orders, fills = [], []
        else:
            orders, fills = process_tick(
                elapsed_pct, state.cal_prob, book_up, book_dn,
                state.dutch_engine, state.dutch_sim,
            )
    else:
        orders, fills = [], []

    # Optional tick logging (includes spot_price + book BBO for replay parity)
    if getattr(args, "dutch_tick_log", False) and state.dutch_logger:
        state.dutch_logger.log_tick(bar_id, {
            "time_pct": round(elapsed_pct, 4),
            "cal_prob": round(state.cal_prob, 4),
            "raw_prob": round(state.raw_prob, 4),
            "is_inference": getattr(state, "_did_infer", False),
            "spot_price": getattr(state, "last_spot", None),
            "bid_up": round(book_up.best_bid, 4) if book_up else None,
            "ask_up": round(book_up.best_ask, 4) if book_up else None,
            "bid_dn": round(book_dn.best_bid, 4) if book_dn else None,
            "ask_dn": round(book_dn.best_ask, 4) if book_dn else None,
            "has_book": book_up is not None,
            "snap": state.dutch_engine.snapshot(),
            "pending_orders": len(state.dutch_sim.pending_orders),
        })


async def _divergence_tick(
    state: TFState, elapsed_pct: float, book_up, book_dn,
) -> None:
    """Run Divergence engine on_tick + simulator fills + live CLOB routing."""
    from qm.strategy.dutch.tick_processor import process_tick

    if not state.divergence_engine or not state.divergence_sim:
        return
    if state.last_model_time <= 0:
        return

    orders, fills = process_tick(
        elapsed_pct, state.cal_prob, book_up, book_dn,
        state.divergence_engine, state.divergence_sim,
    )

    # Live: route same orders to real CLOB (in addition to paper)
    if state.divergence_live_router and orders:
        import re as _re

        for order in orders:
            if order.action != "BUY":
                continue  # Only route buys to CLOB (sells handled by paper)
            allowed, reason = state.live_safety.can_trade(
                state.tf_label, order.dollars,
            )
            if not allowed:
                if state.live_trade_logger:
                    state.live_trade_logger.log_safety_event(
                        bar_id=state.current_bar_id,
                        event="blocked",
                        details=reason,
                    )
                continue

            t0 = time.perf_counter()
            order_id = await state.divergence_live_router.place(order)
            latency_ms = (time.perf_counter() - t0) * 1000

            if order_id and state.live_trade_logger:
                buy_book = book_up if order.side == "UP" else book_dn
                # Parse edge from reason string (e.g. "divergence_up_edge=0.150")
                edge_match = _re.search(r"edge=([\d.]+)", order.reason or "")
                edge_val = float(edge_match.group(1)) if edge_match else 0.0
                state.live_trade_logger.log_order_placed(
                    bar_id=state.current_bar_id,
                    clob_order_id=order_id,
                    side=order.side,
                    action=order.action,
                    limit_price=order.limit_price,
                    shares=order.shares,
                    dollars=order.dollars,
                    edge=edge_val,
                    cal_prob=state.cal_prob,
                    book_bid=getattr(buy_book, "best_bid", 0),
                    book_ask=getattr(buy_book, "best_ask", 0),
                    book_depth=sum(getattr(buy_book, "asks", {}).values()),
                    time_pct=elapsed_pct,
                    api_latency_ms=latency_ms,
                )
            if order_id:
                state.live_safety.record_fill(state.tf_label, order.dollars)

        # Check for CLOB fills
        live_fills = await state.divergence_live_router.check_fills()
        for fill in live_fills:
            if state.live_trade_logger:
                state.live_trade_logger.log_order_filled(
                    bar_id=state.current_bar_id,
                    clob_order_id="",  # tracked internally by router
                    fill_price=fill.fill_price,
                    filled_shares=fill.filled_shares,
                )


def _record_tick(
    tick_queue, state, book_up, book_dn, elapsed_pct: float,
    asset_label: str, bar_secs: float, ws_feed=None,
) -> None:
    """Record a tick to Parquet for backtest replay.

    IMPORTANT: book_up/book_dn must be the SAME objects passed to _dutch_tick,
    not re-read from ws_feed (race condition: WSS may update between calls).
    """
    rec_up = book_up
    rec_dn = book_dn
    if not (rec_up and rec_dn and rec_up.best_bid > 0 and rec_up.best_ask < 1):
        return
    from qm.data.connectors.tick_writer import TickSnapshot
    bar_id = state.current_bar_id
    rec_ws = datetime.fromtimestamp(bar_id, tz=UTC)
    rec_we = datetime.fromtimestamp(bar_id + int(bar_secs), tz=UTC)
    # Consume is_inference flag (only first tick after inference is marked)
    is_inf = getattr(state, "_did_infer", False)
    if is_inf:
        state._did_infer = False
    # On inference ticks: use elapsed_pct from inference time, not tick time
    if is_inf:
        inf_elapsed = getattr(state, "_last_inference_elapsed_pct", None)
        if inf_elapsed is not None:
            elapsed_pct = inf_elapsed
    # PartialBar + features snapshot on inference ticks (for backtest parity)
    pb = getattr(state, "_last_inference_partial", None) if is_inf else None
    btc_pb = getattr(state, "_last_inference_btc_partial", None) if is_inf else None
    feat_arr = getattr(state, "_last_inference_features", None) if is_inf else None
    feat_json = None
    if feat_arr is not None:
        import json as _json
        feat_json = _json.dumps([round(float(v), 8) for v in feat_arr])
    try:
        tick_queue.put_nowait(TickSnapshot(
            ts=datetime.now(UTC),
            asset=asset_label,
            timeframe=state.tf_label,
            condition_id=state.dutch_bar_condition_id,
            bid_up=rec_up.best_bid, ask_up=rec_up.best_ask,
            bid_dn=rec_dn.best_bid, ask_dn=rec_dn.best_ask,
            mid_up=rec_up.mid,
            spread_up=rec_up.spread, spread_dn=rec_dn.spread,
            depth_bid_up=rec_up.bids.get(rec_up.best_bid, 0.0),
            depth_ask_up=rec_up.asks.get(rec_up.best_ask, 0.0),
            depth_bid_dn=rec_dn.bids.get(rec_dn.best_bid, 0.0),
            depth_ask_dn=rec_dn.asks.get(rec_dn.best_ask, 0.0),
            is_heartbeat=False,
            is_stale=not ws_feed._connected.is_set() if ws_feed else False,
            spot_price=getattr(state, "last_spot", float("nan")),
            window_start=rec_ws, window_end=rec_we,
            elapsed_pct=elapsed_pct,
            cal_prob=state.cal_prob,
            is_inference=is_inf,
            pb_open=pb.open if pb else None,
            pb_high=pb.high_so_far if pb else None,
            pb_low=pb.low_so_far if pb else None,
            pb_close=pb.current_price if pb else None,
            pb_volume=pb.volume_so_far if pb else None,
            pb_trade_count=pb.trade_count if pb else None,
            pb_elapsed_s=pb.elapsed_seconds if pb else None,
            pb_remaining_s=pb.remaining_seconds if pb else None,
            btc_open=btc_pb.open if btc_pb else None,
            btc_high=btc_pb.high_so_far if btc_pb else None,
            btc_low=btc_pb.low_so_far if btc_pb else None,
            btc_close=btc_pb.current_price if btc_pb else None,
            btc_volume=btc_pb.volume_so_far if btc_pb else None,
            btc_trade_count=btc_pb.trade_count if btc_pb else None,
            btc_elapsed_s=btc_pb.elapsed_seconds if btc_pb else None,
            btc_remaining_s=btc_pb.remaining_seconds if btc_pb else None,
            raw_prob=state.raw_prob if is_inf else None,
            features_json=feat_json,
        ))
    except asyncio.QueueFull:
        pass  # Non-fatal: drop tick if queue full


async def _check_resolutions(
    state: TFState, asset_enum: Asset, scanner: MarketScanner,
) -> None:
    """Poll Gamma API for outcomes on pending bars."""
    if not state.dutch_pending_resolutions:
        return
    if time.time() - state.dutch_session.get("_last_resolution_check", 0) < 30.0:
        return
    state.dutch_session["_last_resolution_check"] = time.time()
    for item in state.dutch_pending_resolutions[:]:
        try:
            status = await scanner.get_market_status(
                item["condition_id"], asset=asset_enum,
            )
            if status and status.get("resolved", False):
                outcome_str = status.get("outcome", "")
                outcome = "UP" if outcome_str.lower() in ("up", "yes") else "DN"
                summary = item["summary"]
                summary.compute_pnl(outcome)
                if state.dutch_logger:
                    state.dutch_logger.log_bar(summary)
                profit = summary.pnl.get("profit", 0)
                pair_cost = summary.cost.get("avg_pair_cost", 1.0)
                state.dutch_session["total_pnl"] += profit
                state.dutch_session["bars"] += 1
                state.dutch_session["_sum_pair_cost"] = (
                    state.dutch_session.get("_sum_pair_cost", 0) + pair_cost
                )
                state.dutch_session["avg_pair_cost"] = (
                    state.dutch_session["_sum_pair_cost"] / state.dutch_session["bars"]
                )
                if profit >= 0:
                    state.dutch_session["wins"] += 1
                else:
                    state.dutch_session["losses"] += 1
                state.dutch_pending_resolutions.remove(item)
                logger.info(
                    "Dutch %s bar %d resolved %s: PnL=$%.2f (matched=%.1f, pair_cost=%.3f)",
                    state.tf_label, item["bar_id"], outcome, profit,
                    summary.inventory.get("matched", 0), pair_cost,
                )
                # Piggyback: resolve matching Divergence bar with same outcome
                for div_item in state.divergence_pending_resolutions[:]:
                    if div_item["bar_id"] == item["bar_id"]:
                        div_summary = div_item["summary"]
                        div_summary.compute_pnl(outcome)
                        if state.divergence_logger:
                            state.divergence_logger.log_bar(div_summary)
                        div_profit = div_summary.pnl.get("profit", 0)
                        state.divergence_session["total_pnl"] += div_profit
                        state.divergence_session["bars"] += 1
                        if div_profit >= 0:
                            state.divergence_session["wins"] += 1
                        else:
                            state.divergence_session["losses"] += 1
                        state.divergence_pending_resolutions.remove(div_item)
                        logger.info(
                            "Diverg %s bar %d resolved %s: PnL=$%.2f (cost=$%.2f)",
                            state.tf_label, item["bar_id"], outcome, div_profit,
                            div_summary.cost.get("total", 0),
                        )
                        break
                # Record outcome to resolution cache for backtest parity
                try:
                    res_dir = Path("data/raw/polymarket_ticks/resolutions")
                    res_dir.mkdir(parents=True, exist_ok=True)
                    date_str = datetime.fromtimestamp(
                        item["bar_id"], tz=UTC,
                    ).strftime("%Y-%m-%d")
                    res_file = res_dir / f"{state.tf_label}_{date_str}.jsonl"
                    with open(res_file, "a") as rf:
                        json.dump({
                            "bar_id": item["bar_id"],
                            "outcome": outcome,
                            "condition_id": item.get("condition_id", ""),
                        }, rf)
                        rf.write("\n")
                except Exception:
                    pass  # Non-fatal
        except Exception as e:
            logger.debug("Resolution check %s failed: %s", state.tf_label, e)
    # Cap pending list to prevent unbounded growth
    if len(state.dutch_pending_resolutions) > 20:
        dropped = len(state.dutch_pending_resolutions) - 20
        state.dutch_pending_resolutions[:] = state.dutch_pending_resolutions[-20:]
        logger.warning("Dropped %d stale pending resolutions (%s)", dropped, state.tf_label)


def _save_tf_state(state: TFState) -> None:
    """Persist session to JSON."""
    if state.dutch_state_file:
        _save_dutch_state(
            state.dutch_state_file, state.dutch_session,
            state.dutch_pending_resolutions,
        )


def _update_feature_cache(state: TFState, bar, pipeline: FeaturePipeline) -> None:
    """Update feature cache from completed bar."""
    state.recent_bars.append(bar)
    state.recent_bars[:] = state.recent_bars[-500:]

    if len(state.recent_bars) >= 20:
        bars_data = {
            "time": [b.timestamp for b in state.recent_bars],
            "open": [b.open for b in state.recent_bars],
            "high": [b.high for b in state.recent_bars],
            "low": [b.low for b in state.recent_bars],
            "close": [b.close for b in state.recent_bars],
            "volume": [b.volume for b in state.recent_bars],
            "trade_count": [b.trade_count for b in state.recent_bars],
            "vwap": [b.vwap for b in state.recent_bars],
        }
        try:
            bars_df = pl.DataFrame(bars_data)
            featured = pipeline.compute(bars_df)
            last_row = featured.row(-1, named=True)
            cache_dict = {
                name: float(val)
                for name in pipeline.feature_names
                if (val := last_row.get(name)) is not None
            }
            state.feat_cache.update_history(cache_dict)
            logger.debug("Updated feature cache %s (%d features)", state.tf_label, len(cache_dict))

            # Record cache snapshot for backtest parity
            try:
                bar_id = int(bar.timestamp.timestamp())
                snap_dir = state.dutch_logger._dir if state.dutch_logger else Path(f"data/dutch_paper/{state.tf_label}")
                snap_dir.mkdir(parents=True, exist_ok=True)
                snap_file = snap_dir / f"cache_snapshots_{datetime.now(UTC).strftime('%Y-%m-%d')}.jsonl"
                with open(snap_file, "a") as f:
                    json.dump({"bar_id": bar_id, "cache": cache_dict}, f)
                    f.write("\n")
                logger.info("Recorded cache snapshot for bar %d (%d features)", bar_id, len(cache_dict))
            except Exception as e2:
                logger.warning("Cache snapshot write failed: %s", e2)
        except Exception as e:
            logger.warning("Feature cache update failed (%s): %s", state.tf_label, e)

    # Record cache snapshot for backtest parity
    # When recent_bars < 20, cache hasn't changed from warm-up (same in BT and live).
    # When >= 20, cache_dict was just computed above — record it.
    # (This intentionally only records when cache is recomputed, which is the
    #  moment the backtest needs to match.)


# -- Main loop --------------------------------------------------------

async def main_loop(args: argparse.Namespace) -> None:
    model_dir = Path(args.model_dir)

    # -- Resolve timeframes ----------------------------------------
    if args.timeframe:
        timeframes = [TF_MAP[args.timeframe]]
    else:
        timeframes = [TF_MAP[t.strip()] for t in args.timeframes.split(",")]

    # -- Asset resolution -----------------------------------------
    asset_label = args.asset
    asset_enum = ASSET_MAP[asset_label]
    tv_symbol = TV_SYMBOLS[asset_label]

    dutch_mode = getattr(args, "dutch", False)

    tf_labels_str = ",".join(TF_LABELS[tf] for tf in timeframes)
    print("=" * 60)
    if dutch_mode:
        print(f"  {asset_label} Dutch Accumulation Paper Trader")
    else:
        print(f"  {asset_label} Dutch Scalping Alpha Monitor")
    print("=" * 60)
    print(f"  Asset:       {asset_label}")
    print(f"  Timeframes:  {tf_labels_str}")
    print(f"  Polymarket:  {'OFF' if args.no_polymarket else 'ON (WSS orderbook)'}")
    if dutch_mode:
        print(f"  Dutch:       ON (budget=${args.dutch_budget:.0f}, order=${args.dutch_order_size:.0f})")
    print(f"  Poll:        {POLL_INTERVAL*1000:.0f}ms")
    print(f"  Thresholds:  {[f'{t*100:.0f}%' for t in TIME_PCTS]}")
    print("=" * 60)

    # -- Per-TF initialization ------------------------------------
    tf_states: dict[Timeframe, TFState] = {}
    pipeline = FeaturePipeline()  # shared feature pipeline
    needs_btc_feed = False  # track if any TF needs cross-asset BTC

    for tf in timeframes:
        tf_label = TF_LABELS[tf]

        # Load model + calibrator
        model, calibrator = load_model(model_dir, asset_label, tf_label)

        # Feature cache
        cache_dir = model_dir / f"{asset_label}_{tf_label}"
        feat_cache = LiveFeatureCache.from_model_dir(
            cache_dir, asset=asset_enum, timeframe=tf,
        )
        warm_up_cache(feat_cache, asset_enum, tf)

        if isinstance(feat_cache, CrossAssetLiveFeatureCache):
            warm_up_btc(feat_cache, tf)
            needs_btc_feed = True

        state = TFState(
            tf=tf,
            tf_label=tf_label,
            model=model,
            calibrator=calibrator,
            feat_cache=feat_cache,
            mid_tracker=MidTracker(window_secs=MID_HISTORY_SECS),
        )

        # Dutch setup
        if dutch_mode:
            dutch_config, sim_kwargs = load_dutch_config(args, asset_label, tf_label, tf)
            state.dutch_engine = DutchAccumulationEngine(dutch_config)
            state.dutch_sim = LimitOrderSimulator(**sim_kwargs) if sim_kwargs else LimitOrderSimulator()
            logger.info(
                "Dutch %s config: budget=$%.0f, order=$%.0f, pair_cost<%.2f, "
                "conv_skip=%.2f, conv_size=%.2f, onesided_cap=$%.0f",
                tf_label,
                dutch_config.bar_budget, dutch_config.order_size,
                dutch_config.max_marginal_pair_cost,
                dutch_config.conviction_buy_skip,
                dutch_config.conviction_size_floor,
                dutch_config.max_onesided_cost,
            )
            state.dutch_logger = DutchSummaryLogger(
                base_dir=Path("data/dutch_paper"),
                asset=asset_label,
                timeframe=tf_label,
            )
            state.dutch_engine.set_event_callback(state.dutch_logger.log_event)
            state.dutch_state_file = Path(f"data/dutch_paper/state_{asset_label}_{tf_label}.json")

            # Divergence engine (alongside Dutch)
            if getattr(args, "divergence", False):
                from qm.strategy.engines.divergence import DivergenceConfig, DivergenceEngine

                div_config = DivergenceConfig(
                    bar_budget=args.dutch_budget,
                    bar_seconds=BAR_SECONDS[tf],
                    min_edge=getattr(args, "div_min_edge", 0.03),
                    kelly_fraction=getattr(args, "div_kelly", 0.25),
                    order_size=getattr(args, "div_order_size", 5.0),
                )
                state.divergence_engine = DivergenceEngine(div_config)
                state.divergence_sim = LimitOrderSimulator(**sim_kwargs) if sim_kwargs else LimitOrderSimulator()
                state.divergence_logger = DutchSummaryLogger(
                    base_dir=Path("data/divergence_paper"),
                    asset=asset_label,
                    timeframe=tf_label,
                )
                logger.info(
                    "Divergence %s enabled: min_edge=%.2f, kelly=%.2f, order=$%.0f",
                    tf_label, div_config.min_edge, div_config.kelly_fraction,
                    div_config.order_size,
                )

                # Live trading router (real CLOB orders)
                if getattr(args, "live", False):
                    from qm.execution.polymarket.client import PolymarketClient
                    from qm.execution.polymarket.divergence_router import DivergenceLiveRouter
                    from qm.execution.polymarket.safety import LiveSafetyConfig, LiveSafetyGuard
                    from qm.execution.polymarket.trade_logger import TradeLogger

                    if not hasattr(args, "_pm_client"):
                        args._pm_client = PolymarketClient()
                        logger.info("Polymarket CLOB client initialized (L2 auth)")

                    state.divergence_live_router = DivergenceLiveRouter(
                        args._pm_client,
                        dry_run=getattr(args, "dry_run", False),
                    )
                    state.live_safety = LiveSafetyGuard(LiveSafetyConfig(
                        max_order_usd=getattr(args, "live_order_size", 2.0),
                        max_daily_loss_usd=getattr(args, "live_max_daily_loss", 50.0),
                        max_concurrent_orders=5,      # max 5 resting orders per asset
                        max_position_per_pair=10.0,    # max $10 exposure per asset per bar
                    ))
                    state.live_trade_logger = TradeLogger(
                        base_dir=Path("data/divergence_live"),
                        asset=asset_label,
                        timeframe=tf_label,
                    )
                    # Load persisted safety state
                    safety_path = Path(f"data/divergence_live/safety_{asset_label}_{tf_label}.json")
                    state.live_safety.load_state(safety_path)

                    mode = "DRY-RUN" if getattr(args, "dry_run", False) else "LIVE"
                    logger.info(
                        "%s %s: order=$%.0f, daily_loss_cap=$%.0f",
                        mode, tf_label,
                        getattr(args, "live_order_size", 2.0),
                        getattr(args, "live_max_daily_loss", 50.0),
                    )

            if state.dutch_state_file.exists():
                try:
                    with open(state.dutch_state_file) as f:
                        saved = json.load(f)
                    if "session" in saved:
                        state.dutch_session.update(saved["session"])
                        logger.info("Restored dutch %s session: %dW %dL PnL=$%.2f",
                                    tf_label, state.dutch_session["wins"],
                                    state.dutch_session["losses"],
                                    state.dutch_session["total_pnl"])
                except Exception as e:
                    logger.warning("Failed to load dutch state %s: %s", tf_label, e)
            logger.info("Dutch %s enabled: budget=$%.0f, order=$%.0f, edge>%.2f",
                        tf_label, args.dutch_budget, args.dutch_order_size,
                        dutch_config.cheap_threshold)

        # Polymarket scanner per TF
        if not args.no_polymarket:
            state.scanner = MarketScanner(
                assets={asset_enum}, timeframe=tf,
                connector_factory=create_connector,
                min_time_remaining_sec=5.0,
            )
            state.scanner._cache_ttl = 2.0

        tf_states[tf] = state

    # -- Shared BarBuilder (all TFs, one price feed) ---------------
    bar_builder = BarBuilder(assets=[asset_enum], timeframes=timeframes)
    completed_bars: asyncio.Queue = asyncio.Queue()

    # -- BTC cross-asset feed (shared across TFs) ------------------
    btc_bar_builder: BarBuilder | None = None
    btc_completed_bars: asyncio.Queue | None = None
    if needs_btc_feed:
        btc_bar_builder = BarBuilder(assets=[Asset.BTC], timeframes=timeframes)
        btc_completed_bars = asyncio.Queue()

    # -- Start background tasks -----------------------------------
    running_flag = [True]

    # Single shared price feed
    asyncio.create_task(price_feed(asset_enum, tv_symbol, bar_builder, completed_bars, running_flag))

    if btc_bar_builder is not None and btc_completed_bars is not None:
        asyncio.create_task(price_feed(
            Asset.BTC, "BINANCE:BTCUSDT", btc_bar_builder,
            btc_completed_bars, running_flag,
        ))
        logger.info("BTC cross-asset price feed started")

    # Per-TF Polymarket feeds
    if not args.no_polymarket:
        for tf, state in tf_states.items():
            if state.scanner:
                asyncio.create_task(
                    polymarket_feed(
                        asset_enum, tf, state.scanner,
                        state.ws_feeds, state.pm_markets, running_flag,
                    ),
                )

    # -- Shared state ---------------------------------------------
    last_price: float = 0.0

    def handle_shutdown(sig_num, frame):
        logger.info("Shutdown signal received")
        running_flag[0] = False

    signal.signal(signal.SIGINT, handle_shutdown)
    signal.signal(signal.SIGTERM, handle_shutdown)

    # -- Tick Parquet writer (records what live sees for backtest replay) --
    tick_queue: asyncio.Queue | None = None
    tick_writer_task = None
    if dutch_mode:
        from qm.data.connectors.tick_writer import TickWriter, TickSnapshot
        tick_queue = asyncio.Queue()
        _tw = TickWriter(
            base_dir=Path("data/raw/polymarket_ticks"),
            flush_interval=60.0,
            flush_size=500,
        )
        tick_writer_task = asyncio.create_task(_tw.run(tick_queue, running_flag))

    # -- Timing cadences ------------------------------------------
    last_display_time = 0.0
    last_state_save = time.time()
    MODEL_INTERVAL = 1.0
    display_tf_idx = 0  # cycle through TFs for display

    # -- Live trading startup: cancel stale orders + signal handler --
    if getattr(args, "live", False):
        for tf, state in tf_states.items():
            if state.divergence_live_router:
                cancelled = await state.divergence_live_router.cancel_all_open_orders()
                if cancelled:
                    logger.info("Startup: cancelled %d stale CLOB orders (%s)", cancelled, state.tf_label)

        # Graceful shutdown: cancel all CLOB orders on SIGTERM/SIGINT

        async def _live_shutdown(sig_name: str) -> None:
            logger.info("Received %s — cancelling all live CLOB orders...", sig_name)
            for _tf, _st in tf_states.items():
                if _st.divergence_live_router:
                    _cancelled = await _st.divergence_live_router.cancel_all()
                    logger.info("Cancelled %d live orders on %s", len(_cancelled), _st.tf_label)
                if _st.live_safety:
                    _safety_path = Path(f"data/divergence_live/safety_{_st.tf_label}.json")
                    _st.live_safety.save_state(_safety_path)
                if _st.live_trade_logger:
                    _st.live_trade_logger.close()
            running_flag[0] = False

        loop = asyncio.get_event_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            try:
                loop.add_signal_handler(
                    sig,
                    lambda s=sig: asyncio.ensure_future(_live_shutdown(s.name)),
                )
            except NotImplementedError:
                pass  # Windows doesn't support add_signal_handler

    logger.info("Starting main loop (%s, %d TFs)... waiting for ticks",
                "event-driven" if dutch_mode else f"{POLL_INTERVAL*1000:.0f}ms polling",
                len(timeframes))

    while running_flag[0]:
        # ============================================================
        # SLOW PATH: bar management, inference, display (~20 Hz)
        # Must run FIRST so current_bar_id and cal_prob are fresh
        # ============================================================

        # -- Process completed bars (route to correct TFState) ----
        if not completed_bars.empty():
            logger.info("Draining completed_bars queue (size=%d)", completed_bars.qsize())
        while not completed_bars.empty():
            bar = completed_bars.get_nowait()
            logger.info("Processing completed bar: %s %s", bar.timeframe.value, bar.timestamp)
            state = tf_states.get(bar.timeframe)
            if state is None:
                logger.warning("No TFState for %s, skipping", bar.timeframe)
                continue
            print_bar_complete(bar)
            _update_feature_cache(state, bar, pipeline)

        # -- Process BTC completed bars (cross-asset, all TFs) ----
        if btc_completed_bars is not None:
            while not btc_completed_bars.empty():
                btc_completed_bars.get_nowait()
                # BTC bars consumed to keep queue clear; cache updated via partial

        # -- Per-TF processing: bar detection + inference -----------
        now = time.time()
        for tf, state in tf_states.items():
            bar_secs = BAR_SECONDS[tf]

            # -- Get partial bar ----------------------------------
            partial = bar_builder.get_partial_bar(asset_enum, tf)

            if partial is None:
                # V7.5: early-bar Dutch processing from Polymarket market timing
                # Bar boundary detection + setup only (tick processing in fast path)
                if dutch_mode and state.dutch_engine:
                    pm_mkt = state.pm_markets.get(tf)
                    if pm_mkt and pm_mkt.window_end:
                        bar_id_from_market = int(pm_mkt.window_end.timestamp()) - int(bar_secs)
                        now_ts = time.time()
                        if now_ts < bar_id_from_market or now_ts >= bar_id_from_market + bar_secs + 5:
                            continue
                        # Handle bar boundary (new bar detected)
                        if bar_id_from_market != state.current_bar_id and state.current_bar_id != 0:
                            state.last_model_time = 0.0  # require fresh prediction
                            await _finalize_dutch_bar(state)
                            _setup_new_bar(state, bar_id_from_market, pm_mkt)
                            state.current_bar_id = bar_id_from_market
                        elif state.current_bar_id == 0:
                            state.current_bar_id = bar_id_from_market
                            _setup_new_bar(state, bar_id_from_market, pm_mkt)
                continue  # no partial bar yet for this TF

            last_price = state.last_spot = partial.current_price
            bar_id = int(partial.window_start.timestamp())
            elapsed_pct = partial.elapsed_seconds / (partial.remaining_seconds + partial.elapsed_seconds + 1e-10)

            # Reset on new bar
            if bar_id != state.current_bar_id:
                state.last_model_time = 0.0  # require fresh prediction
                # Dutch: finalize previous bar
                if dutch_mode and state.dutch_engine and state.current_bar_id != 0:
                    await _finalize_dutch_bar(state)

                # Set up new bar
                if dutch_mode and state.dutch_engine:
                    pm_market = state.pm_markets.get(tf)
                    w_s = partial.window_start.astimezone(DISPLAY_TZ).strftime("%H:%M")
                    w_e = partial.window_end.astimezone(DISPLAY_TZ).strftime("%H:%M")
                    _setup_new_bar(state, bar_id, pm_market, window_start_str=w_s, window_end_str=w_e)

                state.current_bar_id = bar_id
                state.last_triggered = set()

            # -- Model inference at 1Hz ----------------------------
            state._did_infer = False
            if now - state.last_model_time >= MODEL_INTERVAL:
                _run_inference(state, partial, elapsed_pct, btc_bar_builder)
                state._did_infer = True

            # -- Check market data (cache for fast path) -----------
            pm_market = state.pm_markets.get(tf)
            ws_feed = state.ws_feeds.get(tf)

            market_matches = True
            if pm_market and pm_market.window_end:
                bar_secs_int = int(bar_secs)
                market_bar_start = int(pm_market.window_end.timestamp()) - bar_secs_int
                if market_bar_start != bar_id:
                    market_matches = False
            state._market_matches = market_matches

            has_book = (
                market_matches
                and ws_feed is not None
                and ws_feed._connected.is_set()
                and ws_feed.best_bid_up > 0
                and ws_feed.best_ask_up < 1
            )

            if has_book and ws_feed:
                state.mid_tracker.update(ws_feed.mid_up)

            mid_vel = state.mid_tracker.velocity()

            # -- Threshold crossings ------------------------------
            for threshold in TIME_PCTS:
                if threshold in state.last_triggered:
                    continue
                if elapsed_pct >= threshold:
                    state.last_triggered.add(threshold)
                    if has_book and ws_feed:
                        print_threshold(
                            state.tf_label, threshold, state.raw_prob, state.cal_prob,
                            ws_feed.best_ask_up, ws_feed.best_ask_down,
                            state.cal_prob - ws_feed.best_ask_up,
                            (1 - state.cal_prob) - ws_feed.best_ask_down,
                        )
                    else:
                        print_threshold(
                            state.tf_label, threshold, state.raw_prob, state.cal_prob,
                            None, None, None, None,
                        )

            # -- Resolution polling (every 30s) -------------------
            if dutch_mode and not args.no_polymarket and state.scanner:
                await _check_resolutions(state, asset_enum, state.scanner)

        # ============================================================
        # FAST PATH: process ALL pending book updates for dutch engine
        # Runs AFTER slow path so current_bar_id and cal_prob are fresh
        # ============================================================
        if dutch_mode:
            for tf, state in tf_states.items():
                ws_feed = state.ws_feeds.get(tf)
                if not ws_feed or not ws_feed._connected.is_set():
                    continue
                if not ws_feed.book_updated.is_set():
                    continue
                ws_feed.book_updated.clear()

                # Skip if no bar set up yet or market doesn't match
                if state.current_bar_id == 0:
                    continue
                if not state._market_matches:
                    continue

                # Compute elapsed_pct from wall clock
                bar_secs = BAR_SECONDS[tf]
                elapsed_pct = max(0.0, min(1.0,
                    (time.time() - state.current_bar_id) / bar_secs))

                # Dutch tick processing
                if state.dutch_engine and state.dutch_sim:
                    book_up = ws_feed.get_book("up") if ws_feed.best_bid_up > 0 and ws_feed.best_ask_up < 1 else None
                    book_dn = ws_feed.get_book("down") if book_up else None
                    if book_up and book_dn:
                        _dutch_tick(state, elapsed_pct, book_up, book_dn, args,
                                    state.current_bar_id)
                        await _divergence_tick(state, elapsed_pct, book_up, book_dn)

                        # Record tick to Parquet (same book objects engine saw)
                        if tick_queue is not None:
                            _record_tick(tick_queue, state, book_up, book_dn,
                                         elapsed_pct, asset_label, bar_secs,
                                         ws_feed=ws_feed)

        # -- Display at cadence (cycle through TFs) ----------------
        now_disp = time.time()
        if now_disp - last_display_time >= DISPLAY_INTERVAL:
            last_display_time = now_disp
            # Pick TF to display (cycle through)
            tf_list = list(tf_states.keys())
            if tf_list:
                display_tf = tf_list[display_tf_idx % len(tf_list)]
                display_state = tf_states[display_tf]
                display_partial = bar_builder.get_partial_bar(asset_enum, display_tf)

                if display_partial is not None:
                    ws_feed = display_state.ws_feeds.get(display_tf)
                    pm_market = display_state.pm_markets.get(display_tf)
                    market_matches = True
                    if pm_market and pm_market.window_end:
                        bar_secs_int = int(BAR_SECONDS[display_tf])
                        market_bar_start = int(pm_market.window_end.timestamp()) - bar_secs_int
                        if market_bar_start != int(display_partial.window_start.timestamp()):
                            market_matches = False
                    has_book = (
                        market_matches
                        and ws_feed is not None
                        and ws_feed._connected.is_set()
                        and ws_feed.best_bid_up > 0
                        and ws_feed.best_ask_up < 1
                    )
                    mid_vel = display_state.mid_tracker.velocity()
                    model_ready = display_state.last_model_time > 0

                    if dutch_mode and display_state.dutch_engine:
                        print_dutch_panel(
                            asset_label=asset_label,
                            price=last_price,
                            partial=display_partial,
                            tf_label=f"{display_state.tf_label} [{display_tf_idx % len(tf_list) + 1}/{len(tf_list)}]",
                            cal_prob=display_state.cal_prob,
                            ws_feed=ws_feed,
                            has_book=has_book,
                            mid_vel=mid_vel,
                            pred_us=display_state.pred_us,
                            engine_snap=display_state.dutch_engine.snapshot(),
                            sim_stats=display_state.dutch_sim.stats if display_state.dutch_sim else None,
                            session_stats=display_state.dutch_session,
                            model_ready=model_ready,
                        )
                    else:
                        print_alpha_panel(
                            asset_label=asset_label,
                            price=last_price,
                            partial=display_partial,
                            tf_label=f"{display_state.tf_label} [{display_tf_idx % len(tf_list) + 1}/{len(tf_list)}]",
                            raw_prob=display_state.raw_prob,
                            cal_prob=display_state.cal_prob,
                            ws_feed=ws_feed,
                            has_book=has_book,
                            mid_vel=mid_vel,
                            pred_us=display_state.pred_us,
                            model_ready=model_ready,
                        )
                # Cycle to next TF every display interval
                display_tf_idx += 1

        # -- State persistence (every 5 min, all TFs) -------------
        if dutch_mode and now_disp - last_state_save >= STATE_SAVE_INTERVAL:
            last_state_save = now_disp
            for state in tf_states.values():
                _save_tf_state(state)

            # Daily safety reset at midnight UTC
            from datetime import UTC, datetime
            now_utc = datetime.now(UTC)
            for state in tf_states.values():
                if state.live_safety and now_utc.hour == 0 and now_utc.minute < 6:
                    if not getattr(state, "_daily_reset_done", False):
                        state.live_safety.reset_daily()
                        state._daily_reset_done = True
                elif hasattr(state, "_daily_reset_done"):
                    state._daily_reset_done = False

        # -- Yield to WSS tasks -----------------------------------
        # Dutch: 50ms sleep — WSS runs during this, sets book_updated.
        # Non-dutch: 1s poll (no fast path needed, display-only mode).
        await asyncio.sleep(0.05 if dutch_mode else POLL_INTERVAL)

    # -- Shutdown -------------------------------------------------
    logger.info("Shutting down...")
    for state in tf_states.values():
        if dutch_mode:
            _save_tf_state(state)
        if state.dutch_logger:
            state.dutch_logger.close()
        for feed in state.ws_feeds.values():
            feed.stop()
    # Wait for TickWriter to flush remaining ticks
    if tick_writer_task:
        try:
            await asyncio.wait_for(tick_writer_task, timeout=5.0)
        except (asyncio.TimeoutError, asyncio.CancelledError):
            pass
    logger.info("Monitor stopped.")


def main() -> None:
    args = parse_args()
    asyncio.run(main_loop(args))


if __name__ == "__main__":
    main()
