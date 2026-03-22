#!/usr/bin/env python
"""Realistic Kelly-sized backtest for the Pulse model.

Replaces $100 fixed bets with fractional Kelly sizing on a real
bankroll ($5K default). Reports true expected returns, drawdowns,
and Sharpe with realistic position sizing.

Usage:
    uv run scripts/kelly_backtest.py --asset BTC --bankroll 5000
    uv run scripts/kelly_backtest.py --asset ETH --bankroll 10000
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from pathlib import Path

import lightgbm as lgb
import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from qm.backtest.intrabar_backtest import IntraBarBacktester
from qm.backtest.metrics.calibration import brier_score, expected_calibration_error
from qm.backtest.sanity import BacktestSanityChecker
from qm.core.types import Timeframe
from qm.features.cross_asset_intrabar import load_and_augment
from qm.model.calibration.calibrator import IsotonicCalibrator
from qm.model.targets.intrabar import IntraBarDataset

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("kelly_backtest")

CONFIG_PATH = Path("autoresearch/knobs.json")
N_TICK_FEATURES = 8


def load_knobs() -> dict:
    with open(CONFIG_PATH) as f:
        return json.load(f)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Kelly-sized Pulse backtest")
    p.add_argument("--asset", required=True, choices=["BTC", "ETH", "SOL", "XRP"])
    p.add_argument("--timeframe", default="5m", choices=["5m", "15m", "1h"])
    p.add_argument("--bankroll", type=float, default=5000.0)
    p.add_argument("--kelly-fraction", type=float, default=0.25)
    p.add_argument("--max-bet-frac", type=float, default=0.05)
    p.add_argument("--max-bet-usd", type=float, default=500.0)
    p.add_argument("--min-bet-usd", type=float, default=5.0)
    p.add_argument("--seed", type=int, default=42)
    return p.parse_args()


def main() -> None:
    args = parse_args()
    t0 = time.time()

    knobs = load_knobs()
    cached_features = set(knobs["cached_features"])
    time_pcts_cfg = knobs["time_pcts"]
    backtest_cfg = knobs["backtest"]

    tf_map = {"5m": Timeframe.M5, "15m": Timeframe.M15, "1h": Timeframe.H1}
    tf = tf_map[args.timeframe]

    # ── Load dataset ────────────────────────────────────────────
    cache_path = Path(
        f"data/models/pulse_v2/{args.asset}_{args.timeframe}/dataset.npz"
    )
    if not cache_path.exists():
        logger.error("No cached dataset at %s", cache_path)
        sys.exit(1)

    dataset = IntraBarDataset.load(cache_path)
    dataset = load_and_augment(dataset, args.asset, args.timeframe, knobs)
    logger.info(
        "Loaded: %d samples, %d features",
        len(dataset.y), dataset.X.shape[1],
    )

    # ── Feature + time filtering (same as train_pulse_fast.py) ──
    all_names = dataset.feature_names
    keep_indices = list(range(N_TICK_FEATURES))
    for i in range(N_TICK_FEATURES, len(all_names)):
        name = all_names[i]
        if name in cached_features or name.startswith("btc_"):
            keep_indices.append(i)
    feature_names = [all_names[i] for i in keep_indices]

    tp_set = np.array(time_pcts_cfg)
    tp_mask = np.zeros(len(dataset.time_pcts), dtype=bool)
    for tp in tp_set:
        tp_mask |= np.isclose(dataset.time_pcts, tp, atol=1e-6)

    X = dataset.X[tp_mask][:, keep_indices]
    y = dataset.y[tp_mask]
    bar_indices = dataset.bar_indices[tp_mask]
    market_probs = dataset.market_probs[tp_mask]
    time_pcts = dataset.time_pcts[tp_mask]

    # ── 80/20 temporal split ────────────────────────────────────
    unique_bars = np.unique(bar_indices)
    n_bars = len(unique_bars)
    split_idx = int(n_bars * 0.80)
    train_bars = unique_bars[:split_idx]

    train_mask = np.isin(bar_indices, train_bars)
    test_mask = ~train_mask

    X_train, y_train = X[train_mask], y[train_mask]
    X_test, y_test = X[test_mask], y[test_mask]

    logger.info(
        "Split: %d train, %d test samples (%d/%d bars)",
        train_mask.sum(), test_mask.sum(), split_idx, n_bars - split_idx,
    )

    # ── Train model ─────────────────────────────────────────────
    params = {
        "objective": "binary",
        "metric": "binary_logloss",
        "verbosity": -1,
        "max_depth": 5,
        "num_leaves": 70,
        "min_child_samples": 700,
        "learning_rate": 0.02,
        "subsample": 0.8,
        "colsample_bytree": 0.7,
        "seed": args.seed,
    }
    ds = lgb.Dataset(X_train, y_train, feature_name=feature_names)
    model = lgb.train(params, ds, num_boost_round=1200)

    # ── Calibrate ───────────────────────────────────────────────
    cal = IsotonicCalibrator()
    cal.fit(model.predict(X_train), y_train)
    cal_probs = cal.transform(model.predict(X_test))

    brier = brier_score(cal_probs, y_test)
    ece = expected_calibration_error(cal_probs, y_test)
    logger.info("OOS Brier: %.4f, ECE: %.4f", brier, ece)

    # ── Run fixed-bet backtest (baseline comparison) ────────────
    logger.info("")
    logger.info("=" * 60)
    logger.info("FIXED-BET BACKTEST ($100 flat)")
    logger.info("=" * 60)

    bt_fixed = IntraBarBacktester(
        fee_bps=backtest_cfg.get("fee_bps", 0),
        spread=backtest_cfg.get("spread", 0.02),
        min_edge=backtest_cfg.get("min_edge", 0.01),
        max_trades_per_bar=backtest_cfg.get("max_trades_per_bar", 15),
        max_daily_trades=backtest_cfg.get("max_daily_trades", 500),
        fixed_bet_usd=100.0,
        timeframe=tf,
    )
    fixed_result = bt_fixed.run_full(
        cal_probs, y_test, market_probs[test_mask],
        time_pcts[test_mask], bar_indices[test_mask],
        initial_bankroll=args.bankroll,
    )
    _print_result("$100 fixed", fixed_result.metrics, args.bankroll)

    # ── Run Kelly backtest ──────────────────────────────────────
    logger.info("")
    logger.info("=" * 60)
    logger.info("KELLY BACKTEST (fraction=%.2f, max=%.0f%%)",
                args.kelly_fraction, args.max_bet_frac * 100)
    logger.info("=" * 60)

    bt_kelly = IntraBarBacktester(
        fee_bps=backtest_cfg.get("fee_bps", 0),
        spread=backtest_cfg.get("spread", 0.02),
        min_edge=backtest_cfg.get("min_edge", 0.01),
        max_trades_per_bar=backtest_cfg.get("max_trades_per_bar", 15),
        max_daily_trades=backtest_cfg.get("max_daily_trades", 500),
        kelly_fraction=args.kelly_fraction,
        max_bet_frac=args.max_bet_frac,
        fixed_bet_usd=None,  # enables Kelly mode
        timeframe=tf,
    )
    kelly_result = bt_kelly.run_full(
        cal_probs, y_test, market_probs[test_mask],
        time_pcts[test_mask], bar_indices[test_mask],
        initial_bankroll=args.bankroll,
        max_bet_usd=args.max_bet_usd,
        min_bet_usd=args.min_bet_usd,
    )
    _print_result("Kelly", kelly_result.metrics, args.bankroll)

    # ── Sanity check ────────────────────────────────────────────
    checker = BacktestSanityChecker()
    kelly_metrics_for_check = {
        "brier": brier,
        "ece": ece,
        **{k: v for k, v in kelly_result.metrics.items()
           if isinstance(v, (int, float))},
    }
    results = checker.check(kelly_metrics_for_check)
    logger.info("")
    logger.info(checker.summary(results))

    elapsed = time.time() - t0
    logger.info("")
    logger.info("Done in %.1fs", elapsed)


def _print_result(
    label: str, metrics: dict, initial_bankroll: float
) -> None:
    pnl = metrics.get("total_pnl", 0)
    final = initial_bankroll + pnl
    ret_pct = (pnl / initial_bankroll) * 100 if initial_bankroll > 0 else 0
    n_trades = metrics.get("n_trades", 0)

    # Estimate test period in days (from n_trades and trade frequency)
    test_days = max(1, n_trades / 500)  # ~500 trades/day at 5m
    monthly_ret = ret_pct * (30 / test_days) if test_days > 0 else 0

    logger.info("  Initial bankroll:   $%.2f", initial_bankroll)
    logger.info("  Final bankroll:     $%.2f", final)
    logger.info("  Total PnL:          $%.2f (%.2f%%)", pnl, ret_pct)
    logger.info("  Est. monthly return: %.2f%%", monthly_ret)
    logger.info("  Trades:             %d", n_trades)
    logger.info("  Win rate:           %.2f%%", metrics.get("win_rate", 0) * 100)
    logger.info("  Sharpe:             %.2f", metrics.get("sharpe", 0))
    logger.info("  Max drawdown:       %.2f%%", metrics.get("max_dd", 0) * 100)
    logger.info(
        "  Avg PnL/trade:      $%.4f",
        metrics.get("avg_pnl_per_trade", 0),
    )


if __name__ == "__main__":
    main()
