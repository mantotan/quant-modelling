# Dutch Strategy
Updated: after iteration 72 (2026-03-27T20:00:00Z) — STRATEGIST rotation 7 pre-run analysis

## Summary

Rotation 6 complete (iters 61-72): 5 FROZEN SKIPs (BTC/ETH/SOL frozen pairs) + 1 DIAGNOSTIC SKIP (BTC_5m
iter 61) + 2 active experiments (ETH_1h fill_ticks=2 DISCARD iter 66, XRP_1h fill_ticks=2 KEEP iter 72).
**KEEP rate this rotation: 1/2 active experiments = 50%**
**Cumulative KEEP rate: 1/72 total iterations = 1.4% (or 1 KEEP out of ~12 non-baseline active experiments = 8.3%)**

This is the FIRST KEEP in 72 iterations. XRP_1h fill_ticks=2 produces marginal profit improvement
(+$0.01/bar: -$0.13 vs baseline -$0.14) without destabilizing pair formation. Modest but real signal.

ETH_1h fill_ticks=2 DISCARD: regression on profit (-$0.04 vs +$0.08 baseline) and max_dd (13.8% exceeds
12% threshold). 1h bars already fill at 81-85% with fill_ticks=1; persistence extension not beneficial.

Rotation 7 has NOT started. This strategist update provides explicit researcher instructions for the
chase_threshold experiments on both active pairs.

---

## AUDITOR FREEZES (active — do NOT run experiments)

- **XRP_5m**: FROZEN permanently. fill_rate=15.6% structural floor. Zero pairs at all gates.
- **SOL_15m**: FROZEN. correct_side=45.5% (both measurements below 50%). Resume only when correct_side > 50%.
- **XRP_15m**: FROZEN (iter 48 audit). correct_side=49.2% declining monotonically. Gate exhausted.
- **BTC_5m**: FROZEN permanently (confirmed by diagnostic iter 60). Fill mechanics block pair formation
  regardless of outcome source. P(both sides fill in 5m) = 5.6%. No levers remain.
- **BTC_15m**: FROZEN. 3 consecutive zero-pair baselines. Outcome sparsity (11/139=7.9%).
- **BTC_1h**: FROZEN. Extreme sparsity (1/34=2.9%). Gate series exhausted.
- **ETH_5m**: FROZEN. max_dd=28.7% near 30% kill threshold. 3 consecutive zero-pair baselines.
- **ETH_15m**: FROZEN. Gate series fully exhausted R4 (iters 5/17/40 all zero pairs). Highest latent
  potential: correct_side=71.2% consistent, avg_profit=+$0.16/bar (unmatched inventory).
- **SOL_5m**: FROZEN. 3 consecutive zero-pair runs. max_dd=23.2% elevated. fill_rate=23.1% (P=5.3%).
- **SOL_1h**: FROZEN. 3 consecutive zero-pair baselines. Outcome sparsity (3/35=8.6%).

---

## ETH_1h (pair_cost=0.594, KEEP rate 0% active experiments, max_dd=7.6%)

### Status: ACTIVE — PRIORITIZE (beats trader_a pair_cost target)

Full trajectory:
- Iter 6 (R1): cost=0.000, zero pairs at gate=0.08
- Iter 18 (R2 baseline): cost=0.594, matched=2.0%, profit=-$0.06/bar, DD=13.8%
- Iter 29 (R3 pace=0.25): DISCARD — identical to baseline (pace lever inert on thin data)
- Iter 41 (R4 baseline pace=0.35): cost=0.594, matched=2.0%, profit=+$0.08/bar, DD=7.6%
- Iter 53 (R5 pace=0.30): DISCARD — identical to baseline (pace lever confirmed inert, mirror of iter 29)
- Iter 66 (R6 fill_ticks=2): DISCARD — profit regression -$0.04/bar vs +$0.08; DD=13.8% exceeds 12%; fill_ticks extension not beneficial on already-high-fill pair
- Rotation 7: chase_threshold 0.03->0.05 experiment NEXT

ETH_1h best performer: pair_cost=0.594 BEATS trader_a target (<0.85). Profit=+$0.08/bar at baseline.
Current bottleneck: matched_ratio=2.0% insufficient for statistical significance. Each KEEP/DISCARD
boundary is difficult to call on 34-35 bars with 4-5 outcomes.

**Current knobs state:**
- knobs_ETH_1h.json: fill_ticks=1 (correctly restored post-DISCARD iter 66), chase_threshold=0.03
- best_knobs_ETH_1h.json: fill_ticks=1, chase_threshold=0.03 (unchanged — no KEEP yet)
- Confirmed: both files are at fill_ticks=1 and chase_threshold=0.03

