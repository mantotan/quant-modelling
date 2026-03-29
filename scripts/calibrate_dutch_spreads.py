"""Calibrate max_marginal_pair_cost per pair from actual tick/bar data.

Reads tick data for spread percentiles and bar data for realized pair costs.
Outputs recommended max_mpc values per pair.

Usage:
    uv run scripts/calibrate_dutch_spreads.py
    uv run scripts/calibrate_dutch_spreads.py --since 4h    # recent data only
    uv run scripts/calibrate_dutch_spreads.py --apply        # write recommendations to knobs files
"""

import json
import glob
import os
import sys
from datetime import datetime, timezone, timedelta
from collections import defaultdict


def parse_since(arg: str) -> datetime | None:
    if not arg:
        return None
    if arg[-1] in "hmd":
        unit = arg[-1]
        val = float(arg[:-1])
        delta = {"h": timedelta(hours=val), "m": timedelta(minutes=val), "d": timedelta(days=val)}[unit]
        return datetime.now(timezone.utc) - delta
    if ":" in arg and len(arg) <= 5:
        h, m = arg.split(":")
        now = datetime.now(timezone.utc)
        return now.replace(hour=int(h), minute=int(m), second=0, microsecond=0)
    return datetime.fromisoformat(arg)


def percentile(sorted_vals: list[float], pct: float) -> float:
    if not sorted_vals:
        return 0.0
    k = (len(sorted_vals) - 1) * pct / 100.0
    f = int(k)
    c = f + 1
    if c >= len(sorted_vals):
        return sorted_vals[-1]
    return sorted_vals[f] + (k - f) * (sorted_vals[c] - sorted_vals[f])


def load_spread_data(since: datetime | None = None) -> dict:
    """Load tick data and compute spread distributions per pair."""
    results = {}
    for tick_file in sorted(glob.glob("data/dutch_paper/*/ticks_*.jsonl")):
        pair = os.path.basename(os.path.dirname(tick_file))
        if pair not in results:
            results[pair] = []
        with open(tick_file) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    t = json.loads(line)
                    if since:
                        ts = t.get("ts", "")
                        if isinstance(ts, str) and ts < since.isoformat():
                            continue
                    ask_up = t.get("ask_up", 0)
                    ask_dn = t.get("ask_dn", 0)
                    if ask_up > 0 and ask_dn > 0:
                        results[pair].append(ask_up + ask_dn)
                except Exception:
                    continue
    return results


def load_bar_pair_costs(since: datetime | None = None) -> dict:
    """Load bar data and extract realized pair costs."""
    results = defaultdict(list)
    for bar_file in sorted(glob.glob("data/dutch_paper/*/bars_*.jsonl")):
        pair = os.path.basename(os.path.dirname(bar_file))
        with open(bar_file) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    b = json.loads(line)
                    if since:
                        bar_id = b.get("bar_id", 0)
                        if datetime.fromtimestamp(bar_id, tz=timezone.utc) < since:
                            continue
                    matched = b.get("inventory", {}).get("matched", 0)
                    pc = b.get("cost", {}).get("avg_pair_cost", 0)
                    profit = b.get("pnl", {}).get("profit", 0)
                    cost = b.get("cost", {}).get("total", 0)
                    if matched > 0 and pc > 0:
                        results[pair].append({
                            "pair_cost": pc,
                            "matched": matched,
                            "profit": profit,
                            "cost": cost,
                        })
                except Exception:
                    continue
    return results


def load_current_knobs() -> dict:
    """Load current max_marginal_pair_cost from knobs files."""
    knobs = {}
    for knobs_file in sorted(glob.glob("autoresearch/dutch/knobs_*.json")):
        pair = os.path.basename(knobs_file).replace("knobs_", "").replace(".json", "")
        if pair.startswith("best_"):
            continue
        with open(knobs_file) as f:
            k = json.load(f)
        knobs[pair] = k.get("max_marginal_pair_cost", 1.03)
    return knobs


def recommend_mpc(spreads: list[float], bars: list[dict], current_mpc: float) -> tuple[float, str]:
    """Recommend max_mpc based on spread percentiles and bar profitability.

    Returns (recommended_mpc, reasoning).
    """
    if not spreads:
        return current_mpc, "no tick data"

    sorted_spreads = sorted(spreads)
    p10 = percentile(sorted_spreads, 10)
    p20 = percentile(sorted_spreads, 20)
    p50 = percentile(sorted_spreads, 50)

    # Target: p20 + 0.005 (trade during cheapest ~25% of ticks)
    target = round(p20 + 0.005, 4)

    # Floor: never tighten below 90% of current working value
    floor = round(current_mpc * 0.90, 4)

    # If we have bar data, check what pair cost threshold gives profitability
    if bars:
        profitable_pcs = sorted([b["pair_cost"] for b in bars if b["profit"] > 0])
        losing_pcs = sorted([b["pair_cost"] for b in bars if b["profit"] <= 0])

        if profitable_pcs:
            # The max pair_cost of profitable bars = our empirical ceiling
            max_profitable_pc = profitable_pcs[-1]
            # Weight toward empirical data over spread percentiles
            empirical_target = round(min(max_profitable_pc, 1.02), 4)
            target = round((target + empirical_target) / 2, 4)

    recommended = max(target, floor)

    # Round to nearest 0.005
    recommended = round(round(recommended / 0.005) * 0.005, 3)

    # Clamp to reasonable range
    recommended = max(1.005, min(1.06, recommended))

    reason = f"p20={p20:.4f} target={target:.4f} floor={floor:.4f}"
    return recommended, reason


