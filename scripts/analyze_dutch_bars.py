#!/usr/bin/env python
"""Deep analysis of Dutch backtest bar + event JSONL files."""
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

print(f"=== OVERVIEW: {len(bars)} bars, {len(events)} events ===\n")

# 1. P&L distribution
profits = [b["pnl"]["profit"] for b in bars]
winning = [p for p in profits if p > 0]
losing = [p for p in profits if p <= 0]
print("--- P&L DISTRIBUTION ---")
print(f"Total P&L:     ${sum(profits):.2f}")
print(f"Winning bars:  {len(winning)}/{len(bars)} ({100*len(winning)/len(bars):.1f}%)")
print(f"Losing bars:   {len(losing)}/{len(bars)} ({100*len(losing)/len(bars):.1f}%)")
print(f"Avg win:       ${sum(winning)/max(len(winning),1):.2f}")
print(f"Avg loss:      ${sum(losing)/max(len(losing),1):.2f}")
print(f"Best bar:      ${max(profits):.2f}")
print(f"Worst bar:     ${min(profits):.2f}\n")

# 2. Outcome distribution
outcomes = Counter(b["outcome"] for b in bars)
print("--- OUTCOMES ---")
for k, v in outcomes.items():
    pnl_for = sum(b["pnl"]["profit"] for b in bars if b["outcome"] == k)
    print(f"{k}: {v} bars, total P&L ${pnl_for:.2f}, avg ${pnl_for/v:.2f}")
print()

# 3. Pair cost analysis
pair_costs = [b["cost"]["avg_pair_cost"] for b in bars if b["inventory"]["matched"] > 0]
above_1 = [pc for pc in pair_costs if pc > 1.0]
below_1 = [pc for pc in pair_costs if pc < 1.0]
at_1 = [pc for pc in pair_costs if pc == 1.0]
print("--- PAIR COST ---")
print(f"Bars with matched shares: {len(pair_costs)}/{len(bars)}")
print(f"Avg pair cost:       {sum(pair_costs)/len(pair_costs):.4f}")
print(f"Bars with pc > 1.0: {len(above_1)}/{len(pair_costs)} ({100*len(above_1)/len(pair_costs):.1f}%)")
print(f"Bars with pc = 1.0: {len(at_1)}/{len(pair_costs)} ({100*len(at_1)/len(pair_costs):.1f}%)")
print(f"Bars with pc < 1.0: {len(below_1)}/{len(pair_costs)} ({100*len(below_1)/len(pair_costs):.1f}%)")
if above_1:
    print(f"Avg pc when > 1.0:  {sum(above_1)/len(above_1):.4f}")
if below_1:
    print(f"Avg pc when < 1.0:  {sum(below_1)/len(below_1):.4f}")
print()

# Pair cost histogram
print("--- PAIR COST HISTOGRAM ---")
buckets = [(0.7, 0.8), (0.8, 0.85), (0.85, 0.9), (0.9, 0.95), (0.95, 1.0), (1.0, 1.05), (1.05, 1.1), (1.1, 1.2)]
for lo, hi in buckets:
    n = sum(1 for pc in pair_costs if lo <= pc < hi)
    bar_str = "#" * n
    print(f"  [{lo:.2f}-{hi:.2f}): {n:3d} {bar_str}")
print()

# 4. Inventory analysis
print("--- INVENTORY BALANCE ---")
total_up = sum(b["inventory"]["up_shares"] for b in bars)
total_dn = sum(b["inventory"]["dn_shares"] for b in bars)
total_matched = sum(b["inventory"]["matched"] for b in bars)
total_unm_up = sum(b["inventory"]["unmatched_up"] for b in bars)
total_unm_dn = sum(b["inventory"]["unmatched_dn"] for b in bars)
total_sold_up = sum(b["inventory"].get("sold_up", 0) for b in bars)
total_sold_dn = sum(b["inventory"].get("sold_dn", 0) for b in bars)
print(f"Total UP shares bought: {total_up:.1f}")
print(f"Total DN shares bought: {total_dn:.1f}")
print(f"Total matched:          {total_matched:.1f}")
print(f"Total unmatched UP:     {total_unm_up:.1f}")
print(f"Total unmatched DN:     {total_unm_dn:.1f}")
print(f"Total sold UP:          {total_sold_up:.1f}")
print(f"Total sold DN:          {total_sold_dn:.1f}")
print(f"Match rate:             {total_matched / max(total_up, total_dn, 0.01) * 100:.1f}%")
print()

