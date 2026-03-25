"""Dutch autoresearch validation: spread stress test.

Reruns the Dutch backtest at multiple spread levels (0.01, 0.015, 0.02, 0.03)
to find where profitability breaks for each pair.

Read-only diagnostic — does NOT modify any best_knobs, models, or state files.
Uses temp files for overridden knobs, cleaned up after each run.
"""

from __future__ import annotations

import json
import logging
import shutil
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

# Import run_backtest directly
from dutch_backtest import run_backtest  # noqa: E402

logger = logging.getLogger(__name__)

ASSETS = ["BTC", "ETH", "SOL", "XRP"]
TIMEFRAMES = ["5m", "15m", "1h"]
SPREAD_LEVELS = [0.01, 0.015, 0.02, 0.03]

KNOBS_DIR = Path("autoresearch/dutch")
TICKS_DIR = Path("data/raw/polymarket_ticks")
MODEL_DIR = Path("data/models/pulse_v2")


def load_pair_knobs(asset: str, tf: str) -> dict | None:
    """Load best_knobs for a pair, return None if not found."""
    path = KNOBS_DIR / f"best_knobs_{asset}_{tf}.json"
    if not path.exists():
        return None
    with open(path) as f:
        return json.load(f)


def run_with_spread(asset: str, tf: str, knobs: dict, spread: float) -> dict:
    """Run backtest with overridden spread_offset values."""
    # Deep copy and override spreads
    modified = json.loads(json.dumps(knobs))
    modified["spread_offset"] = spread
    if "fill_simulator" in modified:
        modified["fill_simulator"]["spread_offset"] = spread

    # Write to temp dir as per-pair knobs file
    tmp_dir = Path(tempfile.mkdtemp(prefix="dutch_spread_"))
    try:
        knobs_file = tmp_dir / f"best_knobs_{asset}_{tf}.json"
        with open(knobs_file, "w") as f:
            json.dump(modified, f, indent=2)

        # Also write a fallback knobs.json (required by load_dutch_config)
        fallback = tmp_dir / "knobs.json"
        with open(fallback, "w") as f:
            json.dump(modified, f, indent=2)

        metrics = run_backtest(
            asset=asset,
            tf_label=tf,
            knobs_dir=tmp_dir,
            knobs_fallback=fallback,
            ticks_dir=TICKS_DIR,
            model_dir=MODEL_DIR,
            inference_interval=1.0,
            save_bars=False,
            verbose=False,
            filter_date=None,
        )
        return metrics
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def main() -> None:
    logging.basicConfig(
        level=logging.WARNING,  # Suppress INFO noise from 48 backtests
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    # Collect results: {pair: {spread: metrics}}
    results: dict[str, dict[float, dict]] = {}
    total_runs = 0
    t0 = time.time()

    for asset in ASSETS:
        for tf in TIMEFRAMES:
            pair = f"{asset}_{tf}"
            knobs = load_pair_knobs(asset, tf)
            if knobs is None:
                print(f"  SKIP {pair}: no best_knobs found")
                continue

            results[pair] = {}
            for spread in SPREAD_LEVELS:
                total_runs += 1
                print(f"  [{total_runs}/48] {pair} spread={spread:.3f} ...", end="", flush=True)
                metrics = run_with_spread(asset, tf, knobs, spread)

                if metrics.get("bars_evaluated", 0) == 0:
                    print(" NO DATA")
                    results[pair][spread] = {"avg_profit": float("nan"), "avg_pair_cost": float("nan")}
                    continue

                results[pair][spread] = metrics
                profit = metrics.get("avg_profit", 0)
                pc = metrics.get("avg_pair_cost", 0)
                print(f" profit=${profit:+.3f}/bar  pair_cost={pc:.4f}")

    elapsed = time.time() - t0

    # Print summary tables
    print()
    print("=" * 100)
    print("DUTCH SPREAD STRESS TEST")
    print(f"({total_runs} backtests in {elapsed:.0f}s)")
    print("=" * 100)

    # Table 1: avg_profit across spreads
    print()
    print("AVG PROFIT ($/bar) by spread level:")
    spread_headers = "  ".join(f"spread={s:.3f}" for s in SPREAD_LEVELS)
    print(f"{'Pair':<12}  {spread_headers}")
    print("-" * 80)

    profitable_at_spread: dict[float, int] = {s: 0 for s in SPREAD_LEVELS}

    for pair in sorted(results.keys()):
        cells = []
        for spread in SPREAD_LEVELS:
            m = results[pair].get(spread, {})
            profit = m.get("avg_profit", float("nan"))
            if profit != profit:  # NaN check
                cells.append(f"{'N/A':>12}")
            else:
                marker = " " if profit >= 0 else ""
                cells.append(f"${profit:>+9.3f}{marker}")
                if profit > 0:
                    profitable_at_spread[spread] += 1
        print(f"{pair:<12}  {'  '.join(cells)}")

    print("-" * 80)
    counts = "  ".join(f"{profitable_at_spread[s]:>12}" for s in SPREAD_LEVELS)
    print(f"{'Profitable':<12}  {counts}")

    # Table 2: pair_cost across spreads
    print()
    print("PAIR COST by spread level:")
    print(f"{'Pair':<12}  {spread_headers}")
    print("-" * 80)

    for pair in sorted(results.keys()):
        cells = []
        for spread in SPREAD_LEVELS:
            m = results[pair].get(spread, {})
            pc = m.get("avg_pair_cost", float("nan"))
            if pc != pc:  # NaN check
                cells.append(f"{'N/A':>12}")
            else:
                cells.append(f"{pc:>12.4f}")
        print(f"{pair:<12}  {'  '.join(cells)}")

    # Table 3: max_dd across spreads
    print()
    print("MAX DRAWDOWN (%) by spread level:")
    print(f"{'Pair':<12}  {spread_headers}")
    print("-" * 80)

    for pair in sorted(results.keys()):
        cells = []
        for spread in SPREAD_LEVELS:
            m = results[pair].get(spread, {})
            dd = m.get("max_dd_pct", float("nan"))
            if dd != dd:  # NaN check
                cells.append(f"{'N/A':>12}")
            else:
                cells.append(f"{dd:>11.1f}%")
        print(f"{pair:<12}  {'  '.join(cells)}")

    # Final verdict
    print()
    print("=" * 80)
    print("VERDICT")
    print("=" * 80)
    for spread in SPREAD_LEVELS:
        n = profitable_at_spread[spread]
        print(f"  spread={spread:.3f}: {n}/12 pairs profitable")

    target_spread = 0.02
    n_at_target = profitable_at_spread[target_spread]
    if n_at_target >= 3:
        print(f"\nAt spread={target_spread}: {n_at_target} pairs profitable — VIABLE for deployment")
    else:
        print(f"\nAt spread={target_spread}: only {n_at_target} pairs profitable — NOT VIABLE, need methodology fixes")


if __name__ == "__main__":
    main()