**Staging instruction for researcher:**
BEFORE running ETH_1h experiment, set chase_threshold=0.05 in knobs_ETH_1h.json fill_simulator section.
Do NOT modify best_knobs_ETH_1h.json until KEEP is confirmed.

**Priority queue for rotation 7:**
1. **chase_threshold 0.03->0.05 EXPERIMENT** — stage chase_threshold=0.05 in knobs_ETH_1h.json
   - Hypothesis: wider chase window (5% vs 3% price deviation) allows orders to re-enter price after
     brief adverse moves, potentially increasing matched pairs in thin 1h market
   - Baseline ref: pair_cost=0.594, profit=+$0.08/bar, DD=7.6%, matched=2.0% (iter 41 best)
   - Accept KEEP if: matched_ratio > 2.0% OR avg_profit > +$0.08/bar (ANY improvement vs iter 41)
   - DISCARD if: pair_cost increases above 0.65 OR DD exceeds 12% OR matched_ratio drops below 1.5%
   - If KEEP: update best_knobs_ETH_1h.json with chase_threshold=0.05
   - If DISCARD: restore chase_threshold=0.03; next lever = pace_urgency_hi 2.0->1.5
2. If chase_threshold=0.05 DISCARDs: pace_urgency_hi 2.0->1.5 (reduce late-bar urgency spike)
   - Rationale: current urgency doubles at bar end; reducing to 1.5x may improve fill quality
   - Accept KEEP if: pair_cost < 0.594 OR avg_profit > +$0.08/bar
3. If pace_urgency_hi=1.5 DISCARDs: spread_offset 0.01->0.005 (tighter limit placement)
   - Rationale: tighter spread may improve fill rate marginally in liquid 1h ETH market
4. If 3 consecutive DISCARDs on fill sim params: escalate to auditor — ETH_1h at structural floor

Blacklist (cumulative): pace_urgency_lo 0.25/0.30 (inert — DEAD), fill_ticks=2 (regression iter 66),
onesided above 5, skip 0.40, risk_ceil 0.20, bar_budget 250/300, conviction_market_start (GLOBAL).

---

## XRP_1h (pair_cost=0.812, KEEP rate 16.7% (1/6 active), max_dd=9.8%)

### Status: ACTIVE — CONTINUE (first KEEP confirmed, beats pair_cost target)

Full trajectory:
- Iter 12 (R1 baseline): cost=0.855, matched=3.6%, profit=N/A, DD=3.1%
- Iter 23 (R2 baseline): cost=0.812, matched=4.2%, profit=+$0.10/bar, DD=8.0%
- Iter 35 (R3 pace=0.30): DISCARD — COLLAPSE (0% matched vs 4.2%); PACE FLOOR 0.35 CONFIRMED
- Iter 47 (R4 baseline onesided=5.0): cost=0.812, matched=4.1%, profit=-$0.14/bar, DD=9.8%
- Iter 59 (R5 onesided=2.0): DISCARD — COLLAPSE (0% matched); onesided floor confirmed >3.0
- Iter 72 (R6 fill_ticks=2): KEEP — cost=0.812 stable, profit=-$0.13/bar (IMPROVED +$0.01), DD=9.8% safe
- Rotation 7: chase_threshold 0.03->0.05 experiment NEXT

XRP_1h pair_cost=0.812 BEATS trader_a target (<0.85). Profit remains negative (-$0.13/bar) — needs fix.
fill_ticks=2 KEEP is the first concrete improvement: marginal profit boost, no destabilization.
The profitability gap (-$0.13/bar vs target >$0) is the primary focus for rotation 7+.

**Current knobs state:**
- knobs_XRP_1h.json: fill_ticks=2 (correctly reflecting KEEP), chase_threshold=0.03
- best_knobs_XRP_1h.json: fill_ticks=2 (correctly updated after KEEP), chase_threshold=0.03
- Confirmed: both files are at fill_ticks=2 and chase_threshold=0.03

**Staging instruction for researcher:**
BEFORE running XRP_1h experiment, set chase_threshold=0.05 in knobs_XRP_1h.json fill_simulator section.
Do NOT modify best_knobs_XRP_1h.json until KEEP is confirmed.
CRITICAL: do NOT change fill_ticks (keep at 2), onesided, pace_urgency_lo, or magnitude_gate.
Only change: chase_threshold 0.03->0.05.

