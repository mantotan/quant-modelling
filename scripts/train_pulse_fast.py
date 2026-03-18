#!/usr/bin/env python
"""Fast single-asset Pulse trainer for autoresearch iterations.

Reads experiment config from autoresearch/knobs.json (never hardcoded).
Loads pre-cached IntraBarDataset for instant startup (~1s vs 15min).
Outputs structured JSON results to stdout for agent parsing.
Exit code 0 = success, 1 = crash.

Usage:
    uv run scripts/train_pulse_fast.py --asset BTC --timeframe 5m
    uv run scripts/train_pulse_fast.py --asset BTC --trials 40 --timeout 420 --mode fast
    uv run scripts/train_pulse_fast.py --asset BTC --mode verify --trials 100
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import sys
import time
import traceback
from pathlib import Path

import lightgbm as lgb
import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from qm.backtest.intrabar_backtest import IntraBarBacktester
from qm.backtest.metrics.calibration import brier_score, expected_calibration_error
from qm.backtest.validation.walk_forward import WalkForwardSplitter
from qm.core.types import Timeframe
from qm.model.calibration.calibrator import IsotonicCalibrator
from qm.model.targets.intrabar import IntraBarDataset
from qm.model.trainers.device import detect_device

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
    stream=sys.stderr,  # logs to stderr, structured output to stdout
)
logger = logging.getLogger("train_pulse_fast")

CONFIG_PATH = Path("autoresearch/knobs.json")

# Tick features (indices 0-7) are ALWAYS included — they are the core signal.
N_TICK_FEATURES = 8


def load_knobs() -> dict:
    """Load research knobs from config file."""
    with open(CONFIG_PATH) as f:
        return json.load(f)


def config_hash() -> str:
    """MD5 hash of current knobs.json for result correlation."""
    return hashlib.md5(CONFIG_PATH.read_bytes()).hexdigest()[:8]


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Fast Pulse trainer")
    p.add_argument("--asset", required=True, choices=["BTC", "ETH", "SOL", "XRP"])
    p.add_argument("--timeframe", default="5m", choices=["5m", "15m", "1h"])
    p.add_argument("--trials", type=int, default=40, help="Optuna trials (default 40)")
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--timeout", type=int, default=420, help="Wall-clock budget in seconds")
    p.add_argument("--mode", default="fast", choices=["fast", "verify"])
    return p.parse_args()


def run(args: argparse.Namespace) -> dict:
    import optuna

    optuna.logging.set_verbosity(optuna.logging.WARNING)

    t0 = time.time()
    cfg_hash = config_hash()
    device = detect_device(prefer_gpu=True)

    # ── Load knobs from config ────────────────────────────────────
    knobs = load_knobs()
    CACHED_FEATURES = set(knobs["cached_features"])
    TIME_PCTS = knobs["time_pcts"]
    HPO_SEARCH_SPACE = {k: tuple(v) for k, v in knobs["hpo_search_space"].items()}
    WALK_FORWARD = knobs["walk_forward"]
    BACKTEST = knobs["backtest"]

    tf_map = {"5m": Timeframe.M5, "15m": Timeframe.M15, "1h": Timeframe.H1}
    tf = tf_map[args.timeframe]

    # ── Mode-dependent trial/timeout ──────────────────────────────
    if args.mode == "verify":
        n_trials = max(args.trials, 100)
        hpo_timeout = max(args.timeout - 90, 120)
    else:
        n_trials = args.trials
        hpo_timeout = max(args.timeout - 60, 60)

    # ── Load cached dataset ───────────────────────────────────────
    cache_path = Path(f"data/models/pulse_v2/{args.asset}_{args.timeframe}/dataset.npz")
    if not cache_path.exists():
        return {"status": "error", "reason": f"No cached dataset at {cache_path}. Run train_pulse_v2.py first."}

    dataset = IntraBarDataset.load(cache_path)
    logger.info("Loaded cached dataset: %d samples, %d features", len(dataset.y), dataset.X.shape[1])

    # Warn if market_sim efficiency differs from what generated the dataset
    eff = knobs.get("market_sim", {}).get("efficiency", 0.75)
    if eff != 0.75:
        logger.warning("market_sim.efficiency=%.2f but dataset was generated with 0.75. "
                        "Changing this knob has NO runtime effect — market_probs are baked into .npz", eff)

    # ── Feature filtering ─────────────────────────────────────────
    # Tick features (0..7) always included. Historical features (8..22) filtered by knobs.
    all_names = dataset.feature_names
    keep_indices = list(range(N_TICK_FEATURES))  # tick features always in
    for i in range(N_TICK_FEATURES, len(all_names)):
        if all_names[i] in CACHED_FEATURES:
            keep_indices.append(i)

    feature_names_used = [all_names[i] for i in keep_indices]

    # ── Time-pct filtering ────────────────────────────────────────
    # Use tolerance-based matching to avoid float equality issues
    tp_set = np.array(TIME_PCTS)
    tp_mask = np.zeros(len(dataset.time_pcts), dtype=bool)
    for tp in tp_set:
        tp_mask |= np.isclose(dataset.time_pcts, tp, atol=1e-6)

    X = dataset.X[tp_mask][:, keep_indices]
    y = dataset.y[tp_mask]
    bar_indices = dataset.bar_indices[tp_mask]
    market_probs = dataset.market_probs[tp_mask]
    time_pcts = dataset.time_pcts[tp_mask]

    logger.info("After filtering: %d samples, %d features, %d time_pcts",
                len(y), len(feature_names_used), len(tp_set))

    # ── 80/20 bar-level temporal split ────────────────────────────
    unique_bars = np.unique(bar_indices)
    n_bars = len(unique_bars)
    split_bar_idx = int(n_bars * 0.80)
    train_bars = unique_bars[:split_bar_idx]

    train_mask = np.isin(bar_indices, train_bars)
    test_mask = ~train_mask

    X_train, y_train = X[train_mask], y[train_mask]
    X_test, y_test = X[test_mask], y[test_mask]
    mp_test = market_probs[test_mask]
    tp_test = time_pcts[test_mask]
    bi_test = bar_indices[test_mask]
    train_bar_indices = bar_indices[train_mask]

    base_rate = float(y_train.mean())
    logger.info("Data: %d train (%d bars), %d test (%d bars), base=%.4f",
                len(X_train), split_bar_idx, len(X_test), n_bars - split_bar_idx, base_rate)

    # ── Walk-forward splitter (bar-level) ─────────────────────────
    wf = WALK_FORWARD
    train_unique_bars = np.unique(train_bar_indices)
    n_train_bars = len(train_unique_bars)

    splitter = WalkForwardSplitter(
        n_splits=wf["n_splits"],
        train_period=min(wf["train_bars"], n_train_bars // 2),
        test_period=min(wf["test_bars"], n_train_bars // 10),
        purge_period=wf["purge_period"],
        embargo_period=wf["embargo_period"],
    )

    # ── Optuna HPO ────────────────────────────────────────────────
    ss = HPO_SEARCH_SPACE

    def objective(trial: optuna.Trial) -> float:
        params = {
            "objective": "binary",
            "metric": "binary_logloss",
            "verbosity": -1,
            "device": device,
            "seed": args.seed,
            "n_estimators": trial.suggest_int("n_estimators", *ss["n_estimators"]),
            "learning_rate": trial.suggest_float("lr", *ss["learning_rate"], log=True),
            "max_depth": trial.suggest_int("max_depth", *ss["max_depth"]),
            "num_leaves": trial.suggest_int("num_leaves", *ss["num_leaves"]),
            "min_child_samples": trial.suggest_int("min_child", *ss["min_child_samples"]),
            "subsample": trial.suggest_float("subsample", *ss["subsample"]),
            "colsample_bytree": trial.suggest_float("colsample", *ss["colsample_bytree"]),
            "reg_alpha": trial.suggest_float("reg_alpha", *ss["reg_alpha"], log=True),
            "reg_lambda": trial.suggest_float("reg_lambda", *ss["reg_lambda"], log=True),
        }

        n_est = params.pop("n_estimators")
        for alias, real in [("lr", "learning_rate"), ("min_child", "min_child_samples"),
                            ("colsample", "colsample_bytree")]:
            if alias in params:
                params[real] = params.pop(alias)

        briers = []
        for bar_train_idx, bar_test_idx in splitter.split(n_train_bars):
            bars_tr = train_unique_bars[bar_train_idx]
            bars_te = train_unique_bars[bar_test_idx]

            tr_mask = np.isin(train_bar_indices, bars_tr)
            te_mask = np.isin(train_bar_indices, bars_te)

            if tr_mask.sum() == 0 or te_mask.sum() == 0:
                continue

            ds = lgb.Dataset(X_train[tr_mask], y_train[tr_mask],
                             feature_name=feature_names_used)
            vs = lgb.Dataset(X_train[te_mask], y_train[te_mask],
                             reference=ds)

            model = lgb.train(
                params, ds, num_boost_round=n_est,
                valid_sets=[vs],
                callbacks=[lgb.early_stopping(50, verbose=False)],
            )
            preds = model.predict(X_train[te_mask])
            briers.append(float(np.mean((preds - y_train[te_mask]) ** 2)))

        return float(np.mean(briers)) if briers else 1.0

    study = optuna.create_study(direction="minimize",
                                sampler=optuna.samplers.TPESampler(seed=args.seed))
    study.optimize(objective, n_trials=n_trials, n_jobs=1, timeout=hpo_timeout)

    logger.info("Best HPO Brier: %.6f (%d/%d trials, %s mode)",
                study.best_value, len(study.trials), n_trials, args.mode)

    # ── Retrain best ──────────────────────────────────────────────
    bp = study.best_params.copy()
    n_est = bp.pop("n_estimators", 500)
    for alias, real in [("lr", "learning_rate"), ("min_child", "min_child_samples"),
                        ("colsample", "colsample_bytree")]:
        if alias in bp:
            bp[real] = bp.pop(alias)

    final_params = {
        "objective": "binary", "metric": "binary_logloss",
        "verbosity": -1, "device": device, "seed": args.seed, **bp,
    }
    ds_final = lgb.Dataset(X_train, y_train, feature_name=feature_names_used)
    model_final = lgb.train(final_params, ds_final, num_boost_round=n_est)

    # ── Calibrate (walk-forward OOS on train set) ─────────────────
    oos_probs = np.zeros(len(y_train))
    oos_mask = np.zeros(len(y_train), dtype=bool)
    for bar_train_idx, bar_test_idx in splitter.split(n_train_bars):
        bars_tr = train_unique_bars[bar_train_idx]
        bars_te = train_unique_bars[bar_test_idx]

        tr_mask = np.isin(train_bar_indices, bars_tr)
        te_mask = np.isin(train_bar_indices, bars_te)

        if tr_mask.sum() == 0 or te_mask.sum() == 0:
            continue

        ds = lgb.Dataset(X_train[tr_mask], y_train[tr_mask])
        m = lgb.train(final_params, ds, num_boost_round=n_est)
        oos_probs[te_mask] = m.predict(X_train[te_mask])
        oos_mask[te_mask] = True

    cal = IsotonicCalibrator()
    cal.fit(oos_probs[oos_mask], y_train[oos_mask])

    # ── Evaluate on test set ──────────────────────────────────────
    raw_test = model_final.predict(X_test)
    cal_test = cal.transform(raw_test)

    acc = float(np.mean((cal_test > 0.5) == (y_test == 1)))
    brier = brier_score(cal_test, y_test)
    ece = expected_calibration_error(cal_test, y_test)

    # ── Backtest (maker-only: fee_bps=0, impact_bps=0) ───────────
    bt = BACKTEST
    backtester = IntraBarBacktester(
        fee_bps=bt["fee_bps"],
        spread=bt["spread"],
        min_edge=bt["min_edge"],
        impact_bps=bt.get("impact_bps", 0),
        max_trades_per_bar=bt.get("max_trades_per_bar", 3),
        max_daily_trades=bt.get("max_daily_trades", 100),
        fixed_bet_usd=bt.get("fixed_bet_usd", 50.0),
        timeframe=tf,
    )
    bt_metrics = backtester.evaluate_fast(cal_test, y_test, mp_test, tp_test, bi_test)

    # ── Both-sides evaluation (trader_a-style) ────────────────────
    bs_results = {}
    strategies = knobs.get("strategies", {})
    bs_cfg = strategies.get("both_sides_mm", {})
    if bs_cfg.get("enabled", False):
        try:
            from qm.backtest.both_sides_backtest import BothSidesBacktester
            bs_bt = BothSidesBacktester(
                margin=bs_cfg.get("margin", 0.03),
                fixed_bet_usd=bs_cfg.get("fixed_bet_usd", 100),
                max_trades_per_bar=bs_cfg.get("max_trades_per_bar", 26),
                fee_bps=bt["fee_bps"],
                timeframe=tf,
            )
            bs_metrics = bs_bt.evaluate_fast(cal_test, y_test, mp_test, tp_test, bi_test)
            bs_results = {
                "bs_pnl": round(bs_metrics.get("total_pnl", 0), 2),
                "bs_sharpe": round(bs_metrics.get("sharpe", 0), 2),
                "bs_trades": bs_metrics.get("n_trades", 0),
            }
            logger.info("Both-sides: pnl=$%.2f, sharpe=%.2f, trades=%d",
                        bs_results["bs_pnl"], bs_results["bs_sharpe"], bs_results["bs_trades"])
        except Exception as e:
            logger.warning("Both-sides eval failed: %s", e)

    # ── Feature importance ────────────────────────────────────────
    fi = dict(zip(model_final.feature_name(),
                  model_final.feature_importance(importance_type="gain")))
    top_features = sorted(fi.items(), key=lambda x: -x[1])[:10]

    elapsed = time.time() - t0

    return {
        "status": "ok",
        "mode": args.mode,
        "model": "pulse",
        "config_hash": cfg_hash,
        "asset": args.asset,
        "timeframe": args.timeframe,
        "elapsed_s": round(elapsed, 1),
        "n_train": len(X_train),
        "n_test": len(X_test),
        "n_features": len(feature_names_used),
        "n_bars_train": split_bar_idx,
        "n_bars_test": n_bars - split_bar_idx,
        "base_rate": round(base_rate, 4),
        "hpo_brier": round(study.best_value, 6),
        "hpo_trials": len(study.trials),
        "oos_accuracy": round(acc, 4),
        "oos_brier": round(brier, 6),
        "oos_ece": round(ece, 4),
        "backtest_pnl": round(bt_metrics.get("total_pnl", 0), 2),
        "backtest_trades": bt_metrics.get("n_trades", 0),
        "backtest_win_rate": round(bt_metrics.get("win_rate", 0), 4),
        "backtest_sharpe": round(bt_metrics.get("sharpe", 0), 2),
        "backtest_max_dd": round(bt_metrics.get("max_dd", 0), 4),
        "top_features": [f[0] for f in top_features],
        "best_params": {k: round(v, 6) if isinstance(v, float) else v
                        for k, v in study.best_params.items()},
        **bs_results,
    }


def main() -> None:
    args = parse_args()
    try:
        results = run(args)
    except Exception:
        traceback.print_exc(file=sys.stderr)
        results = {"status": "crash", "reason": traceback.format_exc()[-500:]}

    # Structured output to stdout — this is what the agent parses
    print("===RESULTS_JSON===")
    print(json.dumps(results, indent=2))
    print("===END_RESULTS===")

    sys.exit(0 if results["status"] == "ok" else 1)


if __name__ == "__main__":
    main()
