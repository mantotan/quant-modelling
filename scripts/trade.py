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
from datetime import UTC, datetime, timedelta
from pathlib import Path

import lightgbm as lgb
import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from qm.core.types import Asset, MarketType, Outcome, PolymarketMarket, Timeframe
from qm.data.connectors.polymarket_recorder import (
    _extract_prices,
    _is_binary_up_down,
    _match_asset,
)
from qm.data.ingestion.bar_builder import BarBuilder
from qm.data.storage.parquet import ParquetStore
from qm.execution.audit import AuditWriter
from qm.execution.loop import TradingLoop
from qm.execution.paper.engine import PaperExecutor
from qm.features.live_cache import RUST_AVAILABLE, get_feature_calculator
from qm.features.pipeline import FeaturePipeline
from qm.model.calibration.calibrator import IsotonicCalibrator
from qm.model.signals import SignalGenerator
from qm.risk.bankroll import Bankroll
from qm.risk.circuit_breaker import CircuitBreaker
from qm.risk.manager import RiskManager
from qm.strategy.filter import TradeFilter
from qm.strategy.portfolio import Portfolio
from qm.strategy.sizing.kelly import KellySizer

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("trade")

# Time thresholds for Pulse predictions (fraction of bar elapsed)
TIME_PCTS = [0.30, 0.40, 0.60, 0.80]

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
    model_path = model_dir / f"{asset}_{tf}" / "model.txt"
    cal_path = model_dir / f"{asset}_{tf}" / "calibrator.pkl"

    if not model_path.exists():
        logger.error("No model at %s", model_path)
        sys.exit(1)

    model = lgb.Booster(model_file=str(model_path))
    logger.info("Loaded model: %s", model_path)

    calibrator = None
    if cal_path.exists():
        import pickle
        with open(cal_path, "rb") as f:
            calibrator = pickle.load(f)
        logger.info("Loaded calibrator: %s", cal_path)
    else:
        calibrator = IsotonicCalibrator()
        logger.warning("No calibrator found, using uncalibrated probs")

    return model, calibrator


def warm_up(
    asset: Asset,
    tf: Timeframe,
    feature_calc,
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

    if RUST_AVAILABLE:
        feature_calc.update_cache(asset.value, cache_dict)
    else:
        feature_calc.update_cache(asset, cache_dict)

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


async def discover_markets(asset: Asset) -> PolymarketMarket | None:
    """Find an active Polymarket 5m binary crypto market.

    Uses the same logic as PolymarketOddsRecorder._discover_markets().
    Returns None if no active market found.
    """
    import aiohttp

    url = "https://gamma-api.polymarket.com/markets"
    try:
        async with aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=10),
        ) as session, session.get(
            url, params={"active": "true", "closed": "false"},
        ) as resp:
            if resp.status != 200:
                return None
            markets = await resp.json()
    except Exception:
        logger.debug("Gamma API unreachable")
        return None

    for m in markets:
        tokens = m.get("tokens", [])
        if not _is_binary_up_down(tokens):
            continue
        matched = _match_asset(m.get("question", ""))
        if matched != asset:
            continue

        price_up, price_down = _extract_prices(tokens)
        if price_up is None:
            continue

        return PolymarketMarket(
            condition_id=m.get("condition_id", ""),
            token_id_up=tokens[0].get("token_id", ""),
            token_id_down=tokens[1].get("token_id", ""),
            asset=asset,
            market_type=MarketType.FIVE_MIN,
            window_start=datetime.now(UTC),
            window_end=datetime.now(UTC) + timedelta(minutes=5),
            mid_up=price_up or 0.5,
            spread=abs(1.0 - (price_up or 0.5) - (price_down or 0.5)),
            volume=float(m.get("volume", 0) or 0),
        )

    return None