**Priority queue for rotation 7:**
1. **chase_threshold 0.03->0.05 EXPERIMENT** — stage chase_threshold=0.05 in knobs_XRP_1h.json
   - Hypothesis: wider chase window allows re-entry after price movement in sparse XRP_1h market,
     potentially improving fill quality and matched_ratio from 4.0%
   - Baseline ref: pair_cost=0.812, profit=-$0.13/bar, DD=9.8%, matched=4.0% (iter 72, KEEP state)
   - Accept KEEP if: pair_cost < 0.812 OR avg_profit > -$0.13/bar (ANY improvement)
   - DISCARD if: matched_ratio < 2.0% OR DD > 15%
   - Note: chase_threshold is fill-sim only, should NOT trigger the collapse mechanism
   - If KEEP: update best_knobs_XRP_1h.json with chase_threshold=0.05
   - If DISCARD: restore chase_threshold=0.03; next lever = onesided=3.5 intermediate test
2. If chase_threshold=0.05 DISCARDs: onesided=3.5 intermediate test
   - Rationale: onesided=2.0 collapses at iter 59; onesided=5.0 is stable; $3.5 is midpoint
   - Accept KEEP if: pair_cost < 0.812 OR avg_profit > -$0.13/bar
   - Extreme caution: if matched_ratio < 2.0%, immediate DISCARD (collapse mechanism)
3. If onesided=3.5 collapses: CONFIRM onesided floor at 5.0. Next: pace_urgency_hi 2.0->1.5
4. If 3 consecutive DISCARDs: escalate to auditor — XRP_1h structural floor assessment needed

Blacklist (cumulative): skip 0.45/0.55, bar_budget 300, risk_ceil 0.20,
pace_urgency_lo 0.30 (COLLAPSE iter 35), pace_urgency_lo 0.45 (D pre-RESET),
max_onesided_cost 2.0 (COLLAPSE iter 59), fill_ticks=1 deprecated (KEEP at fill_ticks=2).
PACE_LO FLOOR: 0.35 confirmed. ONESIDED FLOOR: 5.0 current reference.

---

## Rotation 7 Execution Plan (priority order)

1. **BTC_5m** — SKIP (FROZEN PERMANENT — fill mechanics structural, P=5.6%)
2. **BTC_15m** — SKIP (FROZEN — 3 consecutive zero-pair baselines, outcome sparsity 7.9%)
3. **BTC_1h** — SKIP (FROZEN — extreme sparsity 2.9%)
4. **ETH_5m** — SKIP (FROZEN — DD=28.7% near kill threshold, fill mechanics structural P=5.8%)
5. **ETH_15m** — SKIP (FROZEN — gate series exhausted, outcome sparsity 9.9%)
6. **ETH_1h** — **chase_threshold 0.03->0.05 EXPERIMENT** (stage in knobs_ETH_1h.json only)
7. **SOL_5m** — SKIP (FROZEN — outcome sparsity 6.7%, DD elevated, fill mechanics P=5.3%)
8. **SOL_15m** — SKIP (FROZEN — correct_side=45.5% < 50%)
9. **SOL_1h** — SKIP (FROZEN — outcome sparsity 8.6%)
10. **XRP_5m** — SKIP (FROZEN PERMANENT)
11. **XRP_15m** — SKIP (FROZEN — correct_side declining, gate exhausted)
12. **XRP_1h** — **chase_threshold 0.03->0.05 EXPERIMENT** (stage in knobs_XRP_1h.json only; keep fill_ticks=2)

**Rotation 7 success criteria:**
- At minimum 1 KEEP on chase_threshold (same bar as rotation 6 at 50% KEEP rate on fill_ticks)
- If both chase DISCARDs: system has exhausted fill-sim lever set 1 (fill_ticks, chase_threshold)
  → escalate to next category: pace_urgency_hi on both active pairs
- If chase DISCARDs and pace_urgency_hi also DISCARDs in rotation 8:
  consider auditor for structural assessment — dataset growth may be required

---

## Cross-Pair Observations

### Rotation 6 critical findings

**First KEEP achieved (iter 72, XRP_1h fill_ticks=2):**
- fill_ticks extends limit order persistence across 2 tick intervals
- Marginal improvement: +$0.01/bar profit, pair formation stable at 4.0%
- Result is real but small — XRP_1h remains loss-making (-$0.13/bar)
- This confirms fill-sim levers are the correct avenue for thin 1h markets

**ETH_1h fill_ticks=2 DISCARD (iter 66): divergent behavior from XRP_1h:**
- ETH_1h fill_rate already 81-85% at fill_ticks=1 — near ceiling
- Adding persistence increases DD (13.8% vs 7.6% baseline) — longer-lived orders accumulate more
  unmatched inventory in adverse moves
