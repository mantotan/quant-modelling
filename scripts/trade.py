#!/usr/bin/env python
"""Unified trading script: paper, dry-run, and live modes.

Single entry point for all trading modes. Same Rust hot path for all:
  tick → Rust FeatureCalculator → LightGBM → calibrate → signal → execute

Modes:
  paper:   PaperExecutor (instant sim fill, no network)
  dry-run: Full CLOB flow, Rust signing, but orders NOT submitted
  live:    Full CLOB flow, real orders on Polymarket

Usage:
    uv run scripts/trade.py --mode paper --asset BTC --bankroll 5000
    uv run scripts/trade.py --mode dry-run --asset BTC --bankroll 500
    uv run scripts/trade.py --mode live --asset BTC --bankroll 500 --max-bet 25
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import signal
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import aiohttp
import lightgbm as lgb
import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from qm.core.types import Asset, Outcome, PolymarketMarket, Timeframe
from qm.data.connectors.polymarket_ws import PolymarketWSFeed
from qm.data.ingestion.bar_builder import BarBuilder
from qm.data.storage.parquet import ParquetStore
from qm.execution.audit import AuditWriter
from qm.execution.loop import TradingLoop
from qm.execution.paper.engine import PaperExecutor
from qm.execution.paper.trade_logger import PaperTradeLogger
from qm.model.calibration.calibrator import TimeAwareCalibrator
from qm.strategy.bar_accumulator import BarEdgeAccumulator
from qm.execution.polymarket.market_scanner import MarketScanner
from qm.features.live_cache import RUST_AVAILABLE, LiveFeatureCache
from qm.features.pipeline import FeaturePipeline
from qm.model.calibration.calibrator import IsotonicCalibrator
from qm.model.signals import SignalGenerator
from qm.risk.bankroll import Bankroll
from qm.risk.circuit_breaker import CircuitBreaker
from qm.risk.manager import RiskManager
from qm.strategy.filter import TradeFilter
from qm.strategy.portfolio import Portfolio
from qm.strategy.sizing.kelly import KellySizer

# TradingView websocket for real-time tick data
TV_WSS_URL = "wss://data.tradingview.com/socket.io/websocket"
_TV_SYMBOLS: dict[str, str] = {
    "BTC": "BINANCE:BTCUSDT", "ETH": "BINANCE:ETHUSDT",
    "SOL": "BINANCE:SOLUSDT", "XRP": "BINANCE:XRPUSDT",
}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("trade")

# Time thresholds for Pulse predictions — must match training config
_KNOBS_PATH = Path("autoresearch/best_knobs.json")
if _KNOBS_PATH.exists():
    with open(_KNOBS_PATH) as _f:
        TIME_PCTS = json.loads(_f.read()).get("time_pcts", [0.80])
else:
    TIME_PCTS = [0.80]

# State file for crash recovery
STATE_FILE = Path("data/trade_state.json")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="QM Trading System")
    p.add_argument(
        "--mode", required=True, choices=["paper", "dry-run", "live"],
        help="Trading mode",
    )
    p.add_argument("--asset", default="BTC", choices=["BTC", "ETH", "SOL", "XRP"])
    p.add_argument("--timeframe", default="5m", choices=["5m", "15m", "1h"])
    p.add_argument("--bankroll", type=float, default=5000.0)
    p.add_argument("--max-bet", type=float, default=25.0)
    p.add_argument("--min-edge", type=float, default=0.01)
    p.add_argument(
        "--model-dir", default="data/models/pulse_v2",
        help="Model directory",
    )
    return p.parse_args()


def load_model(model_dir: Path, asset: str, tf: str):
    """Load trained LightGBM model + calibrator."""
    model_path = model_dir / f"{asset}_{tf}" / "model.lgb"
    cal_path = model_dir / f"{asset}_{tf}" / "calibrator.pkl"

    if not model_path.exists():
        logger.error("No model at %s", model_path)
        sys.exit(1)

    model = lgb.Booster(model_file=str(model_path))
    logger.info("Loaded model: %s", model_path)

    calibrator = None
    if cal_path.exists():
        calibrator = TimeAwareCalibrator()
        calibrator.load(cal_path)  # handles both legacy and new formats
        logger.info("Loaded calibrator: %s", cal_path)
    else:
        logger.warning("No calibrator found, using uncalibrated probs")

    return model, calibrator


def warm_up(
    asset: Asset,
    tf: Timeframe,
    live_cache: LiveFeatureCache,
    bar_builder: BarBuilder,
) -> None:
    """Load historical bars and populate the feature cache.

    Ensures the first prediction uses real feature values (rsi_14, etc.)
    instead of defaults. Also primes the BarBuilder with the last bar.
    """
    store = ParquetStore(base_dir=Path("data/raw/ohlcv"))
    bars_df = store.read_bars(asset, tf)
    if bars_df.is_empty():
        logger.warning("No OHLCV data for warm-up — using defaults")
        return

    # Compute features on last 500 bars
    pipeline = FeaturePipeline()
    n = min(500, len(bars_df))
    recent = bars_df.tail(n)
    featured = pipeline.compute(recent)

    # Extract the last bar's features into the cache
    last_row = featured.row(-1, named=True)
    cache_dict = {}
    for name in pipeline.feature_names:
        val = last_row.get(name)
        if val is not None:
            cache_dict[name] = float(val)

    live_cache.update_history(cache_dict)

    logger.info(
        "Warm-up: cached %d features from %d bars for %s",
        len(cache_dict), n, asset.value,
    )


def create_executor(mode: str):
    """Create the appropriate executor for the trading mode."""
    if mode == "paper":
        return PaperExecutor()

    # dry-run and live use the real CLOB integration
    from qm.execution.polymarket.client import PolymarketClient
    from qm.execution.polymarket.live_executor import LiveExecutor
    from qm.execution.polymarket.order_manager import OrderManager

    try:
        client = PolymarketClient()
        order_mgr = OrderManager(client)
        submit = mode == "live"  # dry-run: submit=False
        executor = LiveExecutor(client, order_mgr, submit=submit)
        logger.info(
            "Created %s executor (submit=%s)",
            mode, submit,
        )
        return executor
    except Exception as e:
        logger.warning(
            "Failed to create %s executor: %s. Falling back to paper.",
            mode, e,
        )
        return PaperExecutor()


async def resolution_monitor(
    portfolio: Portfolio,
    trading_loop: TradingLoop,
    scanner: MarketScanner,
    running_flag: list[bool],
    trade_logger: PaperTradeLogger | None = None,
) -> None:
    """Poll Gamma API for market resolutions every 30s.

    Uses MarketScanner.get_market_status() to check actual outcomes,
    NOT random resolution. This ensures paper PnL reflects real
    market outcomes.
    """
    while running_flag[0]:
        await asyncio.sleep(30.0)
        positions = portfolio.get_open_positions()
        if not positions:
            continue

        for pos in positions:
            age = (datetime.now(UTC) - pos.entry_time).total_seconds()
            if age < 300:  # wait at least 5 min before checking
                continue

            # Poll Gamma API for actual resolution
            market_info = await scanner.get_market_status(
                pos.condition_id,
                asset=pos.asset,
                entry_time=pos.entry_time,
            )
            if market_info is None:
                if age > 600:  # > 10 min, warn
                    logger.warning(
                        "Position %s age %.0fs, no resolution yet",
                        pos.condition_id[:12], age,
                    )
                continue

            if not market_info.get("resolved", False):
                continue

            # Determine actual outcome from Gamma API
            outcome_str = market_info.get("outcome", "")
            outcome = (
                Outcome.UP
                if outcome_str.lower() in ("up", "yes")
                else Outcome.DOWN
            )

            pnl = await trading_loop.on_market_resolution(
                pos.condition_id, outcome,
            )
            won = pnl > 0
            logger.info(
                "Resolved %s %s: %s → PnL $%.2f",
                pos.asset.value, pos.side.value,
                "WIN" if won else "LOSS", pnl,
            )

            if trade_logger:
                trade_logger.log_resolution(
                    condition_id=pos.condition_id,
                    outcome=outcome.value,
                    pnl=float(pnl),
                    was_correct=won,
                )


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
    asset: Asset,
    bar_builder: BarBuilder,
    running_flag: list[bool],
) -> None:
    """Stream real-time ticks from TradingView websocket into BarBuilder.

    Subscribes to BINANCE:{ASSET}USDT via TradingView's public quote feed.
    Sub-second tick data with volume — much better than REST polling.
    Auto-reconnects on disconnect.
    """
    import random
    import string

    tv_symbol = _TV_SYMBOLS.get(asset.value, f"BINANCE:{asset.value}USDT")
    logger.info("Price feed starting: %s via TradingView WSS", tv_symbol)

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
                        bar_builder.on_trade(
                            asset, float(lp), float(vol) * 0.0001, now,
                        )
                        tick_count += 1
                        if tick_count == 1:
                            logger.info(
                                "First tick: %s $%.2f", asset.value, lp,
                            )

                await ws.close()
        except Exception:
            logger.warning("Price feed disconnected, reconnecting in 5s...")
            await asyncio.sleep(5.0)


def save_state(portfolio: Portfolio, stats: dict) -> None:
    """Save portfolio state for crash recovery."""
    state = {
        "bankroll": portfolio.bankroll.to_dict(),
        "n_positions": len(portfolio.get_open_positions()),
        "stats": stats,
        "saved_at": datetime.now(UTC).isoformat(),
    }
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


async def main_loop(args: argparse.Namespace) -> None:
    asset_map = {
        "BTC": Asset.BTC, "ETH": Asset.ETH,
        "SOL": Asset.SOL, "XRP": Asset.XRP,
    }
    tf_map = {"5m": Timeframe.M5, "15m": Timeframe.M15, "1h": Timeframe.H1}
    asset = asset_map[args.asset]
    tf = tf_map[args.timeframe]

    logger.info("=" * 60)
    logger.info("QM Trading System")
    logger.info("=" * 60)
    logger.info("  Mode:     %s", args.mode)
    logger.info("  Asset:    %s", args.asset)
    logger.info("  Bankroll: $%.2f", args.bankroll)
    logger.info("  Max bet:  $%.2f", args.max_bet)
    logger.info("  Rust:     %s", "YES" if RUST_AVAILABLE else "NO (Python fallback)")
    logger.info("=" * 60)

    # ── Load model ──────────────────────────────────────────────
    model_dir = Path(args.model_dir)
    model, calibrator = load_model(model_dir, args.asset, args.timeframe)

    # ── Feature calculator (Rust or Python, reordered to model) ─
    model_subdir = model_dir / f"{args.asset}_{args.timeframe}"
    live_cache = LiveFeatureCache.from_model_dir(
        model_dir=model_subdir, asset=asset, timeframe=tf,
    )
    logger.info(
        "Feature cache: %s (%d model features)",
        "Rust" if RUST_AVAILABLE else "Python", live_cache.n_features,
    )

    # ── Build BarBuilder for tick aggregation ───────────────────
    bar_builder = BarBuilder(assets=[asset], timeframes=[tf])

    # ── Warm-up: populate feature cache ─────────────────────────
    warm_up(asset, tf, live_cache, bar_builder)

    # ── Instantiate trading components ──────────────────────────
    bankroll = Bankroll(initial=args.bankroll)
    portfolio = Portfolio(bankroll=bankroll)
    circuit_breaker = CircuitBreaker()
    risk_manager = RiskManager(
        bankroll=bankroll, circuit_breaker=circuit_breaker,
    )
    sizer = KellySizer(
        fraction=0.25, max_bet_pct=0.05,
        max_bet_usd=args.max_bet, min_bet_usd=1.0,
    )
    signal_gen = SignalGenerator(min_edge=args.min_edge)
    trade_filter = TradeFilter(
        risk_manager=risk_manager,
        min_edge=args.min_edge,
        min_time_remaining_sec=60.0,
        min_liquidity_usd=0.0,  # No liquidity filter for paper trading
    )
    executor = create_executor(args.mode)
    audit = AuditWriter()
    trade_logger = PaperTradeLogger(
        base_dir=Path("data/paper_trades"),
        asset=args.asset,
        timeframe=args.timeframe,
    )

    # Load trading strategy from knobs (default: first_confident)
    _knobs = json.loads(_KNOBS_PATH.read_text()) if _KNOBS_PATH.exists() else {}
    trading_cfg = _knobs.get("trading", {})
    accumulator = BarEdgeAccumulator(
        strategy=trading_cfg.get("strategy", "first_confident"),
        confidence_threshold=trading_cfg.get("confidence_threshold", 0.05),
    )
    logger.info("Trading strategy: %s (threshold=%.2f)",
                accumulator.strategy, accumulator.confidence_threshold)

    trading_loop = TradingLoop(
        signal_generator=signal_gen,
        calibrator=calibrator,
        risk_manager=risk_manager,
        trade_filter=trade_filter,
        sizer=sizer,
        portfolio=portfolio,
        executor=executor,
        audit=audit,
    )

    # ── Stats tracking ──────────────────────────────────────────
    stats = {
        "trades": 0, "signals": 0, "predictions": 0,
        "wins": 0, "losses": 0, "total_pnl": 0.0,
        "start_time": datetime.now(UTC).isoformat(),
    }

    # ── Market scanner (cached, 10s TTL) ────────────────────────
    scanner = MarketScanner(assets={asset}, timeframe=tf)

    # ── Polymarket WS orderbook feed ──────────────────────────
    ws_feed = PolymarketWSFeed()
    ws_feed_task: asyncio.Task | None = None
    ws_subscribed_market: str = ""  # condition_id of currently subscribed market

    # ── Start background tasks ─────────────────────────────────
    running_flag = [True]  # mutable list so coroutines can check
    asyncio.create_task(
        price_feed(asset, bar_builder, running_flag),
    )
    asyncio.create_task(
        resolution_monitor(
            portfolio, trading_loop, scanner, running_flag, trade_logger,
        ),
    )

    # ── Main polling loop ───────────────────────────────────────
    last_triggered: dict[Asset, set[float]] = {}
    current_bar_id: dict[Asset, int] = {}
    last_dashboard = time.time()
    bar_seconds = {"5m": 300.0, "15m": 900.0, "1h": 3600.0}[args.timeframe]

    logger.info("Starting main loop (1s polling)...")
    logger.info("Waiting for Polymarket market discovery...")

    def handle_shutdown(sig_num, frame):
        nonlocal running_flag
        logger.info("Shutdown signal received")
        running_flag[0] = False

    signal.signal(signal.SIGINT, handle_shutdown)
    signal.signal(signal.SIGTERM, handle_shutdown)

    while running_flag[0]:
        await asyncio.sleep(1.0)

        # Get partial bar snapshot
        partial = bar_builder.get_partial_bar(asset, tf)

        if partial is None:
            # No bar data yet — ticks come from CcxtWebsocketConnector
            continue

        bar_id = int(partial.window_start.timestamp())
        if bar_id != current_bar_id.get(asset):
            # Bar changed — execute any deferred trade from previous bar
            old_bar_id = current_bar_id.get(asset)
            if old_bar_id is not None:
                deferred = accumulator.on_bar_end(old_bar_id)
                if deferred:
                    market = await scanner.get_active_market(asset)
                    if market and ws_feed.mid_up > 0:
                        market = PolymarketMarket(
                            condition_id=market.condition_id,
                            token_id_up=market.token_id_up,
                            token_id_down=market.token_id_down,
                            asset=market.asset,
                            market_type=market.market_type,
                            window_start=market.window_start,
                            window_end=market.window_end,
                            mid_up=ws_feed.mid_up,
                            spread=ws_feed.spread,
                            volume=market.volume,
                        )
                        fill = await trading_loop.on_partial_bar(
                            partial, market, deferred.model_prob,
                        )
                        if fill and fill.status == "filled":
                            stats["trades"] += 1
                            logger.info(
                                "TRADE (deferred): %s %s $%.2f @ %.4f (edge=%.3f)",
                                asset.value, deferred.side,
                                fill.size_usd, fill.price, deferred.edge,
                            )
                accumulator.cleanup_old_bars(bar_id)
            current_bar_id[asset] = bar_id
            last_triggered[asset] = set()

        elapsed_pct = partial.elapsed_seconds / (bar_seconds + 1e-10)

        # Check time_pct thresholds
        for threshold in TIME_PCTS:
            if threshold in last_triggered.get(asset, set()):
                continue
            if elapsed_pct < threshold:
                continue

            last_triggered.setdefault(asset, set()).add(threshold)

            # Discover active market (cached, 10s TTL)
            market = await scanner.get_active_market(asset)
            if market is None:
                logger.debug("No active market for %s", asset.value)
                continue

            # Start/update WS orderbook feed for this market
            if market.condition_id != ws_subscribed_market:
                if ws_feed_task is not None:
                    ws_feed.stop()
                    ws_feed_task.cancel()
                ws_feed = PolymarketWSFeed()
                ws_feed_task = asyncio.create_task(
                    ws_feed.connect_and_run(
                        market.token_id_up, market.token_id_down, running_flag,
                    ),
                )
                ws_subscribed_market = market.condition_id
                logger.info(
                    "WS feed subscribed: %s (up=%s...)",
                    market.condition_id[:16], market.token_id_up[:16],
                )
                await asyncio.sleep(1.0)  # Wait for initial book snapshot

            # Override market odds with live WS data
            if ws_feed.mid_up > 0:
                market = PolymarketMarket(
                    condition_id=market.condition_id,
                    token_id_up=market.token_id_up,
                    token_id_down=market.token_id_down,
                    asset=market.asset,
                    market_type=market.market_type,
                    window_start=market.window_start,
                    window_end=market.window_end,
                    mid_up=ws_feed.mid_up,
                    spread=ws_feed.spread,
                    volume=market.volume,
                )

            # Compute features (reordered to model's expected order)
            t0 = time.perf_counter_ns()
            features = live_cache.get_features(partial)

            # Model prediction
            prob_up = model.predict(features.reshape(1, -1))[0]
            if calibrator and hasattr(calibrator, "transform"):
                prob_up = calibrator.transform(
                    np.array([prob_up]),
                    np.array([elapsed_pct]),
                )[0]

            elapsed_us = (time.perf_counter_ns() - t0) / 1000
            stats["predictions"] += 1

            # Feed prediction to accumulator (one-bet-per-bar)
            decision = accumulator.on_prediction(
                bar_id=bar_id,
                time_pct=elapsed_pct,
                model_prob=float(prob_up),
                market_prob=float(market.mid_up),
                spread=float(market.spread),
            )

            fill = None
            if decision:
                # Accumulator approved this trade — execute it
                fill = await trading_loop.on_partial_bar(
                    partial, market, decision.model_prob,
                )

            # Log every prediction for reconciliation replay
            trade_logger.log_prediction(
                bar_id=bar_id,
                elapsed_pct=elapsed_pct,
                model_prob=float(prob_up),
                market_prob=float(market.mid_up),
                market_spread=float(market.spread),
                condition_id=market.condition_id,
                features=features.flatten().tolist(),
                signal_edge=decision.edge if decision else float(abs(prob_up - market.mid_up)),
                signal_side=decision.side if decision else ("UP" if prob_up > 0.5 else "DOWN"),
                size_usd=float(fill.size_usd) if fill and fill.status == "filled" else 0,
                fill_price=float(fill.price) if fill and fill.status == "filled" else 0,
                fill_status=fill.status if fill else "no_trade",
            )

            if fill and fill.status == "filled":
                stats["trades"] += 1
                logger.info(
                    "TRADE: %s %s $%.2f @ %.4f (prob=%.3f, edge=%.3f) [%.0fus]",
                    asset.value, decision.side,
                    fill.size_usd, fill.price, decision.model_prob,
                    decision.edge, elapsed_us,
                )

        # Dashboard every 5 minutes
        if time.time() - last_dashboard > 300:
            last_dashboard = time.time()
            n_pos = len(portfolio._positions)
            logger.info(
                "DASHBOARD | bankroll=$%.2f | positions=%d | "
                "trades=%d | predictions=%d | pnl=$%.2f",
                bankroll.current, n_pos,
                stats["trades"], stats["predictions"],
                bankroll.current - args.bankroll,
            )
            save_state(portfolio, stats)

    # ── Shutdown ────────────────────────────────────────────────
    logger.info("Shutting down...")
    ws_feed.stop()
    trade_logger.close()
    save_state(portfolio, stats)
    logger.info(
        "Final: bankroll=$%.2f, trades=%d, PnL=$%.2f",
        bankroll.current, stats["trades"],
        bankroll.current - args.bankroll,
    )


def main() -> None:
    args = parse_args()
    asyncio.run(main_loop(args))


if __name__ == "__main__":
    main()