# 5. CORE economics
print("--- CORE ECONOMICS ---")
total_cost = sum(b["cost"]["total"] for b in bars)
total_payout = sum(b["pnl"]["payout"] for b in bars)
total_matched_payout = sum(b["pnl"].get("matched_payout", 0) for b in bars)
total_unmatched_payout = sum(b["pnl"].get("unmatched_payout", 0) for b in bars)
print(f"Total $ spent buying:     ${total_cost:.2f}")
print(f"Total matched payout:     ${total_matched_payout:.2f}")
print(f"Total unmatched payout:   ${total_unmatched_payout:.2f}")
print(f"Net P&L:                  ${total_payout + total_unmatched_payout - total_cost:.2f}")
print(f"Effective cost ratio:     {total_cost / max(total_payout + total_unmatched_payout, 1):.4f}")
print()

# 6. Decompose: matched pair P&L vs unmatched waste
print("--- LOSS DECOMPOSITION (the big question) ---")
matched_profit_total = 0  # profit just from matched pairs (pair_cost < 1 contributes positive)
unmatched_waste_total = 0  # money spent on unmatched losing-side shares
unmatched_bonus_total = 0  # money won from unmatched winning-side shares

for b in bars:
    matched = b["inventory"]["matched"]
    pc = b["cost"]["avg_pair_cost"]
    unm_up = b["inventory"]["unmatched_up"]
    unm_dn = b["inventory"]["unmatched_dn"]

    # Matched pair profit: matched * (1.0 - pair_cost)
    matched_profit = matched * (1.0 - pc) if matched > 0 else 0
    matched_profit_total += matched_profit

    # Unmatched: compute avg cost per share per side
    up_shares = b["inventory"]["up_shares"]
    dn_shares = b["inventory"]["dn_shares"]
    cost_per_up = b["cost"]["cost_up"] / up_shares if up_shares > 0 else 0
    cost_per_dn = b["cost"]["cost_dn"] / dn_shares if dn_shares > 0 else 0

    if b["outcome"] == "UP":
        # UP wins: unmatched UP pays out, unmatched DN is waste
        unmatched_bonus_total += unm_up * (1.0 - cost_per_up)  # profit on winning unmatched
        unmatched_waste_total += unm_dn * cost_per_dn  # total loss on losing unmatched
    else:
        # DN wins: unmatched DN pays out, unmatched UP is waste
        unmatched_bonus_total += unm_dn * (1.0 - cost_per_dn)
        unmatched_waste_total += unm_up * cost_per_up

print(f"Matched pair P&L:       ${matched_profit_total:.2f}  (from pair_cost {'<' if matched_profit_total > 0 else '>'} 1.0)")
print(f"Unmatched losing waste: ${-unmatched_waste_total:.2f}  (bought wrong side, no match)")
print(f"Unmatched winning gain: ${unmatched_bonus_total:.2f}  (lucky unmatched on right side)")
print(f"TOTAL check:            ${matched_profit_total - unmatched_waste_total + unmatched_bonus_total:.2f}")
print()

# Bars with worst unmatched waste
print("--- TOP 10 WORST UNMATCHED WASTE BARS ---")
bar_waste = []
for b in bars:
    unm_up = b["inventory"]["unmatched_up"]
    unm_dn = b["inventory"]["unmatched_dn"]
    up_shares = b["inventory"]["up_shares"]
    dn_shares = b["inventory"]["dn_shares"]
    cost_per_up = b["cost"]["cost_up"] / up_shares if up_shares > 0 else 0
    cost_per_dn = b["cost"]["cost_dn"] / dn_shares if dn_shares > 0 else 0

    if b["outcome"] == "UP":
        waste = unm_dn * cost_per_dn
    else:
        waste = unm_up * cost_per_up
    bar_waste.append((waste, b))

bar_waste.sort(key=lambda x: x[0], reverse=True)
for waste, b in bar_waste[:10]:
    ws = b["window_start"]
    out = b["outcome"]
    matched = b["inventory"]["matched"]
    unm = b["inventory"]["unmatched_up"] + b["inventory"]["unmatched_dn"]
    profit = b["pnl"]["profit"]
    pc = b["cost"]["avg_pair_cost"]
    print(f"  {ws} {out} matched={matched:.0f} unmatched={unm:.0f} pc={pc:.3f} waste=${waste:.2f} profit=${profit:.2f}")