- XRP_1h fill_rate=69-74% at fill_ticks=1 — more room for improvement → fill_ticks=2 beneficial
- Lesson: fill_ticks benefit correlates inversely with baseline fill_rate

**Fill rate differential determines fill_ticks effectiveness:**
- ETH_1h fill_rate=81-85%: fill_ticks=2 DISCARD (already filling well)
- XRP_1h fill_rate=70-74%: fill_ticks=2 KEEP (room for improvement)
- This pattern predicts: chase_threshold may also behave differently by pair

**Dataset growth bottleneck remains the primary constraint for frozen pairs:**
- All 10 frozen pairs blocked by either fill mechanics (5m/some 15m) or outcome sparsity (15m/1h)
- ETH_1h/XRP_1h: 34-36 bars, 4-5 outcomes — 12 iterations of experiments on effectively the same data
- Without live-log data accumulation (OHLC resolution or time), frozen pairs cannot be unblocked
- Fill mechanics pairs (BTC_5m, ETH_5m, SOL_5m, XRP_5m): permanent unless fill engine redesigned

**Parameter categories tested to date and effectiveness:**
- magnitude_gate: EXHAUSTED (all values 0.08/0.04/0.02/0.0 tested across all pairs — uniformly ineffective)
- pace_urgency_lo: DEAD on thin datasets. Lever EXHAUSTED for ETH_1h. Floor=0.35 for XRP_1h.
- max_onesided_cost: Collapse mechanism confirmed at $2. XRP_1h floor at $5 (onesided=5.0).
- fill_ticks: TESTED. KEEP on XRP_1h. DISCARD on ETH_1h. Beneficial at lower fill rates only.
- chase_threshold: UNTESTED on both active pairs — NEXT PRIORITY for rotation 7.
- pace_urgency_hi: UNTESTED on both active pairs — queued for rotation 8 if chase DISCARDs.
- spread_offset: UNTESTED — lower priority.
- max_chase: UNTESTED — lower priority.

---

## trader_a Benchmark Comparison (after rotation 6, iter 72)

| Pair | PairCost | Target | Gap | AvgProfit | MaxDD% | Status |
|------|----------|--------|-----|-----------|--------|--------|
| BTC_5m | 0.000 | < 0.85 | N/A | -$0.060/bar | 23.4% | FROZEN PERMANENT — fill mechanics (P=5.6%) |
| BTC_15m | 0.000 | < 0.85 | N/A | -$0.019/bar | 12.4% | FROZEN — outcome sparsity + zero pairs |
| BTC_1h | 0.000 | < 0.85 | N/A | -$0.032/bar | 3.9% | FROZEN — extreme sparsity (2.9%) |
| ETH_5m | 0.000 | < 0.85 | N/A | -$0.091/bar | 28.7% | FROZEN — DD WARNING, fill mechanics (P=5.8%) |
| ETH_15m | 0.000 | < 0.85 | N/A | +$0.158/bar | 7.1% | FROZEN — gate exhausted, strong signal wasted |
| ETH_1h | 0.594 | < 0.85 | -0.256 (BEATS) | +$0.080/bar | 7.6% | ACTIVE — chase_threshold=0.05 queued |
| SOL_5m | 0.000 | < 0.85 | N/A | +$0.135/bar | 23.2% | FROZEN — fill mechanics (P=5.3%) |
| SOL_15m | 0.567* | < 0.85 | N/A | -$0.270/bar | 19.8% | FROZEN — correct_side=45.5% < 50% |
| SOL_1h | 0.000 | < 0.85 | N/A | -$0.110/bar | 8.3% | FROZEN — outcome sparsity (8.6%) |
| XRP_5m | N/A | < 0.85 | N/A | N/A | N/A | FROZEN PERMANENT — fill_rate=15.6% floor |
| XRP_15m | 0.950 | < 0.85 | +0.100 (FAILS) | -$0.240/bar | 20.5% | FROZEN — correct_side=49.2% declining |
| XRP_1h | 0.812 | < 0.85 | -0.038 (BEATS) | -$0.130/bar | 9.8% | ACTIVE — chase_threshold=0.05 queued |

*SOL_15m: artificially low pair_cost (near-zero pairs)

Best performers (active, pair_cost beats target):
- ETH_1h: pair_cost=0.594 — BENCHMARK ACHIEVED. profit=+$0.08/bar positive. CHASE THRESHOLD NEXT.
- XRP_1h: pair_cost=0.812 — BENCHMARK ACHIEVED. profit=-$0.13/bar negative. CHASE THRESHOLD NEXT.

