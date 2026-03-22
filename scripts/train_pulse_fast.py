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
from qm.features.cross_asset_intrabar import load_and_augment
from qm.model.calibration.calibrator import TimeAwareCalibrator
from qm.model.objective import ObjectiveConfig, compute_objective
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
    p.add_argument("--save", action="store_true",
                   help="Save model + calibrator to data/models/pulse_v2/{ASSET}_{TF}/")
    return p.parse_args()


def _run_specialist_hpo(
    X_sub, y_sub, bar_indices_sub, tp_sub,
    feature_names, splitter_fn, ss, device, seed, n_trials, hpo_timeout, obj_config,
    label,
):
    """Run Optuna HPO for one specialist (early or late)."""
    import optuna

    unique_bars = np.unique(bar_indices_sub)
    n_bars = len(unique_bars)
    splitter = splitter_fn(n_bars)

    def objective(trial: optuna.Trial) -> float:
        params = {
            "objective": "binary", "metric": "binary_logloss",
            "verbosity": -1, "device": device, "seed": seed,
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

        fold_briers = []
        for bar_train_idx, bar_test_idx in splitter.split(n_bars):
            bars_tr = unique_bars[bar_train_idx]
            bars_te = unique_bars[bar_test_idx]
            tr_m = np.isin(bar_indices_sub, bars_tr)
            te_m = np.isin(bar_indices_sub, bars_te)
            if tr_m.sum() == 0 or te_m.sum() == 0:
                continue
            ds = lgb.Dataset(X_sub[tr_m], y_sub[tr_m], feature_name=feature_names)
            vs = lgb.Dataset(X_sub[te_m], y_sub[te_m], reference=ds)
            model = lgb.train(params, ds, num_boost_round=n_est,
                              valid_sets=[vs], callbacks=[lgb.early_stopping(50, verbose=False)])
            preds = model.predict(X_sub[te_m])
            fold_briers.append(float(np.mean((preds - y_sub[te_m]) ** 2)))

        if not fold_briers:
            return 1.0
        avg_metrics = {"brier": float(np.mean(fold_briers)), "sharpe": 0.0,
                       "n_trades": int(len(y_sub) / max(len(fold_briers), 1)), "max_dd": 0.0}
        return compute_objective(avg_metrics, obj_config)

    study = optuna.create_study(direction="minimize",
                                sampler=optuna.samplers.TPESampler(seed=seed))
    study.optimize(objective, n_trials=n_trials, n_jobs=1, timeout=hpo_timeout)
    logger.info("%s specialist: best objective %.6f (%d trials)",
                label, study.best_value, len(study.trials))
    return study


def _run_specialist_path(
    X_train, y_train, X_test, y_test, mp_test, tp_test, bi_test,
    train_bar_indices, tp_train, train_unique_bars, n_train_bars,
    feature_names_used, spec_cfg, ss, device, args, obj_config,
    n_trials, hpo_timeout, tf, knobs, cfg_hash, t0,
    split_bar_idx, n_bars, base_rate,
):
    """Specialist training: separate HPO for early and late time_pcts."""
    import optuna

    optuna.logging.set_verbosity(optuna.logging.WARNING)

    early_tps = set(spec_cfg.get("early_time_pcts", [0.10, 0.20]))
    late_tps = set(spec_cfg.get("late_time_pcts", [0.40, 0.60, 0.80]))
    boundary = spec_cfg.get("boundary", 0.40)

    # Split train data by time_pct
    early_train_mask = np.zeros(len(tp_train), dtype=bool)
    late_train_mask = np.zeros(len(tp_train), dtype=bool)
    for i in range(len(tp_train)):
        t = round(float(tp_train[i]), 2)
        if t in early_tps:
            early_train_mask[i] = True
        elif t in late_tps:
            late_train_mask[i] = True

    early_test_mask = np.zeros(len(tp_test), dtype=bool)
    late_test_mask = np.zeros(len(tp_test), dtype=bool)
    for i in range(len(tp_test)):
        t = round(float(tp_test[i]), 2)
        if t in early_tps:
            early_test_mask[i] = True
        elif t in late_tps:
            late_test_mask[i] = True

    logger.info("Specialist split: early=%d train/%d test, late=%d train/%d test",
                early_train_mask.sum(), early_test_mask.sum(),
                late_train_mask.sum(), late_test_mask.sum())

    wf = knobs["walk_forward"]

    def make_splitter(n_b):
        return WalkForwardSplitter(
            n_splits=wf["n_splits"],
            train_period=min(wf["train_bars"], n_b // 2),
            test_period=min(wf["test_bars"], n_b // 10),
            purge_period=wf["purge_period"],
            embargo_period=wf["embargo_period"],
        )

    spec_trials = max(n_trials // 2, 10)
    spec_timeout = max(hpo_timeout // 2, 30)

    # ── HPO for early specialist ──────────────────────────────
    early_study = _run_specialist_hpo(
        X_train[early_train_mask], y_train[early_train_mask],
        train_bar_indices[early_train_mask], tp_train[early_train_mask],
        feature_names_used, make_splitter, ss, device, args.seed,
        spec_trials, spec_timeout, obj_config, "Early",
    )

    # ── HPO for late specialist ───────────────────────────────
    late_study = _run_specialist_hpo(
        X_train[late_train_mask], y_train[late_train_mask],
        train_bar_indices[late_train_mask], tp_train[late_train_mask],
        feature_names_used, make_splitter, ss, device, args.seed + 1,
        spec_trials, spec_timeout, obj_config, "Late",
    )

    # ── Retrain best for each specialist ──────────────────────
    results_parts = {}
    for label, study, tr_mask, te_mask, tp_tr, tp_te in [
        ("early", early_study, early_train_mask, early_test_mask, tp_train, tp_test),
        ("late", late_study, late_train_mask, late_test_mask, tp_train, tp_test),
    ]:
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

        X_tr_sub = X_train[tr_mask]
        y_tr_sub = y_train[tr_mask]
        bi_tr_sub = train_bar_indices[tr_mask]
        tp_tr_sub = tp_tr[tr_mask]

        ds_final = lgb.Dataset(X_tr_sub, y_tr_sub, feature_name=feature_names_used)
        model = lgb.train(final_params, ds_final, num_boost_round=n_est)

        # Walk-forward OOS calibration
        unique_bars = np.unique(bi_tr_sub)
        n_b = len(unique_bars)
        sp = make_splitter(n_b)
        oos_probs = np.zeros(len(y_tr_sub))
        oos_m = np.zeros(len(y_tr_sub), dtype=bool)
        for btr, bte in sp.split(n_b):
            bars_tr = unique_bars[btr]
            bars_te = unique_bars[bte]
            tr_m2 = np.isin(bi_tr_sub, bars_tr)
            te_m2 = np.isin(bi_tr_sub, bars_te)
            if tr_m2.sum() == 0 or te_m2.sum() == 0:
                continue
            ds = lgb.Dataset(X_tr_sub[tr_m2], y_tr_sub[tr_m2])
            m = lgb.train(final_params, ds, num_boost_round=n_est)
            oos_probs[te_m2] = m.predict(X_tr_sub[te_m2])
            oos_m[te_m2] = True

        cal = TimeAwareCalibrator()
        if oos_m.any():
            cal.fit(oos_probs[oos_m], y_tr_sub[oos_m], tp_tr_sub[oos_m])

        # Evaluate on test subset
        X_te_sub = X_test[te_mask]
        y_te_sub = y_test[te_mask]
        raw_preds = model.predict(X_te_sub)
        cal_preds = cal.transform(raw_preds, tp_te[te_mask])

        brier_val = brier_score(cal_preds, y_te_sub)
        acc_val = float(np.mean((cal_preds > 0.5) == (y_te_sub == 1)))

        results_parts[label] = {
            "model": model, "cal": cal, "n_est": n_est,
            "brier": brier_val, "accuracy": acc_val,
            "n_test": len(y_te_sub), "best_params": study.best_params,
            "hpo_objective": study.best_value, "hpo_trials": len(study.trials),
        }
        logger.info("%s specialist: brier=%.6f, acc=%.4f, n_test=%d",
                     label, brier_val, acc_val, len(y_te_sub))

    # ── Combined evaluation (batch predict per specialist) ──────
    all_cal_test = np.full(len(y_test), 0.5)  # fallback for unassigned time_pcts

    for label, te_mask in [("early", early_test_mask), ("late", late_test_mask)]:
        if label not in results_parts or not te_mask.any():
            continue
        part = results_parts[label]
        raw_preds = part["model"].predict(X_test[te_mask])
        cal_preds = part["cal"].transform(raw_preds, tp_test[te_mask])
        all_cal_test[te_mask] = cal_preds

    brier = brier_score(all_cal_test, y_test)
    ece = expected_calibration_error(all_cal_test, y_test)
    acc = float(np.mean((all_cal_test > 0.5) == (y_test == 1)))

    # Backtest combined
    bt = knobs["backtest"]
    backtester = IntraBarBacktester(
        fee_bps=bt["fee_bps"], spread=bt["spread"], min_edge=bt["min_edge"],
        impact_bps=bt.get("impact_bps", 0),
        max_trades_per_bar=bt.get("max_trades_per_bar", 3),
        max_daily_trades=bt.get("max_daily_trades", 100),
        fixed_bet_usd=bt.get("fixed_bet_usd", 50.0), timeframe=tf,
    )
    bt_metrics = backtester.evaluate_fast(all_cal_test, y_test, mp_test, tp_test, bi_test)

    # Save specialist models
    if args.save:
        model_dir = Path(f"data/models/pulse_v2/{args.asset}_{args.timeframe}")
        model_dir.mkdir(parents=True, exist_ok=True)
        if "early" in results_parts:
            results_parts["early"]["model"].save_model(str(model_dir / "model_early.lgb"))
            results_parts["early"]["cal"].save(model_dir / "calibrator_early.pkl")
        if "late" in results_parts:
            results_parts["late"]["model"].save_model(str(model_dir / "model_late.lgb"))
            results_parts["late"]["cal"].save(model_dir / "calibrator_late.pkl")
        (model_dir / "specialist_config.json").write_text(json.dumps({
            "boundary": boundary,
            "early_time_pcts": sorted(early_tps),
            "late_time_pcts": sorted(late_tps),
        }, indent=2))
        logger.info("Specialist models saved to %s", model_dir)

    # Feature importance (use late model as primary)
    fi_model = results_parts.get("late", results_parts.get("early", {})).get("model")
    top_features = []
    if fi_model:
        fi = dict(zip(fi_model.feature_name(),
                      fi_model.feature_importance(importance_type="gain")))
        top_features = sorted(fi.items(), key=lambda x: -x[1])[:10]

    elapsed = time.time() - t0
    return {
        "status": "ok",
        "mode": args.mode,
        "model": "pulse_specialist",
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
        "specialist_boundary": boundary,
        "early_brier": round(results_parts.get("early", {}).get("brier", 0), 6),
        "late_brier": round(results_parts.get("late", {}).get("brier", 0), 6),
        "hpo_objective": round(
            (results_parts.get("early", {}).get("hpo_objective", 0) +
             results_parts.get("late", {}).get("hpo_objective", 0)) / 2, 6),
        "hpo_objective_primary": obj_config.primary,
        "hpo_trials": sum(r.get("hpo_trials", 0) for r in results_parts.values()),
        "oos_accuracy": round(acc, 4),
        "oos_brier": round(brier, 6),
        "oos_ece": round(ece, 4),
        "backtest_pnl": round(bt_metrics.get("total_pnl", 0), 2),
        "backtest_trades": bt_metrics.get("n_trades", 0),
        "backtest_win_rate": round(bt_metrics.get("win_rate", 0), 4),
        "backtest_sharpe": round(bt_metrics.get("sharpe", 0), 2),
        "backtest_max_dd": round(bt_metrics.get("max_dd", 0), 4),
        "backtest_avg_pnl_per_trade": round(bt_metrics.get("avg_pnl_per_trade", 0), 4),
        "backtest_time_buckets": bt_metrics.get("time_buckets", {}),
        "top_features": [f[0] for f in top_features],
        "best_params_early": {k: round(v, 6) if isinstance(v, float) else v
                              for k, v in results_parts.get("early", {}).get("best_params", {}).items()},
        "best_params_late": {k: round(v, 6) if isinstance(v, float) else v
                             for k, v in results_parts.get("late", {}).get("best_params", {}).items()},
    }


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

    # ── Objective config (enriched knobs) ───────────────────────
    obj_cfg_raw = knobs.get("objective", {})
    obj_config = ObjectiveConfig(
        primary=obj_cfg_raw.get("primary", "brier"),
        brier_threshold=obj_cfg_raw.get("brier_threshold", 0.25),
        brier_penalty_weight=obj_cfg_raw.get("brier_penalty_weight", 10.0),
        min_trades=obj_cfg_raw.get("min_trades", 50),
        trade_penalty_weight=obj_cfg_raw.get("trade_penalty_weight", 5.0),
        max_drawdown_threshold=obj_cfg_raw.get("max_drawdown_threshold", 0.30),
        drawdown_penalty_weight=obj_cfg_raw.get("drawdown_penalty_weight", 5.0),
    )
    logger.info(
        "Objective: primary=%s, brier_threshold=%.2f",
        obj_config.primary, obj_config.brier_threshold,
    )

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

    # ── Cross-asset augmentation (non-BTC only) ──────────────────
    dataset = load_and_augment(dataset, args.asset, args.timeframe, knobs)

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
        name = all_names[i]
        if name in CACHED_FEATURES or name.startswith("btc_"):
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

    actual_tps = sorted(set(float(round(t, 6)) for t in time_pcts))
    if len(actual_tps) < len(tp_set):
        unmatched = [
            float(tp) for tp in tp_set
            if not any(np.isclose(tp, a, atol=1e-6) for a in actual_tps)
        ]
        logger.warning(
            "time_pcts MISMATCH: requested %s but only %s exist in dataset. "
            "Unmatched: %s", list(tp_set), actual_tps, unmatched,
        )
    logger.info("After filtering: %d samples, %d features, %d/%d time_pcts matched",
                len(y), len(feature_names_used), len(actual_tps), len(tp_set))

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
    tp_train = time_pcts[train_mask]

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

    # ── Specialist branch (if enabled) ───────────────────────────
    spec_cfg = knobs.get("specialist", {})
    ss = HPO_SEARCH_SPACE

    if spec_cfg.get("enabled", False):
        return _run_specialist_path(
            X_train, y_train, X_test, y_test, mp_test, tp_test, bi_test,
            train_bar_indices, tp_train, train_unique_bars, n_train_bars,
            feature_names_used, spec_cfg, ss, device, args, obj_config,
            n_trials, hpo_timeout, tf, knobs, cfg_hash, t0,
            split_bar_idx, n_bars, base_rate,
        )

    # ── Optuna HPO (single-model path — unchanged) ─────────────

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

        fold_briers = []
        fold_n_trades = []
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
            fold_briers.append(float(np.mean((preds - y_train[te_mask]) ** 2)))
            fold_n_trades.append(int(te_mask.sum()))

        if not fold_briers:
            return 1.0

        # Use configurable objective instead of raw Brier
        avg_metrics = {
            "brier": float(np.mean(fold_briers)),
            "sharpe": 0.0,  # not available in CV folds
            "n_trades": int(np.mean(fold_n_trades)),
            "max_dd": 0.0,
        }
        return compute_objective(avg_metrics, obj_config)

    study = optuna.create_study(direction="minimize",
                                sampler=optuna.samplers.TPESampler(seed=args.seed))
    study.optimize(objective, n_trials=n_trials, n_jobs=1, timeout=hpo_timeout)

    logger.info("Best HPO objective: %.6f (%s-primary, %d/%d trials, %s mode)",
                study.best_value, obj_config.primary, len(study.trials), n_trials, args.mode)

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

    cal = TimeAwareCalibrator()
    cal.fit(oos_probs[oos_mask], y_train[oos_mask], tp_train[oos_mask])

    # ── Save model + calibrator to disk (if --save) ──────────────
    if args.save:
        model_dir = Path(f"data/models/pulse_v2/{args.asset}_{args.timeframe}")
        model_dir.mkdir(parents=True, exist_ok=True)
        model_final.save_model(str(model_dir / "model.lgb"))
        cal.save(model_dir / "calibrator.pkl")
        logger.info("Model + calibrator saved to %s", model_dir)

    # ── Evaluate on test set ──────────────────────────────────────
    raw_test = model_final.predict(X_test)
    cal_test = cal.transform(raw_test, tp_test)

    acc = float(np.mean((cal_test > 0.5) == (y_test == 1)))
    brier = brier_score(cal_test, y_test)
    ece = expected_calibration_error(cal_test, y_test)

    # ── Backtest (maker-only: fee_bps=0, impact_bps=0) ───────────
    # NOTE: Single-side PnL is normalized (fixed_bet_usd / 10,000 per trade).
    # Both-sides PnL is in raw USD (fixed_bet_usd per order).
    # The two are not directly comparable in absolute dollar terms.
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
        "hpo_objective": round(study.best_value, 6),
        "hpo_objective_primary": obj_config.primary,
        "hpo_trials": len(study.trials),
        "oos_accuracy": round(acc, 4),
        "oos_brier": round(brier, 6),
        "oos_ece": round(ece, 4),
        "backtest_pnl": round(bt_metrics.get("total_pnl", 0), 2),
        "backtest_trades": bt_metrics.get("n_trades", 0),
        "backtest_win_rate": round(bt_metrics.get("win_rate", 0), 4),
        "backtest_sharpe": round(bt_metrics.get("sharpe", 0), 2),
        "backtest_max_dd": round(bt_metrics.get("max_dd", 0), 4),
        "backtest_avg_pnl_per_trade": round(bt_metrics.get("avg_pnl_per_trade", 0), 4),
        "backtest_time_buckets": bt_metrics.get("time_buckets", {}),
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