def main():
    since = None
    apply_mode = "--apply" in sys.argv
    if "--since" in sys.argv:
        idx = sys.argv.index("--since")
        if idx + 1 < len(sys.argv):
            since = parse_since(sys.argv[idx + 1])

    print("Loading tick data...")
    spread_data = load_spread_data(since)
    print("Loading bar data...")
    bar_data = load_bar_pair_costs(since)
    current_knobs = load_current_knobs()

    if since:
        print(f"\nDutch Spread Calibration (since {since.strftime('%Y-%m-%d %H:%M UTC')})")
    else:
        print("\nDutch Spread Calibration (all data)")
    print("=" * 100)

    # Group by timeframe
    recommendations = {}
    for tf in ["5m", "15m", "1h"]:
        pairs = sorted([p for p in set(list(spread_data.keys()) + list(bar_data.keys())) if p.endswith(tf)])
        if not pairs:
            continue

        print(f"\n{'Pair':<12} {'Ticks':>7} {'p10':>7} {'p20':>7} {'p50':>7} {'Bars':>5} {'AvgPC':>7} {'PC<1':>5} {'Cur':>6} {'Rec':>6} {'Action':<20}")
        print("-" * 100)

        for pair in pairs:
            spreads = spread_data.get(pair, [])
            bars = bar_data.get(pair, [])
            current = current_knobs.get(pair, 1.03)

            sorted_spreads = sorted(spreads) if spreads else []
            p10 = percentile(sorted_spreads, 10)
            p20 = percentile(sorted_spreads, 20)
            p50 = percentile(sorted_spreads, 50)

            avg_pc = sum(b["pair_cost"] for b in bars) / len(bars) if bars else 0
            pc_below_1 = sum(1 for b in bars if b["pair_cost"] < 1.0)

            rec, reason = recommend_mpc(spreads, bars, current)
            recommendations[pair] = rec

            if rec < current - 0.001:
                action = f"TIGHTEN {current:.3f}->{rec:.3f}"
            elif rec > current + 0.001:
                action = f"LOOSEN  {current:.3f}->{rec:.3f}"
            else:
                action = "KEEP"

            print(
                f"{pair:<12} {len(spreads):>7} {p10:>7.4f} {p20:>7.4f} {p50:>7.4f} "
                f"{len(bars):>5} {avg_pc:>7.4f} {pc_below_1:>3}/{len(bars):<3} "
                f"{current:>5.3f} {rec:>5.3f}  {action}"
            )

    # Profit summary
    print("\n" + "=" * 100)
    print("PROFIT IMPACT ESTIMATE")
    print("-" * 100)
    for tf in ["5m", "15m", "1h"]:
        pairs = sorted([p for p in bar_data.keys() if p.endswith(tf)])
        for pair in pairs:
            bars = bar_data[pair]
            rec = recommendations.get(pair, current_knobs.get(pair, 1.03))
            # Simulate: what if we only kept bars where pair_cost <= rec?
            kept = [b for b in bars if b["pair_cost"] <= rec]
            dropped = [b for b in bars if b["pair_cost"] > rec]
            kept_pnl = sum(b["profit"] for b in kept)
            dropped_pnl = sum(b["profit"] for b in dropped)
            total_pnl = sum(b["profit"] for b in bars)
            if dropped:
                print(
                    f"  {pair:<12} current PnL=${total_pnl:>8.2f} | "
                    f"at {rec:.3f}: keep {len(kept)}/{len(bars)} bars, "
                    f"PnL=${kept_pnl:>8.2f}, "
                    f"saved=${-dropped_pnl:>7.2f} by filtering {len(dropped)} expensive bars"
                )

    if apply_mode:
        print("\n" + "=" * 100)
        print("APPLYING RECOMMENDATIONS")
        for pair, rec in sorted(recommendations.items()):
            knobs_file = f"autoresearch/dutch/knobs_{pair}.json"
            if not os.path.exists(knobs_file):
                continue
            current = current_knobs.get(pair, 1.03)
            if abs(rec - current) < 0.001:
                continue
            with open(knobs_file) as f:
                k = json.load(f)
            k["max_marginal_pair_cost"] = rec
            with open(knobs_file, "w") as f:
                json.dump(k, f, indent=2)
                f.write("\n")
            print(f"  {pair}: {current:.3f} -> {rec:.3f}")
        print("\nDone. Restart PM2 to apply: pm2 restart dutch-BTC dutch-ETH dutch-SOL dutch-XRP")
    else:
        print("\nRun with --apply to write recommendations to knobs files.")


if __name__ == "__main__":
    main()