Primary gap to close: XRP_1h profitability (-$0.13/bar vs >$0 target).
Secondary gap: ETH_1h matched_ratio at 2.0% — insufficient statistical power for reliable experiments.

Pairs with strong signal quality but frozen by structural issues (priority for future unfreeze):
- ETH_15m: correct_side=71.2%, avg_profit=+$0.16/bar (unmatched) — highest latent potential
- BTC_1h: correct_side=70.0% — strong signal, blocked by extreme sparsity (2.9%)
- BTC_5m: correct_side=62.9% — blocked by fill mechanics (structural, requires engine redesign)

---

## Blacklist Summary

### Per-pair blacklists

- **BTC_5m**: FROZEN PERMANENT. All parameter experiments blocked indefinitely.
  Fill mechanics structural barrier (not outcome sparsity). P(both sides fill)=5.6%.
- **BTC_15m**: FROZEN. gate=0.08/0.04/0.0 all fail; outcome sparsity dominant (7.9%).
- **BTC_1h**: FROZEN. gate=0.08/0.04/0.0 all fail; extreme outcome sparsity (2.9%).
- **ETH_5m**: FROZEN. gate series exhausted; DD=28.7% near 30% kill threshold; P=5.8% fill mechanics.
- **ETH_15m**: FROZEN. gate series exhausted; outcome sparsity (9.9%). Strong signal — most promising
  candidate to unfreeze IF outcome resolution engineering delivers more live-log data.
- **ETH_1h**: pace_urgency_lo 0.25/0.30 (DEAD — inert on thin data), fill_ticks=2 (regression).
  onesided above 5, skip 0.40, risk_ceil 0.20, bar_budget 250/300, conviction_market_start (GLOBAL).
- **SOL_5m**: FROZEN. fill mechanics dominant (fill_rate=23.1%, P=5.3%).
- **SOL_15m**: FROZEN. correct_side=45.5% both measurements < 50%.
- **SOL_1h**: FROZEN. gate series exhausted; outcome sparsity (8.6%).
- **XRP_5m**: FROZEN PERMANENT. fill_rate=15.6% structural floor.
- **XRP_15m**: FROZEN. correct_side declining (53.7%->50.0%->49.2%); gate exhausted.
- **XRP_1h**: skip 0.45/0.55, bar_budget 300, risk_ceil 0.20,
  pace_urgency_lo 0.30 (COLLAPSE), pace_urgency_lo 0.45 (D), max_onesided_cost 2.0 (COLLAPSE).
  PACE_LO FLOOR: 0.35 confirmed. fill_ticks=1 superseded (KEEP at fill_ticks=2).

### Global Blacklist

- **conviction_market_start**: GLOBALLY BLACKLISTED. Fails across ALL tested pairs.
- **magnitude_gate (all values 0.0/0.02/0.04/0.08)**: Exhausted for ALL pairs. Gate parameter is
  irrelevant for any pair with outcome sparsity or fill mechanics bottleneck.
- **pace_urgency_lo < 0.35**: GLOBALLY BLACKLISTED. COLLAPSE mechanism confirmed on XRP_1h.
  ETH_1h: lever dead entirely. Do NOT test below 0.35 on any pair.
- **max_onesided_cost < 3.0**: BLACKLISTED. $2 causes collapse on XRP_1h. Minimum test = 3.5.
- **Any experiment on frozen pairs**: BLOCKED until auditor lifts freeze or structural fix deployed.

### Structural Engineering Recommendations (for future audit/development)

1. **Outcome resolution rate**: Current 8-14% for 1h pairs is the binding long-term constraint.
   Engineering fix: ingest more live-log data OR implement OHLC-based outcome resolution.
   This would unfreeze ETH_15m (correct_side=71.2%, strong signal) and potentially BTC_1h/SOL_1h.
   Priority: HIGH — would add 2-4 active experimental pairs.
2. **Fill mechanics for 5m pairs**: P(both sides fill in bar)=5.6% for BTC_5m is structural.
   Engineering fix: increase fill_ticks substantially (e.g., 5-10), widen spread_offset, or use
   market orders for small sizes. Current fill_ticks lever (1->2) is insufficient for 5m.
   The 5m pairs require engine redesign, not parameter tuning.
3. **Dataset growth**: ETH_1h/XRP_1h only have 34-36 bars. Statistical power is very low.
   Most parameter changes produce undetectable differences on <10 resolved outcomes.
   Dataset grows naturally at 1 bar/hour — 6 months = ~4,380 bars, >500 outcomes at current rate.
