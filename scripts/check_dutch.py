"""Quick Dutch paper trading PnL dashboard.

Usage:
    uv run scripts/check_dutch.py              # all data
    uv run scripts/check_dutch.py --since 2h   # last 2 hours only
    uv run scripts/check_dutch.py --since 10:00 # since 10:00 UTC today
"""

import json
import glob
import os
import sys
from datetime import datetime, timezone, timedelta
from collections import defaultdict


def parse_since(arg: str) -> datetime:
    """Parse --since argument into a UTC datetime."""
    # Relative: 2h, 30m, 1d
    if arg[-1] in "hmd":
        unit = arg[-1]
        val = float(arg[:-1])
        delta = {"h": timedelta(hours=val), "m": timedelta(minutes=val), "d": timedelta(days=val)}[unit]
        return datetime.now(timezone.utc) - delta
    # Absolute HH:MM (today UTC)
    if ":" in arg and len(arg) <= 5:
        h, m = arg.split(":")
        now = datetime.now(timezone.utc)
        return now.replace(hour=int(h), minute=int(m), second=0, microsecond=0)
    # ISO timestamp
    return datetime.fromisoformat(arg)


def load_bars(since: datetime | None = None):
    """Load all bar JSONL files, optionally filtering by timestamp."""
    results = defaultdict(lambda: {
        "bars": 0, "profit": 0.0, "matched": 0.0, "cost": 0.0,
        "matched_profit": 0.0, "unmatched_payout": 0.0,
        "orders_up": 0, "orders_dn": 0,
        "bars_with_outcome": 0, "correct_side": 0,
    })

    for bar_file in sorted(glob.glob("data/dutch_paper/*/bars_*.jsonl")):
        pair = os.path.basename(os.path.dirname(bar_file))
        with open(bar_file) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    bar = json.loads(line)
                except Exception:
                    continue

                # Filter by timestamp if requested
                if since:
                    ts = bar.get("ts", bar.get("bar_start", ""))
                    bar_id = bar.get("bar_id", 0)
                    if isinstance(ts, str) and ts:
                        if ts < since.isoformat():
                            continue
                    elif bar_id:
                        if datetime.fromtimestamp(bar_id, tz=timezone.utc) < since:
                            continue

                r = results[pair]
                r["bars"] += 1
                pnl = bar.get("pnl", {})
                cost = bar.get("cost", {})
                inv = bar.get("inventory", {})

                r["profit"] += pnl.get("profit", 0)
                r["matched_profit"] += pnl.get("matched_profit", 0)
                r["unmatched_payout"] += pnl.get("unmatched_payout", 0)
                r["matched"] += inv.get("matched", 0)
                r["cost"] += cost.get("total", 0)

    return results


def load_events_since(since: datetime):
    """Load post-cutoff events and count gate types per pair."""
    gate_counts = defaultdict(lambda: defaultdict(int))
    order_sides = defaultdict(lambda: {"UP": 0, "DN": 0})

    for evt_file in sorted(glob.glob("data/dutch_paper/*/events_*.jsonl")):
        pair = os.path.basename(os.path.dirname(evt_file))
        with open(evt_file) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    e = json.loads(line)
                except Exception:
                    continue
                ts = e.get("ts", "")
                if isinstance(ts, str) and ts < since.isoformat():
                    continue
                t = e.get("type", "")
                if t.startswith("gate_"):
                    gate_counts[pair][t] += 1
                elif t in ("order", "fill"):
                    side = e.get("side", "")
                    if side in ("UP", "DN"):
                        order_sides[pair][side] += 1

    return gate_counts, order_sides


def main():
    since = None
    if "--since" in sys.argv:
        idx = sys.argv.index("--since")
        if idx + 1 < len(sys.argv):
            since = parse_since(sys.argv[idx + 1])

    results = load_bars(since)

    if not results:
        print("No bar data found.")
        return

    # Header
    if since:
        print(f"Dutch Paper Trading PnL (since {since.strftime('%Y-%m-%d %H:%M UTC')})")
    else:
        print("Dutch Paper Trading PnL (all data)")
    print("=" * 80)

    # Group by timeframe
    for tf in ["5m", "15m", "1h"]:
        pairs = sorted([p for p in results if p.endswith(tf)])
        if not pairs:
            continue

        print(f"\n{'Pair':<12} {'Bars':>5} {'Matched':>8} {'PnL':>9} {'Cost':>8} {'BudUtil':>8} {'PnL/Bar':>8}")
        print("-" * 65)

        tf_pnl = 0
        tf_cost = 0
        tf_bars = 0
        for pair in pairs:
            r = results[pair]
            bu = (r["cost"] / (r["bars"] * 200) * 100) if r["bars"] > 0 else 0
            pnl_bar = r["profit"] / r["bars"] if r["bars"] > 0 else 0
            sign = "+" if r["profit"] >= 0 else ""
            print(
                f"{pair:<12} {r['bars']:>5} {r['matched']:>8.1f} "
                f"{sign}${r['profit']:>7.2f} ${r['cost']:>7.1f} {bu:>6.1f}% "
                f"{sign}${pnl_bar:>6.2f}"
            )
            tf_pnl += r["profit"]
            tf_cost += r["cost"]
            tf_bars += r["bars"]

        sign = "+" if tf_pnl >= 0 else ""
        print(f"  {tf} total:  {tf_bars:>5} {'':>8} {sign}${tf_pnl:>7.2f} ${tf_cost:>7.1f}")

    # Grand total
    grand_pnl = sum(r["profit"] for r in results.values())
    grand_cost = sum(r["cost"] for r in results.values())
    grand_bars = sum(r["bars"] for r in results.values())
    grand_matched = sum(r["matched"] for r in results.values())
    sign = "+" if grand_pnl >= 0 else ""
    print("\n" + "=" * 65)
    print(f"  TOTAL      {grand_bars:>5} {grand_matched:>8.1f} {sign}${grand_pnl:>7.2f} ${grand_cost:>7.1f}")

    # Gate summary (last 2h or since cutoff)
    gate_since = since or (datetime.now(timezone.utc) - timedelta(hours=2))
    gate_counts, order_sides = load_events_since(gate_since)

    if gate_counts:
        print(f"\nGate events (since {gate_since.strftime('%H:%M UTC')}):")
        print("-" * 65)
        # Collect all gate types
        all_gates = set()
        for gc in gate_counts.values():
            all_gates.update(gc.keys())
        all_gates = sorted(all_gates)

        header = f"{'Pair':<12}" + "".join(f"{g.replace('gate_', ''):>14}" for g in all_gates)
        print(header)
        for pair in sorted(gate_counts.keys()):
            row = f"{pair:<12}"
            for g in all_gates:
                cnt = gate_counts[pair].get(g, 0)
                row += f"{cnt:>14}"
            # Add order sides
            os_info = order_sides.get(pair, {})
            row += f"   orders: UP={os_info.get('UP', 0)} DN={os_info.get('DN', 0)}"
            print(row)


if __name__ == "__main__":
    main()
