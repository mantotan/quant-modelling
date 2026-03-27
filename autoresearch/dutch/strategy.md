# Dutch Strategy
Updated: after iteration 103 (2026-03-27T01:00:00Z) — STRATEGIST rotation 9 post-run analysis

## Summary

Rotations 8-9 (iters 80-103): 1 active KEEP (ETH_1h spread_offset=0.005 iter97, marginal +$0.01/bar).
XRP_1h spread_offset DISCARD (iter103: pair_cost regressed 0.785->0.818, profit -0.08->-0.21).
Rotation 9 ends with ETH_1h holding at pair_cost=0.577, profit=+$0.19/bar — still the best active pair.

**KEEP rate rotations 8-9: 1/2 active experiments = 50%** (rotation 9 recovered from R8 0-KEEP streak)
**Cumulative KEEP rate: 4 KEEPs out of ~17 non-baseline active experiments = 23.5%**

Max_chase is the confirmed next lever for BOTH active pairs (ETH_1h and XRP_1h).
User directive confirmed: run max_chase 2->3 on ETH_1h and XRP_1h in rotation 10.

Spread_offset divergence confirmed: ETH_1h benefits from 0.005 (marginal KEEP), XRP_1h does NOT
(wider natural spread in XRP market means tighter offset reduces fill rate). Spread_offset floors:
- ETH_1h: 0.005 (now active in best_knobs)
- XRP_1h: 0.01 (floor confirmed iter103)

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

## ETH_1h (pair_cost=0.577, KEEP rate 3/9 active experiments=33%, max_dd=11.2%)

### Status: ACTIVE — STRONG CANDIDATE (well below trader_a pair_cost target 0.85)

Full trajectory:
- Iter 6 (R1): cost=0.000, zero pairs at gate=0.08
- Iter 18 (R2 baseline): cost=0.594, matched=2.0%, profit=-$0.06/bar, DD=13.8%
- Iter 29 (R3 pace=0.25): DISCARD — identical to baseline (pace lever inert on thin data)
- Iter 41 (R4 baseline pace=0.35): cost=0.594, matched=2.0%, profit=+$0.08/bar, DD=7.6%
- Iter 53 (R5 pace=0.30): DISCARD — identical to baseline (pace lever confirmed inert)
- Iter 66 (R6 fill_ticks=2): DISCARD — profit regression -$0.04/bar; DD=13.8% exceeds threshold
- Iter 78 (R7 chase_threshold=0.05): KEEP — pair_cost=0.577 (-0.017), profit=+$0.18/bar (+$0.10)
- Iter 85 (R8 pace_urgency_hi=1.5): DISCARD — ALL metrics IDENTICAL; pace inert
- Iter 97 (R9 spread_offset=0.005): KEEP — profit=+$0.19/bar (+$0.01/bar marginal), pair_cost stable

ETH_1h current KEEP state (iter 97): pair_cost=0.577, profit=+$0.19/bar, DD=11.2%, matched=1.9%
PACE CATEGORY EXHAUSTED: pace_urgency_lo (iters 29/53) and pace_urgency_hi (iter 85) all inert.
SPREAD_OFFSET at floor: 0.005 = active in both knobs files (marginal KEEP).

**Current knobs state:**
- knobs_ETH_1h.json: fill_ticks=1, chase_threshold=0.05, spread_offset=0.005, max_chase=2 (experiment: change to 3)
- best_knobs_ETH_1h.json: fill_ticks=1, chase_threshold=0.05, spread_offset=0.005, max_chase=2
- Both files aligned. Next experiment: stage max_chase=3 in knobs_ETH_1h.json only.