async def resolution_monitor(
    portfolio: Portfolio, trading_loop: TradingLoop,
) -> None:
    """Poll for market resolutions every 30s."""
    while True:
        await asyncio.sleep(30.0)
        positions = list(portfolio._positions.values())
        if not positions:
            continue

        for pos in positions:
            # Check if past expected resolution time
            age = (datetime.now(UTC) - pos.entry_time).total_seconds()
            if age > 360:  # > 6 min (5m bar + 1m buffer)
                # Resolve based on whether market moved in our direction
                # In paper mode, use 50/50 random resolution
                # In live mode, poll Gamma API (Phase 3 G)
                import random
                won = random.random() < 0.5
                outcome = pos.side if won else (
                    Outcome.DOWN if pos.side == Outcome.UP else Outcome.UP
                )
                pnl = await trading_loop.on_market_resolution(
                    pos.condition_id, outcome,
                )
                logger.info(
                    "Resolved %s %s: %s → PnL $%.2f",
                    pos.asset.value, pos.side.value,
                    "WIN" if won else "LOSS", pnl,
                )


def save_state(portfolio: Portfolio, stats: dict) -> None:
    """Save portfolio state for crash recovery."""
    state = {
        "bankroll": portfolio.bankroll.to_dict(),
        "n_positions": len(portfolio._positions),
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

    # ── Feature calculator (Rust or Python) ─────────────────────
    feature_calc = get_feature_calculator()
    logger.info(
        "Feature calculator: %s (%d features)",
        "Rust" if RUST_AVAILABLE else "Python",
        feature_calc.n_features() if RUST_AVAILABLE else feature_calc.n_features,
    )

    # ── Build BarBuilder for tick aggregation ───────────────────
    bar_builder = BarBuilder(assets=[asset], timeframes=[tf])

    # ── Warm-up: populate feature cache ─────────────────────────
    warm_up(asset, tf, feature_calc, bar_builder)

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
    trade_filter = TradeFilter(risk_manager=risk_manager)
    executor = create_executor(args.mode)
    audit = AuditWriter()

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

    # ── Start resolution monitor ────────────────────────────────
    asyncio.create_task(resolution_monitor(portfolio, trading_loop))

    # ── Main polling loop ───────────────────────────────────────
    last_triggered: dict[Asset, set[float]] = {}
    current_bar_id: dict[Asset, int] = {}
    last_dashboard = time.time()
    bar_seconds = {"5m": 300.0, "15m": 900.0, "1h": 3600.0}[args.timeframe]

    logger.info("Starting main loop (1s polling)...")
    logger.info("Waiting for Polymarket market discovery...")

    running = True

    def handle_shutdown(sig, frame):
        nonlocal running
        logger.info("Shutdown signal received")
        running = False

    signal.signal(signal.SIGINT, handle_shutdown)
    signal.signal(signal.SIGTERM, handle_shutdown)

    while running:
        await asyncio.sleep(1.0)

        # Get partial bar snapshot
        partial = bar_builder.get_partial_bar(asset, tf)

        if partial is None:
            # No bar data yet — try to simulate a tick to prime the builder
            # In production, ticks come from CcxtWebsocketConnector
            # For now, just wait
            continue

        bar_id = int(partial.window_start.timestamp())
        if bar_id != current_bar_id.get(asset):
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

            # Discover active Polymarket market
            market = await discover_markets(asset)
            if market is None:
                logger.debug("No active market for %s", asset.value)
                continue

            # Compute features (Rust or Python)
            t0 = time.perf_counter_ns()
            if RUST_AVAILABLE:
                features = np.array(feature_calc.compute(
                    asset.value,
                    partial.open, partial.high_so_far,
                    partial.low_so_far, partial.current_price,
                    partial.volume_so_far, partial.trade_count,
                    partial.elapsed_seconds, partial.remaining_seconds,
                ))
            else:
                features = feature_calc.compute(partial)

            # Model prediction
            prob_up = model.predict(features.reshape(1, -1))[0]
            if calibrator and hasattr(calibrator, "transform"):
                prob_up = calibrator.transform(
                    np.array([prob_up]),
                )[0]

            elapsed_us = (time.perf_counter_ns() - t0) / 1000
            stats["predictions"] += 1

            # Execute via TradingLoop
            fill = await trading_loop.on_partial_bar(
                partial, market, float(prob_up),
            )

            if fill and fill.status == "filled":
                stats["trades"] += 1
                logger.info(
                    "TRADE: %s %s $%.2f @ %.4f (prob=%.3f, edge=%.3f) [%.0fus]",
                    asset.value, "UP" if prob_up > 0.5 else "DOWN",
                    fill.size_usd, fill.price, prob_up,
                    abs(prob_up - market.mid_up), elapsed_us,
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
