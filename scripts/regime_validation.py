#!/usr/bin/env python
"""Regime-bucketed OOS validation for Pulse model.

Per auditor ruling (iter 51): compute OOS Sharpe and Brier per
regime_vol_state = {0:low, 1:normal, 2:high, 3:crisis}.

Acceptance criteria:
  - All 4 buckets OOS Sharpe > 0 → FULL PASS
  - 1-2 buckets Sharpe < 0 → RESTRICTED (log which regimes)
  - 3+ buckets Sharpe < 0 → FAIL

Usage:
    uv run scripts/regime_validation.py --asset BTC --timeframe 5m
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

import lightgbm as lgb
import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from qm.backtest.intrabar_backtest import IntraBarBacktester
from qm.core.types import Timeframe
from qm.features.cross_asset_intrabar import load_and_augment
from qm.model.calibration.calibrator import IsotonicCalibrator
from qm.model.targets.intrabar import IntraBarDataset

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("regime_validation")

REGIME_NAMES = {0: "low", 1: "normal", 2: "high", 3: "crisis"}
N_TICK_FEATURES = 8


def load_knobs() -> dict:
    for p in [Path("autoresearch/best_knobs.json"), Path("autoresearch/knobs.json")]:
        if p.exists():
            with open(p) as f:
                return json.load(f)
    logger.error("No knobs.json found")
    sys.exit(1)


def main() -> None:
    p = argparse.ArgumentParser(description="Regime-bucketed OOS validation")
    p.add_argument("--asset", required=True, choices=["BTC", "ETH", "SOL", "XRP"])
    p.add_argument("--timeframe", default="5m", choices=["5m", "15m", "1h"])
    args = p.parse_args()

    tf = {"5m": Timeframe.M5, "15m": Timeframe.M15, "1h": Timeframe.H1}[args.timeframe]
    knobs = load_knobs()

    # ── Load dataset ─────────────────────────────────────────────
    ds_path = Path(f"data/models/pulse_v2/{args.asset}_{args.timeframe}/dataset.npz")
    if not ds_path.exists():
        logger.error("No dataset at %s", ds_path)
        sys.exit(1)

    dataset = IntraBarDataset.load(ds_path)
    dataset = load_and_augment(dataset, args.asset, args.timeframe, knobs)
    all_names = list(dataset.feature_names)

    # Find regime_vol_state index in FULL feature set (before filtering)
    if "regime_vol_state" not in all_names:
        logger.error("regime_vol_state not in dataset features")
        sys.exit(1)
    regime_idx = all_names.index("regime_vol_state")

    # ── Time-pct filtering ───────────────────────────────────────
    tp_set = np.array(knobs.get("time_pcts", [0.80]))
    tp_mask = np.zeros(len(dataset.time_pcts), dtype=bool)
    for tp in tp_set:
        tp_mask |= np.isclose(dataset.time_pcts, tp, atol=1e-6)

    X_full = dataset.X[tp_mask]
    y = dataset.y[tp_mask]
    bar_indices = dataset.bar_indices[tp_mask]
    market_probs = dataset.market_probs[tp_mask]
    time_pcts = dataset.time_pcts[tp_mask]

    # Extract regime state from FULL feature set (before column filtering)
    regime_states = X_full[:, regime_idx]

    # ── Load model + calibrator ──────────────────────────────────
    model_dir = Path(f"data/models/pulse_v2/{args.asset}_{args.timeframe}")
    model = lgb.Booster(model_file=str(model_dir / "model.lgb"))

    from qm.model.calibration.calibrator import TimeAwareCalibrator

    cal_path = model_dir / "calibrator.pkl"
    if cal_path.exists():
        calibrator = TimeAwareCalibrator()
        calibrator.load(cal_path)
    else:
        calibrator = TimeAwareCalibrator()

    # ── Filter columns to match model's expected features ────────
    model_names = model.feature_name()
    col_indices = [all_names.index(n) for n in model_names]
    X = X_full[:, col_indices]

    logger.info("Dataset: %d samples, %d features, %d bars",
                len(y), X.shape[1], len(np.unique(bar_indices)))

    # ── 80/20 temporal split (same as training) ──────────────────
    unique_bars = np.unique(bar_indices)
    n_bars = len(unique_bars)
    split_idx = int(n_bars * 0.80)
    test_bars = unique_bars[split_idx:]
    test_mask = np.isin(bar_indices, test_bars)

    X_test = X[test_mask]
    y_test = y[test_mask]
    bi_test = bar_indices[test_mask]
    mp_test = market_probs[test_mask]
    tp_test = time_pcts[test_mask]
    regime_test = regime_states[test_mask]

    logger.info("Test set: %d samples, %d bars", len(y_test), len(test_bars))

    # ── Predict ──────────────────────────────────────────────────
    raw_probs = model.predict(X_test)
    cal_probs = calibrator.transform(raw_probs, tp_test)

    # ── Backtester ───────────────────────────────────────────────
    bt_cfg = knobs.get("backtest", {})
    backtester = IntraBarBacktester(
        fee_bps=bt_cfg.get("fee_bps", 0),
        spread=bt_cfg.get("spread", 0.02),
        min_edge=bt_cfg.get("min_edge", 0.01),
        max_trades_per_bar=bt_cfg.get("max_trades_per_bar", 15),
        max_daily_trades=bt_cfg.get("max_daily_trades", 500),
        fixed_bet_usd=bt_cfg.get("fixed_bet_usd", 50.0),
        timeframe=tf,
    )

    # ── Per-regime evaluation ────────────────────────────────────
    logger.info("")
    logger.info("=" * 70)
    logger.info("REGIME-BUCKETED OOS VALIDATION — %s %s", args.asset, args.timeframe)
    logger.info("=" * 70)

    results = {}
    for state_val, state_name in sorted(REGIME_NAMES.items()):
        mask = regime_test == state_val
        n = int(mask.sum())
        if n == 0:
            logger.info("  %-8s: no samples", state_name)
            results[state_name] = {"n": 0, "sharpe": 0.0, "brier": 0.0}
            continue

        metrics = backtester.evaluate_fast(
            cal_probs[mask], y_test[mask], mp_test[mask],
            tp_test[mask], bi_test[mask],
        )
        brier = float(np.mean((cal_probs[mask] - y_test[mask]) ** 2))

        results[state_name] = {
            "n": n,
            "sharpe": metrics.get("sharpe", 0.0),
            "brier": brier,
            "pnl": metrics.get("total_pnl", 0.0),
            "trades": metrics.get("n_trades", 0),
            "win_rate": metrics.get("win_rate", 0.0),
        }

        logger.info(
            "  %-8s: n=%5d  Sharpe=%8.2f  Brier=%.4f  PnL=%.2f  trades=%d  win=%.1f%%",
            state_name, n,
            results[state_name]["sharpe"],
            brier,
            results[state_name]["pnl"],
            results[state_name]["trades"],
            results[state_name]["win_rate"] * 100,
        )

    # ── Verdict ──────────────────────────────────────────────────
    logger.info("")
    negative_regimes = [
        name for name, r in results.items()
        if r["n"] > 0 and r["sharpe"] <= 0
    ]

    if len(negative_regimes) == 0:
        verdict = "FULL PASS — positive Sharpe in all regime states"
    elif len(negative_regimes) <= 2:
        verdict = f"RESTRICTED — negative Sharpe in: {', '.join(negative_regimes)}"
    else:
        names = ", ".join(negative_regimes)
        verdict = f"FAIL — negative Sharpe in {len(negative_regimes)}/4: {names}"

    logger.info("  VERDICT: %s", verdict)
    logger.info("=" * 70)


if __name__ == "__main__":
    main()