**Priority queue for rotation 10:**
1. **max_chase 2->3 EXPERIMENT** — allow 3 chase attempts per order (vs 2 currently)
   - Hypothesis: an extra chase attempt may recover more fills after brief adverse price moves
     in thin 1h ETH market. Current chase_threshold=0.05 allows chasing up to 5% movement —
     max_chase=3 lets the fill simulator make one more attempt at recovering fill price.
   - Stage: modify fill_simulator.max_chase=3 in knobs_ETH_1h.json only (not best_knobs)
   - Baseline ref: pair_cost=0.577, profit=+$0.19/bar, DD=11.2%, matched=1.9% (iter 97)
   - Accept KEEP if: matched_ratio > 1.9% OR avg_profit > +$0.19/bar OR pair_cost < 0.577
   - DISCARD if: pair_cost > 0.65 OR DD > 13% OR matched_ratio < 1.5%
   - If KEEP: update best_knobs_ETH_1h.json with max_chase=3; next = cancel_distance 0.05->0.03
   - If DISCARD: restore max_chase=2; next = cancel_distance 0.05->0.03
2. If max_chase DISCARD: cancel_distance 0.05->0.03 (tighter cancellation = orders live longer)
   - Rationale: reducing cancel distance keeps limit orders near midpoint longer before cancellation
   - Accept KEEP if: matched_ratio > 1.9% OR avg_profit > +$0.19/bar
3. If 3 consecutive DISCARDs on fill-sim sub-params (spread_offset KEEP marginal, max_chase DISCARD,
   cancel_distance DISCARD): escalate to auditor — ETH_1h at structural floor
   NOTE: ETH_1h profit=+$0.19/bar already beats trader_a target (>$0). Primary gap: matched_ratio=1.9%
   is too low for deployment confidence. Need >5% matched_ratio for statistical significance.
   At current trajectory, fill_sim tweaks yield <5% improvements each — nearing parametric floor.

Blacklist (cumulative): pace_urgency_lo 0.25/0.30 (DEAD — inert on thin data), fill_ticks=2 (regression
iter 66), pace_urgency_hi=1.5 (inert iter 85), onesided above 5, skip 0.40, risk_ceil 0.20,
bar_budget 250/300, conviction_market_start (GLOBAL).
PACE CATEGORY CLOSED FOR ETH_1h — all pace levers tested (lo 0.25/0.30, hi 1.5). None effective.
Remaining fill-sim sub-params: max_chase (2->3 next), cancel_distance (if needed).

---

## XRP_1h (pair_cost=0.785, KEEP rate 2/8 active experiments=25%, max_dd=8.9%)

### Status: ACTIVE — IMPROVING (pair_cost beats trader_a target; 2 consecutive KEEPs in R6-R7)

Full trajectory:
- Iter 12 (R1 baseline): cost=0.855, matched=3.6%, profit=N/A, DD=3.1%
- Iter 23 (R2 baseline): cost=0.812, matched=4.2%, profit=+$0.10/bar, DD=8.0%
- Iter 35 (R3 pace=0.30): DISCARD — COLLAPSE (0% matched vs 4.2%); PACE FLOOR 0.35 CONFIRMED
- Iter 47 (R4 baseline onesided=5.0): cost=0.812, matched=4.1%, profit=-$0.14/bar, DD=9.8%
- Iter 59 (R5 onesided=2.0): DISCARD — COLLAPSE (0% matched); onesided floor confirmed >3.0
- Iter 72 (R6 fill_ticks=2): KEEP — cost=0.812 stable, profit=-$0.13/bar (+$0.01 improvement)
- Iter 79 (R7 chase_threshold=0.05): KEEP — cost=0.785 (-3.3%), profit=-$0.08/bar (+$0.05)
- Iter 91 (R8 onesided=3.5): DISCARD — pair_cost stable 0.785, profit REGRESSED -0.26/bar
- Iter 103 (R9 spread_offset=0.005): DISCARD — pair_cost REGRESSED 0.818 (+0.033), profit -0.21/bar

XRP_1h KEEP state (iter 79): pair_cost=0.785, profit=-$0.08/bar, DD=8.9%, matched=4.0%
Two consecutive KEEPs in R6-R7 confirm XRP_1h responsive to fill-sim tuning.
R8-R9 both DISCARD: onesided floor at 5.0 confirmed, spread_offset floor at 0.01 confirmed.