print()

# 7. Fill price analysis
print("--- FILL PRICE ANALYSIS (BUY orders only) ---")
all_up_prices = []
all_dn_prices = []
for b in bars:
    for o in b["orders"]:
        reason = o.get("reason", "")
        if "sell" in reason.lower():
            continue
        if o["side"] == "UP":
            all_up_prices.append(o["fill_price"])
        else:
            all_dn_prices.append(o["fill_price"])

if all_up_prices:
    print(f"UP buys:  n={len(all_up_prices)}, avg={sum(all_up_prices)/len(all_up_prices):.4f}, "
          f"min={min(all_up_prices):.2f}, max={max(all_up_prices):.2f}")
if all_dn_prices:
    print(f"DN buys:  n={len(all_dn_prices)}, avg={sum(all_dn_prices)/len(all_dn_prices):.4f}, "
          f"min={min(all_dn_prices):.2f}, max={max(all_dn_prices):.2f}")
if all_up_prices and all_dn_prices:
    avg_sum = sum(all_up_prices)/len(all_up_prices) + sum(all_dn_prices)/len(all_dn_prices)
    print(f"Avg(UP) + Avg(DN) = {avg_sum:.4f}  {'PROFITABLE' if avg_sum < 1.0 else 'LOSING'}")
print()

# 8. Per-bar: are we buying UP and DN at complementary prices?
print("--- PER-BAR PRICE COMPLEMENTARITY ---")
print("For dutch to work: within each bar, avg_fill(UP) + avg_fill(DN) < 1.0")
bars_complementary = 0
bars_not = 0
gaps = []
for b in bars:
    up_fills = [o["fill_price"] for o in b["orders"] if o["side"] == "UP" and "sell" not in o.get("reason", "").lower()]
    dn_fills = [o["fill_price"] for o in b["orders"] if o["side"] == "DN" and "sell" not in o.get("reason", "").lower()]
    if up_fills and dn_fills:
        avg_up = sum(up_fills) / len(up_fills)
        avg_dn = sum(dn_fills) / len(dn_fills)
        gap = avg_up + avg_dn - 1.0
        gaps.append(gap)
        if gap < 0:
            bars_complementary += 1
        else:
            bars_not += 1

print(f"Bars where avg(UP)+avg(DN) < 1.0: {bars_complementary}/{bars_complementary+bars_not}")
print(f"Bars where avg(UP)+avg(DN) >= 1.0: {bars_not}/{bars_complementary+bars_not}")
if gaps:
    print(f"Avg gap from 1.0: {sum(gaps)/len(gaps):+.4f}")
    print(f"Worst overpay:    {max(gaps):+.4f}")
    print(f"Best underpay:    {min(gaps):+.4f}")
print()

# 9. The spread problem: are UP and DN from same time or different times?
print("--- TIMING: UP vs DN fill timing within bars ---")
early_up_late_dn = 0
early_dn_late_up = 0
mixed = 0
for b in bars:
    up_times = [o["time_pct"] for o in b["orders"] if o["side"] == "UP" and "sell" not in o.get("reason", "").lower()]
    dn_times = [o["time_pct"] for o in b["orders"] if o["side"] == "DN" and "sell" not in o.get("reason", "").lower()]
    if up_times and dn_times:
        avg_up_t = sum(up_times) / len(up_times)
        avg_dn_t = sum(dn_times) / len(dn_times)
        if abs(avg_up_t - avg_dn_t) < 0.05:
            mixed += 1
        elif avg_up_t < avg_dn_t:
            early_up_late_dn += 1
        else:
            early_dn_late_up += 1

print(f"UP earlier, DN later: {early_up_late_dn}")
print(f"DN earlier, UP later: {early_dn_late_up}")
print(f"Roughly simultaneous: {mixed}")
print()

