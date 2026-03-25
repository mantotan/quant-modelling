#!/usr/bin/env python
"""Analyze WHY matching stays low even when pair cost is good (Exp6).

Key question: bars have good pair_cost (0.87) but 55% of shares are unmatched.
Where is the money actually going?
"""
import json
import sys
from collections import Counter

BARS_FILE = sys.argv[1] if len(sys.argv) > 1 else "data/dutch_backtest/BTC_15m/bars_2026-03-22.jsonl"
EVENTS_FILE = sys.argv[2] if len(sys.argv) > 2 else "data/dutch_backtest/BTC_15m/events_2026-03-22.jsonl"

bars = []
with open(BARS_FILE) as f:
    for line in f:
        bars.append(json.loads(line))

events = []
with open(EVENTS_FILE) as f:
    for line in f:
        events.append(json.loads(line))

print(f"=== MATCHING ANALYSIS: {len(bars)} bars ===\n")

# 1. Per-bar: how many fills per side? Is matching failing because one side gets 0 fills?
print("--- Q1: BARS BY FILL PATTERN ---")
patterns = Counter()
one_sided_bars = []
for b in bars:
    buy_orders = [o for o in b["orders"] if "sell" not in o.get("reason", "").lower()]
    up_buys = [o for o in buy_orders if o["side"] == "UP"]
    dn_buys = [o for o in buy_orders if o["side"] == "DN"]

    if len(up_buys) == 0 and len(dn_buys) == 0:
        patterns["ZERO fills"] += 1
    elif len(up_buys) == 0:
        patterns["DN only (no UP)"] += 1
        one_sided_bars.append(b)
    elif len(dn_buys) == 0:
        patterns["UP only (no DN)"] += 1
        one_sided_bars.append(b)
    else:
        patterns["BOTH sides"] += 1

for k, v in patterns.most_common():
    print(f"  {k}: {v} ({100*v/len(bars):.1f}%)")

one_sided_pnl = sum(b["pnl"]["profit"] for b in one_sided_bars)
both_sided = [b for b in bars if b not in one_sided_bars]
both_pnl = sum(b["pnl"]["profit"] for b in both_sided)
print(f"\n  One-sided bars P&L: ${one_sided_pnl:.2f} ({len(one_sided_bars)} bars)")
print(f"  Both-sided bars P&L: ${both_pnl:.2f} ({len(both_sided)} bars)")
print()

# 2. For one-sided bars: what side did they fill, and what was the outcome?
print("--- Q2: ONE-SIDED BARS — WHICH SIDE, WHAT OUTCOME ---")
for pattern_name in ["UP only (no DN)", "DN only (no UP)"]:
    these = [b for b in bars
             if sum(1 for o in b["orders"] if o["side"] == "UP" and "sell" not in o.get("reason", "").lower()) > 0
             and sum(1 for o in b["orders"] if o["side"] == "DN" and "sell" not in o.get("reason", "").lower()) == 0]
    if pattern_name == "DN only (no UP)":
        these = [b for b in bars
                 if sum(1 for o in b["orders"] if o["side"] == "DN" and "sell" not in o.get("reason", "").lower()) > 0
                 and sum(1 for o in b["orders"] if o["side"] == "UP" and "sell" not in o.get("reason", "").lower()) == 0]

    if these:
        outcomes = Counter(b["outcome"] for b in these)
        pnl = sum(b["pnl"]["profit"] for b in these)
        print(f"  {pattern_name}: {len(these)} bars, outcomes={dict(outcomes)}, total P&L=${pnl:.2f}")
print()

# 3. For bars with BOTH sides: what causes unmatched shares?
print("--- Q3: BOTH-SIDED BARS — IMBALANCE ANALYSIS ---")
both_bars = [b for b in bars
             if sum(1 for o in b["orders"] if o["side"] == "UP" and "sell" not in o.get("reason", "").lower()) > 0
             and sum(1 for o in b["orders"] if o["side"] == "DN" and "sell" not in o.get("reason", "").lower()) > 0]