**Current knobs state:**
- knobs_XRP_1h.json: fill_ticks=2, chase_threshold=0.05, max_chase=2, spread_offset=0.01 (restored post-DISCARD iter103)
  conviction_buy_skip=0.5 (knobs) vs 0.5 (best_knobs) — aligned.
- best_knobs_XRP_1h.json: max_onesided_cost=5.0, fill_ticks=2, chase_threshold=0.05, spread_offset=0.01
- Next experiment: stage max_chase=3 in knobs_XRP_1h.json only.

**Priority queue for rotation 10:**
1. **max_chase 2->3 EXPERIMENT** — allow 3 chase attempts per order
   - Hypothesis: same as ETH_1h — extra chase attempt may recover fills after price movement
     in XRP_1h sparse window. XRP_1h fills at 65-70% fill rate, up from 69% at KEEP state.
     max_chase=3 gives one more attempt to fill at slightly moved price.
   - Stage: modify fill_simulator.max_chase=3 in knobs_XRP_1h.json only (not best_knobs)
   - Baseline ref: pair_cost=0.785, profit=-$0.08/bar, DD=8.9%, matched=4.0% (iter 79, KEEP state)
   - Accept KEEP if: pair_cost < 0.785 OR avg_profit > -$0.08/bar
   - IMMEDIATE DISCARD if: matched_ratio < 2.0% (collapse mechanism) OR DD > 15%
   - If KEEP: update best_knobs_XRP_1h.json with max_chase=3; next = cancel_distance 0.05->0.03
   - If DISCARD (not collapse): confirm max_chase floor at 2; next = cancel_distance 0.05->0.03
   - If COLLAPSE (matched_ratio < 2.0%): restore immediately; confirm fill_sim exhausted
2. If max_chase DISCARD: cancel_distance 0.05->0.03 (tighter cancellation = orders live longer)
   - Accept KEEP if: pair_cost < 0.785 OR avg_profit > -$0.08/bar
3. If 2 consecutive DISCARDs on fill-sim (max_chase + cancel_distance): escalate to auditor
   — XRP_1h fill-sim sub-params exhausted after spread_offset(D) + onesided(D) + 2 fill-sim DISCARDs
   NOTE: XRP_1h profit=-$0.08/bar improving but still negative. KEEP rate improvement required.
   At current improvement rate (+$0.05/bar per KEEP), 2 more KEEPs would reach profitability.
   After fill-sim exhaustion, no known levers remain for XRP_1h without engine redesign.

Blacklist (cumulative): skip 0.45/0.55, bar_budget 300, risk_ceil 0.20,
pace_urgency_lo 0.30 (COLLAPSE iter 35), pace_urgency_lo 0.45 (D pre-RESET),
max_onesided_cost 2.0 (COLLAPSE iter 59), max_onesided_cost 3.5 (DISCARD iter 91 — profit regression),
fill_ticks=1 superseded (KEEP at fill_ticks=2), chase_threshold=0.03 superseded (KEEP at 0.05),
spread_offset=0.005 (DISCARD iter103 — fill rate reduced in wider-spread XRP market).
PACE_LO FLOOR: 0.35 confirmed. ONESIDED FLOOR: 5.0 confirmed. SPREAD_OFFSET FLOOR: 0.01 confirmed.

---

## Rotation 10 Execution Plan (priority order)

1. **BTC_5m** — SKIP (FROZEN PERMANENT — fill mechanics structural, P=5.6%)
2. **BTC_15m** — SKIP (FROZEN — 3 consecutive zero-pair baselines, outcome sparsity 7.9%)
3. **BTC_1h** — SKIP (FROZEN — extreme sparsity 2.9%)
4. **ETH_5m** — SKIP (FROZEN — DD=28.7% near kill threshold, fill mechanics structural P=5.8%)
5. **ETH_15m** — SKIP (FROZEN — gate series exhausted, outcome sparsity 9.9%)
6. **ETH_1h** — **max_chase 2->3 EXPERIMENT** (stage max_chase=3 in knobs_ETH_1h.json fill_simulator only)
7. **SOL_5m** — SKIP (FROZEN — outcome sparsity 6.7%, DD elevated, fill mechanics P=5.3%)
8. **SOL_15m** — SKIP (FROZEN — correct_side=45.5% < 50%)
9. **SOL_1h** — SKIP (FROZEN — outcome sparsity 8.6%)
10. **XRP_5m** — SKIP (FROZEN PERMANENT)
11. **XRP_15m** — SKIP (FROZEN — correct_side declining, gate exhausted)
12. **XRP_1h** — **max_chase 2->3 EXPERIMENT** (stage max_chase=3 in knobs_XRP_1h.json fill_simulator only)