# 10. Price drift: are we buying into moves?
print("--- PRICE DRIFT: buying into adverse moves ---")
print("Checking if mid_price drifts against us during accumulation")
adverse_bars = 0
for b in bars:
    mid_range = b["market_stats"]["mid_range_up"]
    mid_start = mid_range[0]
    mid_end = mid_range[1]
    outcome = b["outcome"]

    # In an UP outcome: price went up. If we bought UP cheap early and DN expensive late = good
    # In a DN outcome: price went down. If we bought DN cheap early and UP expensive late = good
    # The issue is if price is drifting and we keep buying the wrong side at worse prices

    up_late_fills = [o for o in b["orders"] if o["side"] == "UP" and o["time_pct"] > 0.5 and "sell" not in o.get("reason", "").lower()]
    dn_late_fills = [o for o in b["orders"] if o["side"] == "DN" and o["time_pct"] > 0.5 and "sell" not in o.get("reason", "").lower()]

    if outcome == "DN" and up_late_fills:
        # Bought UP late when price was dropping = adverse
        adverse_bars += 1
    elif outcome == "UP" and dn_late_fills:
        # Bought DN late when price was rising = adverse
        adverse_bars += 1

print(f"Bars with late adverse-side fills: {adverse_bars}/{len(bars)} ({100*adverse_bars/len(bars):.1f}%)")
print()

# 11. Gate events analysis
print("--- GATE EVENTS (what prevented orders) ---")
gate_events = [e for e in events if e["type"].startswith("gate_")]
gate_types = Counter(e["type"] for e in gate_events)
for t, c in gate_types.most_common():
    print(f"  {t}: {c}")
print()

# 12. Sell analysis
print("--- SELL ORDERS ---")
sell_orders = []
for b in bars:
    for o in b["orders"]:
        if "sell" in o.get("reason", "").lower():
            sell_orders.append({**o, "window": b["window_start"], "outcome": b["outcome"]})

print(f"Total sell orders: {len(sell_orders)}")
if sell_orders:
    sell_types = Counter()
    for s in sell_orders:
        reason = s["reason"]
        if "profit" in reason:
            sell_types["sell_profit"] += 1
        elif "cut" in reason:
            sell_types["sell_cut"] += 1
        elif "dump" in reason:
            sell_types["sell_dump"] += 1
        else:
            sell_types["other"] += 1
    for t, c in sell_types.most_common():
        print(f"  {t}: {c}")

    total_sell_dollars = sum(s["dollars"] for s in sell_orders)
    print(f"Total sell $ recovered: ${total_sell_dollars:.2f}")
print()

# 13. Model conviction analysis
print("--- MODEL CONVICTION ---")
avg_probs = [b["model_stats"]["avg_prob"] for b in bars]
for b in bars:
    prob = b["model_stats"]["avg_prob"]
    outcome = b["outcome"]
    correct = (prob > 0.5 and outcome == "UP") or (prob < 0.5 and outcome == "DN")
    b["_model_correct"] = correct

correct_bars = sum(1 for b in bars if b["_model_correct"])
print(f"Model correct direction: {correct_bars}/{len(bars)} ({100*correct_bars/len(bars):.1f}%)")
print(f"Avg probability: {sum(avg_probs)/len(avg_probs):.4f}")
print(f"Prob range: [{min(avg_probs):.4f}, {max(avg_probs):.4f}]")
print()

# P&L when model correct vs wrong
correct_pnl = sum(b["pnl"]["profit"] for b in bars if b["_model_correct"])
wrong_pnl = sum(b["pnl"]["profit"] for b in bars if not b["_model_correct"])
n_correct = sum(1 for b in bars if b["_model_correct"])
n_wrong = len(bars) - n_correct
print(f"P&L when model correct: ${correct_pnl:.2f} ({n_correct} bars, avg ${correct_pnl/max(n_correct,1):.2f})")
print(f"P&L when model wrong:   ${wrong_pnl:.2f} ({n_wrong} bars, avg ${wrong_pnl/max(n_wrong,1):.2f})")
print()

# 14. Chase analysis
print("--- CHASE FILLS ---")
chase_orders = []
non_chase = []
for b in bars:
    for o in b["orders"]:
        reason = o.get("reason", "")
        if "sell" in reason.lower():
            continue
        if "chase" in reason:
            chase_orders.append(o)
        else:
            non_chase.append(o)

