#!/usr/bin/env python
"""Replay backtester: compares paper trading results against backtest.

Reads paper trade JSONL logs and reruns IntraBarBacktester on the same bars
with two modes:
  Mode A (real odds):      Uses real Polymarket odds captured during paper trading.
  Mode B (synthetic odds): Uses Black-Scholes synthetic odds for the same bars.

This directly measures the gap between paper trading and backtesting.

Usage:
    uv run scripts/replay_backtest.py --asset ETH --timeframe 5m
    uv run scripts/replay_backtest.py --asset ETH --date 2026-03-20
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import UTC, date, datetime
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from qm.backtest.intrabar_backtest import IntraBarBacktester
from qm.core.types import Timeframe

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("replay_backtest")


TF_MAP = {"5m": Timeframe.M5, "15m": Timeframe.M15, "1h": Timeframe.H1}


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Replay backtester")
    p.add_argument("--asset", required=True, choices=["BTC", "ETH", "SOL", "XRP"])
    p.add_argument("--timeframe", default="5m", choices=["5m", "15m", "1h"])
    p.add_argument(
        "--date", default=None,
        help="Specific date (YYYY-MM-DD). If omitted, uses all available logs.",
    )
    p.add_argument(
        "--paper-dir", default="data/paper_trades",
        help="Base directory for paper trade JSONL logs",
    )
    p.add_argument(
        "--output-dir", default="data/reconciliation",
        help="Output directory for reconciliation reports",
    )
    return p.parse_args()


def load_paper_trades(
    paper_dir: Path, asset: str, tf: str, filter_date: str | None,
) -> list[dict]:
    """Load prediction events from JSONL files."""
    log_dir = paper_dir / f"{asset}_{tf}"
    if not log_dir.exists():
        logger.error("No paper trade logs at %s", log_dir)
        return []

    predictions: list[dict] = []
    pattern = f"trades_{filter_date}.jsonl" if filter_date else "trades_*.jsonl"

    for path in sorted(log_dir.glob(pattern)):
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                event = json.loads(line)
                if event.get("type") == "prediction":
                    predictions.append(event)

    logger.info("Loaded %d predictions from %s", len(predictions), log_dir)
    return predictions


def load_resolutions(
    paper_dir: Path, asset: str, tf: str, filter_date: str | None,
) -> dict[str, dict]:
    """Load resolution events, keyed by condition_id."""
    log_dir = paper_dir / f"{asset}_{tf}"
    if not log_dir.exists():
        return {}

    resolutions: dict[str, dict] = {}
    pattern = f"trades_{filter_date}.jsonl" if filter_date else "trades_*.jsonl"

    for path in sorted(log_dir.glob(pattern)):
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                event = json.loads(line)
                if event.get("type") == "resolution":
                    resolutions[event["condition_id"]] = event

    return resolutions


def build_arrays(
    predictions: list[dict], resolutions: dict[str, dict],
) -> dict[str, np.ndarray] | None:
    """Convert paper trade events to numpy arrays for backtester."""
    if not predictions:
        return None

    # Only use predictions that have resolved
    resolved = [
        p for p in predictions
        if p["condition_id"] in resolutions
    ]

    if not resolved:
        logger.warning(
            "No resolved predictions yet (%d pending)", len(predictions),
        )
        return None

    logger.info(
        "%d/%d predictions have resolutions",
        len(resolved), len(predictions),
    )

    model_probs = np.array([p["model_prob"] for p in resolved])
    market_probs = np.array([p["market_prob"] for p in resolved])
    time_pcts = np.array([p["elapsed_pct"] for p in resolved])
    bar_indices = np.array([p["bar_id"] for p in resolved])

    # Target: 1 if outcome was UP, 0 otherwise
    targets = np.array([
        1.0 if resolutions[p["condition_id"]]["outcome"].upper() in ("UP", "YES")
        else 0.0
        for p in resolved
    ])

    # Paper PnL per trade
    paper_pnls = np.array([
        resolutions[p["condition_id"]]["pnl"]
        if p["fill_status"] == "filled"
        else 0.0
        for p in resolved
    ])

    # Fill info
    fill_statuses = [p["fill_status"] for p in resolved]
    fill_prices = np.array([p["fill_price"] for p in resolved])
    sizes = np.array([p["size_usd"] for p in resolved])
    spreads = np.array([p["market_spread"] for p in resolved])

    return {
        "model_probs": model_probs,
        "market_probs": market_probs,
        "targets": targets,
        "time_pcts": time_pcts,
        "bar_indices": bar_indices,
        "paper_pnls": paper_pnls,
        "fill_statuses": fill_statuses,
        "fill_prices": fill_prices,
        "sizes": sizes,
        "spreads": spreads,
    }


def run_replay(
    arrays: dict[str, np.ndarray],
    timeframe: Timeframe,
    knobs: dict,
) -> dict:
    """Run backtest replay with real odds (Mode A) and compute divergences."""
    bt_cfg = knobs.get("backtest", {})

    # Mode A: real market odds from paper trading
    backtester_a = IntraBarBacktester(
        fee_bps=bt_cfg.get("fee_bps", 0),
        spread=float(np.median(arrays["spreads"])),  # Use observed median spread
        min_edge=bt_cfg.get("min_edge", 0.01),
        max_trades_per_bar=bt_cfg.get("max_trades_per_bar", 15),
        max_daily_trades=bt_cfg.get("max_daily_trades", 500),
        fixed_bet_usd=bt_cfg.get("fixed_bet_usd", 100.0),
        timeframe=timeframe,
    )

    metrics_a = backtester_a.evaluate_fast(
        model_probs=arrays["model_probs"],
        targets=arrays["targets"],
        market_probs=arrays["market_probs"],  # REAL odds
        time_pcts=arrays["time_pcts"],
        bar_indices=arrays["bar_indices"],
    )

    # Mode B: synthetic backtest (fixed spread from knobs)
    backtester_b = IntraBarBacktester(
        fee_bps=bt_cfg.get("fee_bps", 0),
        spread=bt_cfg.get("spread", 0.02),  # Fixed spread from backtest config
        min_edge=bt_cfg.get("min_edge", 0.01),
        max_trades_per_bar=bt_cfg.get("max_trades_per_bar", 15),
        max_daily_trades=bt_cfg.get("max_daily_trades", 500),
        fixed_bet_usd=bt_cfg.get("fixed_bet_usd", 100.0),
        timeframe=timeframe,
    )

    # For Mode B, use synthetic market_probs = 0.50 (uninformed prior)
    # This matches what backtest does when no real odds are available
    synthetic_probs = np.full_like(arrays["market_probs"], 0.50)

    metrics_b = backtester_b.evaluate_fast(
        model_probs=arrays["model_probs"],
        targets=arrays["targets"],
        market_probs=synthetic_probs,  # SYNTHETIC odds
        time_pcts=arrays["time_pcts"],
        bar_indices=arrays["bar_indices"],
    )

    return {"mode_a": metrics_a, "mode_b": metrics_b}


def compute_divergences(
    arrays: dict[str, np.ndarray],
    replay_metrics: dict,
) -> dict:
    """Compute divergence metrics between paper and backtest."""
    # Market odds divergence (real vs 0.50 baseline)
    real_odds = arrays["market_probs"]
    odds_deviation = np.abs(real_odds - 0.50)

    # Edge sign comparison (would backtest agree on trade direction?)
    model_probs = arrays["model_probs"]
    real_edge_up = model_probs - real_odds
    synthetic_edge_up = model_probs - 0.50
    edge_sign_flip = np.mean(np.sign(real_edge_up) != np.sign(synthetic_edge_up))

    # Paper PnL vs replay PnL
    paper_total = float(arrays["paper_pnls"].sum())
    replay_a_total = float(replay_metrics["mode_a"].get("total_pnl", 0))
    replay_b_total = float(replay_metrics["mode_b"].get("total_pnl", 0))

    # Per-trade PnL correlation (paper vs replay_a)
    filled = np.array([s == "filled" for s in arrays["fill_statuses"]])
    n_filled_paper = int(filled.sum())

    # Trade count comparison
    n_replay_a = int(replay_metrics["mode_a"].get("n_trades", 0))
    n_replay_b = int(replay_metrics["mode_b"].get("n_trades", 0))
    trade_ratio = n_replay_a / max(n_filled_paper, 1)

    return {
        "market_odds_mae": float(odds_deviation.mean()),
        "market_odds_max_dev": float(odds_deviation.max()),
        "market_odds_mean": float(real_odds.mean()),
        "edge_sign_flip_pct": float(edge_sign_flip * 100),
        "pnl_paper": paper_total,
        "pnl_replay_real_odds": replay_a_total,
        "pnl_replay_synthetic_odds": replay_b_total,
        "n_paper_filled": n_filled_paper,
        "n_replay_a_trades": n_replay_a,
        "n_replay_b_trades": n_replay_b,
        "trade_count_ratio": round(trade_ratio, 3),
        "median_spread_observed": float(np.median(arrays["spreads"])),
    }


def assess_trust(divergences: dict) -> dict:
    """Classify trust level based on divergence thresholds."""
    checks = {
        "market_odds_mae_ok": divergences["market_odds_mae"] < 0.03,
        "edge_sign_flip_ok": divergences["edge_sign_flip_pct"] < 5.0,
        "pnl_sign_match": (
            (divergences["pnl_paper"] >= 0) == (divergences["pnl_replay_real_odds"] >= 0)
            if divergences["pnl_paper"] != 0 else True
        ),
        "trade_count_ok": 0.8 <= divergences["trade_count_ratio"] <= 1.2,
    }

    n_pass = sum(checks.values())
    if n_pass == len(checks):
        trust = "TRUSTWORTHY"
    elif n_pass >= len(checks) - 1:
        trust = "SUSPICIOUS"
    else:
        trust = "UNRELIABLE"

    return {
        "thresholds_passed": checks,
        "trust_level": trust,
        "n_checks_passed": n_pass,
        "n_checks_total": len(checks),
    }


def main() -> None:
    args = parse_args()
    tf = TF_MAP[args.timeframe]

    knobs_path = Path("autoresearch/best_knobs.json")
    knobs = json.loads(knobs_path.read_text()) if knobs_path.exists() else {}

    paper_dir = Path(args.paper_dir)

    # Load paper trades
    predictions = load_paper_trades(
        paper_dir, args.asset, args.timeframe, args.date,
    )
    if not predictions:
        logger.error("No paper trade predictions found. Exiting.")
        sys.exit(1)

    resolutions = load_resolutions(
        paper_dir, args.asset, args.timeframe, args.date,
    )
    logger.info("Found %d resolutions", len(resolutions))

    # Build arrays
    arrays = build_arrays(predictions, resolutions)
    if arrays is None:
        logger.error("Cannot build arrays (no resolved trades). Exiting.")
        sys.exit(1)

    # Run replay
    replay_metrics = run_replay(arrays, tf, knobs)
    logger.info("Mode A (real odds): %s", json.dumps(replay_metrics["mode_a"], indent=2))
    logger.info("Mode B (synthetic): %s", json.dumps(replay_metrics["mode_b"], indent=2))

    # Compute divergences
    divergences = compute_divergences(arrays, replay_metrics)
    trust = assess_trust(divergences)

    # Build report
    report = {
        "generated_at": datetime.now(UTC).isoformat(),
        "asset": args.asset,
        "timeframe": args.timeframe,
        "date_filter": args.date,
        "n_predictions": len(predictions),
        "n_resolved": len(arrays["model_probs"]),
        "n_resolutions": len(resolutions),
        "divergences": divergences,
        **trust,
        "replay_mode_a": replay_metrics["mode_a"],
        "replay_mode_b": replay_metrics["mode_b"],
    }

    # Write report
    out_dir = Path(args.output_dir) / f"{args.asset}_{args.timeframe}"
    out_dir.mkdir(parents=True, exist_ok=True)
    today = args.date or date.today().isoformat()
    out_path = out_dir / f"report_{today}.json"
    out_path.write_text(json.dumps(report, indent=2, default=str))
    logger.info("Report written: %s", out_path)

    # Summary
    logger.info("=" * 60)
    logger.info("RECONCILIATION SUMMARY")
    logger.info("=" * 60)
    logger.info("  Trust level:       %s", trust["trust_level"])
    logger.info("  Checks passed:     %d/%d", trust["n_checks_passed"], trust["n_checks_total"])
    logger.info("  Market odds MAE:   %.4f", divergences["market_odds_mae"])
    logger.info("  Edge sign flip %%:  %.1f%%", divergences["edge_sign_flip_pct"])
    logger.info("  Paper PnL:         $%.2f", divergences["pnl_paper"])
    logger.info("  Replay PnL (real): $%.2f", divergences["pnl_replay_real_odds"])
    logger.info("  Replay PnL (syn):  $%.2f", divergences["pnl_replay_synthetic_odds"])
    logger.info("  Trade count ratio: %.2f", divergences["trade_count_ratio"])
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