NOTE: Rotation 10 starts at BTC_5m (pair_index=0). dispatch_state.json shows current_pair=BTC_5m,
pair_index=0. Next researcher dispatch should advance through frozen SKIPs to ETH_1h (index 5).

**Rotation 10 success criteria:**
- Minimum 1 KEEP on either max_chase ETH_1h or max_chase XRP_1h
- If ETH_1h max_chase KEEP: matched_ratio must increase to confirm extra chase is helping
- If XRP_1h max_chase KEEP: profit must improve > -$0.08/bar threshold (pair_cost<0.785 is stretch goal)
- If both DISCARD: both pairs approaching fill-sim parametric floor (spread_offset exhausted both,
  max_chase exhausted both) — escalate both to auditor for structural floor assessment after R10
- CRITICAL: do NOT test any globally blacklisted params; do NOT unfreeze frozen pairs without auditor

**Post-rotation 10 outlook:**
- ETH_1h remaining levers: max_chase, cancel_distance — 2 experiments before auditor escalation
- XRP_1h remaining levers: max_chase, cancel_distance — 2 experiments before auditor escalation
- If all fill-sim sub-params exhausted for both pairs: structural floor confirmed for both
  → auditor must assess whether engine redesign is needed or natural dataset growth is the fix
- Long-term: matched_ratio=1.9% (ETH) and 4.0% (XRP) are statistically insufficient for
  deployment confidence. Need >5% matched_ratio. At current trajectory, this requires structural change.

---

## Cross-Pair Observations

### Rotations 8-9 critical findings

**Spread_offset is pair-specific — not a universal lever:**
- ETH_1h: 0.005 = marginal KEEP (+$0.01/bar, noise floor region). ETH has tighter natural spread.
- XRP_1h: 0.005 = DISCARD (fill_rate -3.3pp, pair_cost +0.033). XRP has wider natural spread.
- Implication: limit placement offset must match the asset's natural bid-ask spread.
  ETH_1h tighter spread accommodates 0.005 offset; XRP_1h wider spread requires 0.01 minimum.

**Max_onesided_cost floor confirmed at 5.0 for XRP_1h (iter 91):**
- 3.5 was the midpoint between 5.0 (stable) and 2.0 (collapse).
- 3.5 showed profit regression (-0.08->-0.26) without collapse (3.9% matched stable).
- The regression at 3.5 means cost cap at $3.50 is binding at times, cutting pair formation quality.
- Floor is 5.0 — tighter onesided caps compress quality without enabling collapse avoidance.

**Fill-sim parameter space is nearly exhausted for both active pairs:**
| Param | ETH_1h | XRP_1h |
|-------|--------|--------|
| fill_ticks | 1 (baseline) | 2 (KEEP iter72) |
| chase_threshold | 0.05 (KEEP iter78) | 0.05 (KEEP iter79) |
| spread_offset | 0.005 (KEEP iter97) | 0.01 (floor iter103) |
| max_chase | 2->3 NEXT | 2->3 NEXT |
| cancel_distance | 0.05 (untested) | 0.05 (untested) |

Remaining fill-sim experiments: 2 each (max_chase + cancel_distance). After these, fill-sim category
is fully explored. Both pairs will need auditor assessment.