if both_bars:
    imbalances = []
    for b in both_bars:
        up_shares = b["inventory"]["up_shares"]
        dn_shares = b["inventory"]["dn_shares"]
        matched = b["inventory"]["matched"]
        total = up_shares + dn_shares
        match_pct = matched / max(up_shares, dn_shares, 0.01)
        imbalance = abs(up_shares - dn_shares) / max(total, 0.01)
        heavier = "UP" if up_shares > dn_shares else "DN"
        imbalances.append((imbalance, match_pct, heavier, b))

    avg_imbal = sum(i[0] for i in imbalances) / len(imbalances)
    avg_match = sum(i[1] for i in imbalances) / len(imbalances)
    heavier_counts = Counter(i[2] for i in imbalances)
    print(f"  Both-sided bars: {len(both_bars)}")
    print(f"  Avg imbalance (|UP-DN|/total): {avg_imbal:.3f}")
    print(f"  Avg match rate: {avg_match:.1%}")
    print(f"  Heavier side: {dict(heavier_counts)}")
    print()

    # Bucket by match quality
    print("  Match rate buckets:")
    for lo, hi, label in [(0.9, 1.01, "90-100%"), (0.7, 0.9, "70-90%"), (0.5, 0.7, "50-70%"), (0.3, 0.5, "30-50%"), (0, 0.3, "0-30%")]:
        n = sum(1 for _, m, _, _ in imbalances if lo <= m < hi)
        pnl = sum(b["pnl"]["profit"] for _, m, _, b in imbalances if lo <= m < hi)
        print(f"    {label}: {n} bars, P&L ${pnl:.2f}")
print()

# 4. Gate analysis: WHY can't we fill the other side?
print("--- Q4: GATE BLOCKS PER SIDE ---")
gate_by_side = {"UP": Counter(), "DN": Counter()}
for e in events:
    if e["type"].startswith("gate_") and "side" in e:
        gate_by_side[e["side"]][e["type"]] += 1

for side in ["UP", "DN"]:
    print(f"  {side}:")
    for gate, count in gate_by_side[side].most_common():
        print(f"    {gate}: {count}")
print()

# 5. Per-bar event trace: which gate is blocking the missing side?
print("--- Q5: WHAT BLOCKS THE MISSING SIDE IN ONE-SIDED BARS ---")
one_sided_gates = Counter()
for b in one_sided_bars:
    bar_id = b["bar_id"]
    buy_orders = [o for o in b["orders"] if "sell" not in o.get("reason", "").lower()]
    filled_sides = set(o["side"] for o in buy_orders)
    missing_side = "DN" if "UP" in filled_sides else "UP"

    bar_events = [e for e in events if e.get("bar_id") == bar_id]
    gates_for_missing = [e for e in bar_events if e["type"].startswith("gate_") and e.get("side") == missing_side]

    if gates_for_missing:
        # Most common gate for missing side
        gate_types = Counter(e["type"] for e in gates_for_missing)
        top_gate = gate_types.most_common(1)[0][0]
        one_sided_gates[top_gate] += 1
    else:
        # Check if there were any orders placed for missing side that didn't fill
        orders_for_missing = [e for e in bar_events if e["type"] == "order" and e.get("side") == missing_side]
        if orders_for_missing:
            one_sided_gates["orders_placed_but_no_fill"] += 1
        else:
            one_sided_gates["no_orders_no_gates"] += 1

print(f"  Primary blocker for missing side ({len(one_sided_bars)} one-sided bars):")
for gate, count in one_sided_gates.most_common():
    print(f"    {gate}: {count}")
print()

# 6. Risk budget analysis: is risk_cap the main blocker?
print("--- Q6: RISK CAP IMPACT ---")
risk_events = [e for e in events if e["type"] == "gate_risk_cap"]
print(f"  Total risk_cap gates: {len(risk_events)}")
if risk_events:
    caps = [e.get("capped_to", 0) for e in risk_events]
    allowed = [e.get("allowed", 0) for e in risk_events]
    zero_caps = sum(1 for c in caps if c <= 0)
    tiny_caps = sum(1 for c in caps if 0 < c <= 1.0)
    print(f"  Capped to $0 (blocked): {zero_caps}")
    print(f"  Capped to $0-1 (tiny):  {tiny_caps}")
    print(f"  Avg allowed risk: ${sum(allowed)/len(allowed):.2f}")
    print(f"  Avg capped to:    ${sum(caps)/len(caps):.2f}")
print()

# 7. The real question: cost structure of profitable vs unprofitable bars
print("--- Q7: PROFITABLE vs UNPROFITABLE BARS — WHAT'S DIFFERENT? ---")
profitable = [b for b in bars if b["pnl"]["profit"] > 0]
unprofitable = [b for b in bars if b["pnl"]["profit"] <= 0]