print(f"Chased fills: {len(chase_orders)}")
print(f"Non-chased fills: {len(non_chase)}")
if chase_orders:
    chase_up = [o for o in chase_orders if o["side"] == "UP"]
    chase_dn = [o for o in chase_orders if o["side"] == "DN"]
    if chase_up:
        print(f"  Chase UP: n={len(chase_up)}, avg price={sum(o['fill_price'] for o in chase_up)/len(chase_up):.4f}")
    if chase_dn:
        print(f"  Chase DN: n={len(chase_dn)}, avg price={sum(o['fill_price'] for o in chase_dn)/len(chase_dn):.4f}")
if non_chase:
    nc_up = [o for o in non_chase if o["side"] == "UP"]
    nc_dn = [o for o in non_chase if o["side"] == "DN"]
    if nc_up:
        print(f"  NoChase UP: n={len(nc_up)}, avg price={sum(o['fill_price'] for o in nc_up)/len(nc_up):.4f}")
    if nc_dn:
        print(f"  NoChase DN: n={len(nc_dn)}, avg price={sum(o['fill_price'] for o in nc_dn)/len(nc_dn):.4f}")
print()

# 15. Worst bars deep dive
print("--- TOP 5 WORST BARS (deep dive) ---")
sorted_bars = sorted(bars, key=lambda b: b["pnl"]["profit"])
for b in sorted_bars[:5]:
    ws = b["window_start"]
    print(f"\n  BAR: {ws} outcome={b['outcome']} profit=${b['pnl']['profit']:.2f}")
    print(f"    matched={b['inventory']['matched']:.1f} unm_up={b['inventory']['unmatched_up']:.1f} unm_dn={b['inventory']['unmatched_dn']:.1f}")
    print(f"    cost_up=${b['cost']['cost_up']:.2f} cost_dn=${b['cost']['cost_dn']:.2f} total=${b['cost']['total']:.2f}")
    print(f"    pair_cost={b['cost']['avg_pair_cost']:.4f} payout=${b['pnl']['payout']:.2f}")
    print(f"    model: avg_prob={b['model_stats']['avg_prob']:.4f} flips={b['model_stats']['flips']}")
    print(f"    fills: placed={b['fill_stats']['orders_placed']} filled={b['fill_stats']['orders_filled']} chased={b['fill_stats']['chased']}")

    # Show UP vs DN fill prices
    up_fills = [(o["fill_price"], o["time_pct"]) for o in b["orders"] if o["side"] == "UP" and "sell" not in o.get("reason", "").lower()]
    dn_fills = [(o["fill_price"], o["time_pct"]) for o in b["orders"] if o["side"] == "DN" and "sell" not in o.get("reason", "").lower()]
    if up_fills:
        print(f"    UP fills: {len(up_fills)}, prices=[{min(p for p,t in up_fills):.2f}-{max(p for p,t in up_fills):.2f}], times=[{min(t for p,t in up_fills):.2f}-{max(t for p,t in up_fills):.2f}]")
    if dn_fills:
        print(f"    DN fills: {len(dn_fills)}, prices=[{min(p for p,t in dn_fills):.2f}-{max(p for p,t in dn_fills):.2f}], times=[{min(t for p,t in dn_fills):.2f}-{max(t for p,t in dn_fills):.2f}]")
print()

# 16. Summary
print("=" * 70)
print("DIAGNOSIS SUMMARY")
print("=" * 70)
print(f"""
1. PAIR COST: avg {sum(pair_costs)/len(pair_costs):.4f}
   - {len(above_1)}/{len(pair_costs)} bars have pair_cost > 1.0 (LOSING on matched pairs)
   - Even matched pairs are barely profitable when pc < 1.0

2. UNMATCHED SHARES: {total_unm_up + total_unm_dn:.0f} unmatched vs {total_matched:.0f} matched
   - Unmatched waste: ${unmatched_waste_total:.2f}
   - This is {abs(unmatched_waste_total) / abs(sum(profits)) * 100:.0f}% of total loss

3. MODEL ACCURACY: {100*correct_bars/len(bars):.1f}% correct
   - But LOSES money even when correct: ${correct_pnl/max(n_correct,1):.2f}/bar
   - Structural issue: cost > payout regardless of direction

4. SELL RATIO: {len(sell_orders)} sells across {len(bars)} bars
   - Near-zero capital recycling

5. CHASE FILLS: {len(chase_orders)}/{len(chase_orders)+len(non_chase)} orders chased
   - Chasing likely worsens fill prices
""")