**Dataset bottleneck intensifying:**
- ETH_1h: ~36 bars, ~4-5 resolved outcomes. Experiments run on same tiny sample set.
- XRP_1h: ~37 bars, ~4-5 resolved outcomes. Same constraint.
- Both pairs' marginal improvements are likely within noise: +$0.01/bar on 4-5 outcomes = ~$0.04 total.
- Statistical power is insufficient for confident KEEP/DISCARD decisions at this dataset size.
- Natural growth: 1 bar/hour = 720 bars/30 days. 6 months adds ~4,380 bars.

---

## trader_a Benchmark Comparison (after rotation 9, iter 103)

| Pair | PairCost | Target | Gap | AvgProfit | MaxDD% | Status |
|------|----------|--------|-----|-----------|--------|--------|
| BTC_5m | 0.000 | < 0.85 | N/A | -$0.031/bar | 23.4% | FROZEN PERMANENT — fill mechanics (P=5.6%) |
| BTC_15m | 0.000 | < 0.85 | N/A | -$0.019/bar | 12.4% | FROZEN — outcome sparsity + zero pairs |
| BTC_1h | 0.000 | < 0.85 | N/A | -$0.032/bar | 3.9% | FROZEN — extreme sparsity (2.9%) |
| ETH_5m | 0.000 | < 0.85 | N/A | -$0.091/bar | 28.7% | FROZEN — DD WARNING, fill mechanics (P=5.8%) |
| ETH_15m | 0.000 | < 0.85 | N/A | +$0.158/bar | 7.1% | FROZEN — gate exhausted, strong signal wasted |
| ETH_1h | 0.577 | < 0.85 | -0.273 (BEATS) | +$0.190/bar | 11.2% | ACTIVE — max_chase=3 queued |
| SOL_5m | 0.000 | < 0.85 | N/A | +$0.135/bar | 23.2% | FROZEN — fill mechanics (P=5.3%) |
| SOL_15m | 0.567* | < 0.85 | N/A | -$0.270/bar | 19.8% | FROZEN — correct_side=45.5% < 50% |
| SOL_1h | 0.000 | < 0.85 | N/A | -$0.110/bar | 8.3% | FROZEN — outcome sparsity (8.6%) |
| XRP_5m | N/A | < 0.85 | N/A | N/A | N/A | FROZEN PERMANENT — fill_rate=15.6% floor |
| XRP_15m | 0.950 | < 0.85 | +0.100 (FAILS) | -$0.240/bar | 20.5% | FROZEN — correct_side=49.2% declining |
| XRP_1h | 0.785 | < 0.85 | -0.065 (BEATS) | -$0.080/bar | 8.9% | ACTIVE — max_chase=3 queued |

*SOL_15m: artificially low pair_cost (near-zero pairs)

**Progress since last strategist (iter 90):**
- ETH_1h: profit improved +$0.18 -> +$0.19/bar (+5.6%), pair_cost stable 0.577.
  spread_offset=0.005 KEEP was marginal. Benchmark profit target ACHIEVED (>$0).
- XRP_1h: spread_offset DISCARD only. pair_cost held at 0.785 KEEP state from iter79.
  No new KEEPs for XRP_1h in rotations 8-9 (2 DISCARDs: onesided=3.5 + spread_offset=0.005).

Best performers (active, pair_cost beats target):
- ETH_1h: pair_cost=0.577 — BENCHMARK ACHIEVED. profit=+$0.19/bar POSITIVE. Needs matched_ratio >5%.
- XRP_1h: pair_cost=0.785 — BENCHMARK ACHIEVED. profit=-$0.08/bar negative, improvement stalled R8-R9.

---

## Blacklist Summary

### Per-pair blacklists

- **BTC_5m**: FROZEN PERMANENT. Fill mechanics structural barrier (P=5.6%). No experiments.
- **BTC_15m**: FROZEN. Gate+onesided exhausted; outcome sparsity dominant (7.9%).
- **BTC_1h**: FROZEN. Gate series exhausted; extreme outcome sparsity (2.9%).
- **ETH_5m**: FROZEN. Gate exhausted; DD=28.7% near 30% kill threshold; P=5.8% fill mechanics.
- **ETH_15m**: FROZEN. Gate exhausted; outcome sparsity (9.9%). Strong signal — most promising
  candidate to unfreeze IF outcome resolution engineering delivers more live-log data.