for label, group in [("PROFITABLE", profitable), ("UNPROFITABLE", unprofitable)]:
    if not group:
        continue
    n = len(group)
    avg_matched = sum(b["inventory"]["matched"] for b in group) / n
    avg_unm = sum(b["inventory"]["unmatched_up"] + b["inventory"]["unmatched_dn"] for b in group) / n
    avg_cost = sum(b["cost"]["total"] for b in group) / n
    avg_pc = sum(b["cost"]["avg_pair_cost"] for b in group if b["inventory"]["matched"] > 0) / max(sum(1 for b in group if b["inventory"]["matched"] > 0), 1)
    avg_fills = sum(b["fill_stats"]["orders_filled"] for b in group) / n
    avg_pnl = sum(b["pnl"]["profit"] for b in group) / n

    print(f"\n  {label} ({n} bars):")
    print(f"    Avg matched:    {avg_matched:.1f} shares")
    print(f"    Avg unmatched:  {avg_unm:.1f} shares")
    print(f"    Avg pair cost:  {avg_pc:.4f}")
    print(f"    Avg total cost: ${avg_cost:.2f}")
    print(f"    Avg fills:      {avg_fills:.1f}")
    print(f"    Avg P&L:        ${avg_pnl:.2f}")

    # Unmatched side vs outcome
    correct_unmatched = 0
    wrong_unmatched = 0
    for b in group:
        unm_up = b["inventory"]["unmatched_up"]
        unm_dn = b["inventory"]["unmatched_dn"]
        if unm_up > unm_dn:
            if b["outcome"] == "UP":
                correct_unmatched += 1
            else:
                wrong_unmatched += 1
        elif unm_dn > unm_up:
            if b["outcome"] == "DN":
                correct_unmatched += 1
            else:
                wrong_unmatched += 1
    print(f"    Unmatched on correct side: {correct_unmatched}")
    print(f"    Unmatched on wrong side:   {wrong_unmatched}")
print()

# 8. The BIG insight: bars with LOW fills have high waste
print("--- Q8: FILL COUNT vs P&L ---")
fill_buckets = [(0, 2, "0-1"), (2, 6, "2-5"), (6, 15, "6-14"), (15, 30, "15-29"), (30, 999, "30+")]
for lo, hi, label in fill_buckets:
    group = [b for b in bars if lo <= b["fill_stats"]["orders_filled"] < hi]
    if group:
        pnl = sum(b["pnl"]["profit"] for b in group)
        avg_matched = sum(b["inventory"]["matched"] for b in group) / len(group)
        avg_unm = sum(b["inventory"]["unmatched_up"] + b["inventory"]["unmatched_dn"] for b in group) / len(group)
        print(f"  {label} fills: {len(group)} bars, P&L ${pnl:.2f}, avg matched={avg_matched:.1f}, avg unmatched={avg_unm:.1f}")
print()

# 9. Critical: bars where model is confident but we barely fill
print("--- Q9: HIGH CONFIDENCE + LOW VOLUME BARS ---")
for b in bars:
    prob = b["model_stats"]["avg_prob"]
    fills = b["fill_stats"]["orders_filled"]
    matched = b["inventory"]["matched"]
    confidence = max(prob, 1.0 - prob)  # confidence regardless of direction

    if confidence > 0.6 and fills < 5:
        ws = b["window_start"]
        outcome = b["outcome"]
        profit = b["pnl"]["profit"]
        cost = b["cost"]["total"]
        print(f"  {ws} conf={confidence:.2f} fills={fills} matched={matched:.0f} cost=${cost:.2f} P&L=${profit:.2f} outcome={outcome}")
print()

# 10. What fraction of total loss comes from one-sided bars vs both-sided?
print("--- Q10: LOSS ATTRIBUTION ---")
zero_bar = [b for b in bars if b["fill_stats"]["orders_filled"] <= 1]
one_side = [b for b in bars if b not in zero_bar and b in one_sided_bars]
both_side_good = [b for b in both_bars if b["inventory"]["matched"] > 0 and b["cost"]["avg_pair_cost"] < 1.0]
both_side_bad = [b for b in both_bars if b["inventory"]["matched"] > 0 and b["cost"]["avg_pair_cost"] >= 1.0]
both_side_zero = [b for b in both_bars if b["inventory"]["matched"] == 0]

categories = [
    ("Zero/1 fill bars", zero_bar),
    ("One-sided only", one_side),
    ("Both-sided, pc < 1.0", both_side_good),
    ("Both-sided, pc >= 1.0", both_side_bad),
    ("Both-sided, 0 matched", both_side_zero),
]
for label, group in categories:
    n = len(group)
    pnl = sum(b["pnl"]["profit"] for b in group) if group else 0
    cost = sum(b["cost"]["total"] for b in group) if group else 0
    print(f"  {label}: {n} bars, cost=${cost:.2f}, P&L=${pnl:.2f}")