- **ETH_1h**: pace_urgency_lo 0.25/0.30, fill_ticks=2, pace_urgency_hi=1.5, onesided>5, skip 0.40,
  risk_ceil 0.20, bar_budget 250/300, conviction_market_start (GLOBAL).
  PACE CATEGORY CLOSED. fill-sim remaining: max_chase (3 next), cancel_distance.
- **SOL_5m**: FROZEN. Fill mechanics dominant (fill_rate=23.1%, P=5.3%).
- **SOL_15m**: FROZEN. correct_side=45.5% both measurements < 50%.
- **SOL_1h**: FROZEN. Gate series exhausted; outcome sparsity (8.6%).
- **XRP_5m**: FROZEN PERMANENT. fill_rate=15.6% structural floor.
- **XRP_15m**: FROZEN. correct_side declining (53.7%->50.0%->49.2%); gate exhausted.
- **XRP_1h**: skip 0.45/0.55, bar_budget 300, risk_ceil 0.20,
  pace_urgency_lo 0.30 (COLLAPSE iter 35), max_onesided_cost 2.0 (COLLAPSE iter 59),
  max_onesided_cost 3.5 (DISCARD iter 91 — profit regression at tighter cap),
  fill_ticks=1 superseded (KEEP at fill_ticks=2), chase_threshold=0.03 superseded (KEEP at 0.05),
  spread_offset=0.005 (DISCARD iter103 — wider XRP natural spread requires 0.01 floor).
  PACE_LO FLOOR: 0.35. ONESIDED FLOOR: 5.0. SPREAD_OFFSET FLOOR: 0.01.
  fill-sim remaining: max_chase (3 next), cancel_distance.

### Global Blacklist

- **conviction_market_start**: GLOBALLY BLACKLISTED. Fails across ALL tested pairs.
- **magnitude_gate (all values 0.0/0.02/0.04/0.08)**: Exhausted for ALL pairs.
- **pace_urgency_lo < 0.35**: GLOBALLY BLACKLISTED. COLLAPSE confirmed on XRP_1h.
- **max_onesided_cost < 3.5**: BLACKLISTED for XRP_1h. $2 causes collapse. $3.5 causes profit regression.
- **Any experiment on frozen pairs**: BLOCKED until auditor lifts freeze or structural fix deployed.
- **Pace levers on thin 1h datasets**: Empirically confirmed inert (<10 resolved outcomes). Dead category.
- **spread_offset 0.005 on XRP_1h**: BLACKLISTED — fill_rate reduction confirmed; floor=0.01 for XRP.

### Structural Engineering Recommendations (for future audit/development)

1. **Outcome resolution rate**: Current 8-14% for 1h pairs is the binding long-term constraint.
   Engineering fix: ingest more live-log data OR implement OHLC-based outcome resolution.
   This would unfreeze ETH_15m (correct_side=71.2%, strong signal) and potentially BTC_1h/SOL_1h.
   Priority: HIGH — would add 2-4 active experimental pairs.
2. **Fill mechanics for 5m pairs**: P(both sides fill in bar)=5.6% for BTC_5m is structural.
   Engineering fix: increase fill_ticks substantially (e.g., 5-10), widen spread_offset, or use
   market orders for small sizes. The 5m pairs require engine redesign, not parameter tuning.
3. **Matched ratio bottleneck**: ETH_1h 1.9%, XRP_1h 4.0% — too low for deployment confidence.
   No parameter tweak can fix this — only time (data accumulation) or structural redesign.
4. **Dataset growth**: ETH_1h/XRP_1h only ~36-37 bars. Statistical power is very low.
   Most parameter changes produce undetectable differences on <5 resolved outcomes.
   Natural growth at 1 bar/hour — 6 months = ~4,380 bars, >500 outcomes at current rate.
   Fill-sim experiments at current stage are largely within statistical noise.
