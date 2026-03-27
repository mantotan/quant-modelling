# Dutch Strategy
Updated: after iteration 115 (2026-03-27T09:15:00Z) — STRATEGIST rotation 10 post-run analysis

## Summary

Rotation 10 (iters 104-115): 1 KEEP (XRP_1h max_chase=3, iter115), 1 DISCARD (ETH_1h max_chase=3, iter109).
**KEEP rate rotation 10: 1/2 active experiments = 50%** (matches rotation 9's 50%).
**Cumulative KEEP rate: 6 KEEPs out of ~21 non-baseline active experiments = 28.6%** (up from 23.5% after R9).

XRP_1h max_chase=3 is a genuine KEEP: profit improved -$0.08 -> -$0.026/bar (+67.5%), fill_rate up 5.3pp.
ETH_1h max_chase=3 is inert: all metrics identical to iter97 KEEP state. max_chase floor at 2 confirmed.

Both pairs have exactly 1 fill-sim lever remaining: cancel_distance 0.05->0.03.
User directive: run cancel_distance=0.03 on ETH_1h AND XRP_1h in rotation 11.
If both DISCARD: escalate both to auditor for structural floor assessment.

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

## ETH_1h (pair_cost=0.577, KEEP rate 3/10 active experiments=30%, max_dd=11.2%)

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
- Iter 109 (R10 max_chase=3): DISCARD — ALL METRICS IDENTICAL; fill_rate 86% too high for extra
  chase to trigger; max_chase floor confirmed at 2 for ETH_1h

ETH_1h current KEEP state (iter 97): pair_cost=0.577, profit=+$0.19/bar, DD=11.2%, matched=1.9%
PACE CATEGORY EXHAUSTED: pace_urgency_lo (iters 29/53) and pace_urgency_hi (iter 85) all inert.
SPREAD_OFFSET at floor: 0.005 = active in both knobs files (marginal KEEP).
MAX_CHASE floor confirmed: 2 (iter 109 max_chase=3 inert — fill_rate already 86% leaves no room).

**Current knobs state:**
- knobs_ETH_1h.json: fill_ticks=1, chase_threshold=0.05, spread_offset=0.005, max_chase=2,
  cancel_distance=0.05 (experiment: change to 0.03)
- best_knobs_ETH_1h.json: same as above (max_chase=2 is floor; best_knobs unchanged after DISCARD)
- Next experiment: stage cancel_distance=0.03 in knobs_ETH_1h.json only (not best_knobs).

**Priority queue for rotation 11:**
1. **cancel_distance 0.05->0.03 EXPERIMENT** — tighter cancellation keeps orders near midpoint longer
   - Hypothesis: reducing cancel distance from 5% to 3% means limit orders stay in queue longer
     before being cancelled due to adverse price movement. On thin ETH_1h dataset, this may
     rescue marginal fills that currently get cancelled just before price reverts.
     Current ETH_1h matched_ratio=1.9% is very low; even a small matched_ratio improvement
     would be meaningful. fill_rate=86% suggests fills are happening — but matched_ratio=1.9%
     means only ~1 in 50 bars results in a matched pair. cancel_distance tightening may help.
   - Stage: modify fill_simulator.cancel_distance=0.03 in knobs_ETH_1h.json only (not best_knobs)
   - Baseline ref: pair_cost=0.577, profit=+$0.19/bar, DD=11.2%, matched=1.9% (iter 97, KEEP state)
   - Accept KEEP if: matched_ratio > 1.9% OR avg_profit > +$0.19/bar OR pair_cost < 0.577
   - DISCARD if: pair_cost > 0.65 OR DD > 13% OR matched_ratio < 1.5% (collapse)
   - If KEEP: update best_knobs_ETH_1h.json with cancel_distance=0.03
   - If DISCARD: restore cancel_distance=0.05; FILL-SIM CATEGORY EXHAUSTED for ETH_1h
     → escalate to auditor for structural floor assessment (all fill-sim sub-params tested)
2. If cancel_distance DISCARD: **ESCALATE TO AUDITOR**
   - ETH_1h fill-sim sub-params fully exhausted:
     fill_ticks=1 (floor), chase_threshold=0.05 (KEEP iter78), spread_offset=0.005 (marginal KEEP iter97),
     max_chase=2 (floor iter109), cancel_distance=0.05 (tested next)
   - Profit=+$0.19/bar BEATS trader_a target. Pair_cost=0.577 BEATS target. Gap: matched_ratio=1.9%.
   - After fill-sim exhaustion: auditor must assess whether dataset growth or engine redesign can
     push matched_ratio to >5% for deployment confidence.

Blacklist (cumulative): pace_urgency_lo 0.25/0.30 (DEAD — inert on thin data), fill_ticks=2 (regression
iter 66), pace_urgency_hi=1.5 (inert iter 85), onesided above 5, skip 0.40, risk_ceil 0.20,
bar_budget 250/300, conviction_market_start (GLOBAL), max_chase=3 (INERT iter109 — fill_rate too high).
PACE CATEGORY CLOSED FOR ETH_1h — all pace levers tested (lo 0.25/0.30, hi 1.5). None effective.
MAX_CHASE FLOOR: 2 (3 inert, fill_rate already 86%).
Remaining fill-sim sub-param: cancel_distance only.

---

## XRP_1h (pair_cost=0.785, KEEP rate 3/9 active experiments=33%, max_dd=10.58%)

### Status: ACTIVE — IMPROVING (pair_cost beats trader_a target; 3rd KEEP from fill-sim tuning)

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
- Iter 115 (R10 max_chase=3): KEEP — profit=-$0.026/bar IMPROVED vs -$0.08/bar (+$0.054/bar=+67.5%);
  fill_rate 69.0%->74.3% (+5.3pp); extra chase attempt recovering fills after adverse price moves;
  pair_cost=0.785 stable; matched_ratio=3.9% stable; max_dd=10.58% safe

XRP_1h current KEEP state (iter 115): pair_cost=0.785, profit=-$0.026/bar, DD=10.58%, matched=3.9%
Three KEEPs (iters 72, 79, 115) confirm XRP_1h is the most fill-sim-responsive pair in the system.
R8-R9 both DISCARD: onesided floor at 5.0 confirmed, spread_offset floor at 0.01 confirmed.
R10: max_chase=3 KEEP — fills improving, profit trajectory accelerating toward breakeven.
At current improvement rate (+$0.054/bar per KEEP), 1-2 more KEEPs could reach profitability.

**Current knobs state:**
- knobs_XRP_1h.json: fill_ticks=2, chase_threshold=0.05, max_chase=3, spread_offset=0.01,
  cancel_distance=0.05 (experiment: change to 0.03)
- best_knobs_XRP_1h.json: fill_ticks=2, chase_threshold=0.05, max_chase=3, spread_offset=0.01,
  cancel_distance=0.05 (both files already have max_chase=3 per iter115 KEEP)
- Next experiment: stage cancel_distance=0.03 in knobs_XRP_1h.json only (not best_knobs).

**Priority queue for rotation 11:**
1. **cancel_distance 0.05->0.03 EXPERIMENT** — tighter cancellation keeps orders near midpoint longer
   - Hypothesis: XRP_1h fill_rate improved to 74.3% with max_chase=3. cancel_distance tightening
     may recover additional fills in the tail of the distribution — orders that currently get cancelled
     at the 5% adverse price threshold but would have filled if they survived to 3%.
     XRP_1h fill_rate at 74% is NOT as saturated as ETH_1h at 86%, so there is more headroom
     for cancel_distance to make a difference on XRP_1h than on ETH_1h.
   - Stage: modify fill_simulator.cancel_distance=0.03 in knobs_XRP_1h.json only (not best_knobs)
   - Baseline ref: pair_cost=0.785, profit=-$0.026/bar, DD=10.58%, matched=3.9% (iter 115, KEEP state)
   - Accept KEEP if: pair_cost < 0.785 OR avg_profit > -$0.026/bar
   - IMMEDIATE DISCARD if: matched_ratio < 2.0% (collapse mechanism) OR DD > 15%
   - If KEEP: update best_knobs_XRP_1h.json with cancel_distance=0.03
   - If DISCARD (not collapse): confirm cancel_distance floor at 0.05; FILL-SIM EXHAUSTED for XRP_1h
     → escalate to auditor for structural floor assessment
   - If COLLAPSE (matched_ratio < 2.0%): restore immediately; fill-sim category exhausted
2. If cancel_distance DISCARD: **ESCALATE TO AUDITOR**
   - XRP_1h fill-sim sub-params fully exhausted:
     fill_ticks=2 (KEEP iter72), chase_threshold=0.05 (KEEP iter79), max_chase=3 (KEEP iter115),
     spread_offset=0.01 (floor iter103), cancel_distance (tested next)
   - profit=-$0.026/bar: close to breakeven. pair_cost=0.785 BEATS target.
   - After fill-sim exhaustion: auditor must assess — is further improvement possible?
     At -$0.026/bar with 3 fill-sim KEEPs, XRP_1h is functionally at structural improvement ceiling
     for fill mechanics. Non-fill-sim levers (pace, onesided) are exhausted. Engine redesign needed.

Blacklist (cumulative): skip 0.45/0.55, bar_budget 300, risk_ceil 0.20,
pace_urgency_lo 0.30 (COLLAPSE iter 35), pace_urgency_lo 0.45 (D pre-RESET),
max_onesided_cost 2.0 (COLLAPSE iter 59), max_onesided_cost 3.5 (DISCARD iter 91 — profit regression),
fill_ticks=1 superseded (KEEP at fill_ticks=2), chase_threshold=0.03 superseded (KEEP at 0.05),
spread_offset=0.005 (DISCARD iter103 — wider XRP natural spread requires 0.01 floor).
PACE_LO FLOOR: 0.35 confirmed. ONESIDED FLOOR: 5.0 confirmed. SPREAD_OFFSET FLOOR: 0.01 confirmed.
MAX_CHASE: 3 is ACTIVE KEEP (do NOT revert). Remaining fill-sim sub-param: cancel_distance only.

---

## Rotation 11 Execution Plan (priority order)

1. **BTC_5m** — SKIP (FROZEN PERMANENT — fill mechanics structural, P=5.6%)
2. **BTC_15m** — SKIP (FROZEN — 3 consecutive zero-pair baselines, outcome sparsity 7.9%)
3. **BTC_1h** — SKIP (FROZEN — extreme sparsity 2.9%)
4. **ETH_5m** — SKIP (FROZEN — DD=28.7% near kill threshold, fill mechanics structural P=5.8%)
5. **ETH_15m** — SKIP (FROZEN — gate series exhausted, outcome sparsity 9.9%)
6. **ETH_1h** — **cancel_distance 0.05->0.03 EXPERIMENT** (stage cancel_distance=0.03 in knobs_ETH_1h.json only)
7. **SOL_5m** — SKIP (FROZEN — outcome sparsity 6.7%, DD elevated, fill mechanics P=5.3%)
8. **SOL_15m** — SKIP (FROZEN — correct_side=45.5% < 50%)
9. **SOL_1h** — SKIP (FROZEN — outcome sparsity 8.6%)
10. **XRP_5m** — SKIP (FROZEN PERMANENT)
11. **XRP_15m** — SKIP (FROZEN — correct_side declining, gate exhausted)
12. **XRP_1h** — **cancel_distance 0.05->0.03 EXPERIMENT** (stage cancel_distance=0.03 in knobs_XRP_1h.json only)

NOTE: dispatch_state.json pair_index=0 (BTC_5m) after auditor ran at iter 115 (XRP_1h).
Next researcher dispatch should start from BTC_5m (index=0), skip frozen pairs, advance to ETH_1h (index=5),
run cancel_distance experiment, then continue to XRP_1h (index=11).

**Rotation 11 success criteria:**
- At least 1 KEEP on either cancel_distance ETH_1h or cancel_distance XRP_1h
- If ETH_1h cancel_distance KEEP: matched_ratio must increase >1.9% (primary gap for ETH_1h)
- If XRP_1h cancel_distance KEEP: profit must improve > -$0.026/bar (pair_cost<0.785 is stretch goal)
- If BOTH DISCARD: BOTH pairs at fill-sim parametric floor — escalate to auditor immediately

**Fill-sim parameter space status after rotation 10:**
| Param | ETH_1h | XRP_1h |
|-------|--------|--------|
| fill_ticks | 1 (baseline floor) | 2 (KEEP iter72) |
| chase_threshold | 0.05 (KEEP iter78) | 0.05 (KEEP iter79) |
| spread_offset | 0.005 (KEEP iter97) | 0.01 (floor iter103) |
| max_chase | 2 (floor iter109 — inert) | 3 (KEEP iter115 — +67.5% profit) |
| cancel_distance | 0.03 NEXT (R11) | 0.03 NEXT (R11) |

**Post-rotation 11 outlook:**
- Both pairs: cancel_distance is the FINAL fill-sim sub-param. After R11, fill-sim is fully explored.
- ETH_1h: profit=+$0.19/bar already positive. Primary concern is matched_ratio=1.9% too low for
  deployment confidence (need >5%). Dataset has ~36 bars, ~4-5 outcomes. Statistical floor reached.
- XRP_1h: profit=-$0.026/bar approaching breakeven. 3 consecutive fill-sim KEEPs show strong
  fill-sim responsiveness. cancel_distance is a genuine candidate given 74% fill_rate (not saturated).
- If both cancel_distance DISCARD: auditor should formally assess structural floors and either
  (a) declare both pairs ready for limited deployment at current performance levels, or
  (b) recommend waiting for dataset growth (720 bars/month natural accumulation), or
  (c) recommend engine-level redesign to improve matched_ratio.

---

## Cross-Pair Observations

### Rotations 9-10 critical findings

**max_chase is pair-specific — fill_rate saturation determines effectiveness:**
- ETH_1h: max_chase=3 INERT (iter109). fill_rate=86% means most orders fill on 1st/2nd attempt.
  Extra chase never triggers. max_chase floor at 2 for ETH_1h.
- XRP_1h: max_chase=3 KEEP (iter115). fill_rate=69%->74.3% (+5.3pp). fill_rate at 69% had room
  to absorb extra chase attempts. XRP_1h benefits; ETH_1h does not.
- General rule: max_chase improvement requires fill_rate < ~80% at baseline. ETH_1h too high,
  XRP_1h in the right range.

**cancel_distance asymmetry prediction:**
- XRP_1h is MORE likely to benefit from cancel_distance tightening than ETH_1h because:
  1. fill_rate=74% vs ETH_1h 86% — more room to recover fills via longer order survival
  2. XRP market has wider natural spread — cancel_distance of 5% may be cancelling orders
     that would fill on slight reversal; 3% keeps them in queue longer without sacrificing too much
  3. XRP_1h shows consistent fill-sim responsiveness (3 KEEPs from fill-sim vs ETH_1h 2 KEEPs)
- ETH_1h cancel_distance benefit is speculative. fill_rate 86% already high. Main hope is
  matched_ratio improvement (1.9% -> target 2.5%+), not profit improvement.

**Divergence in fill-sim effectiveness:**
- ETH_1h: fill-sim peaked at chase_threshold=0.05 (iter78). Subsequent fill-sim experiments marginal.
  System is operating near ETH_1h fill mechanics ceiling.
- XRP_1h: fill-sim still yielding meaningful improvements (max_chase +67.5% in R10). System has
  more headroom. 3 fill-sim KEEPs vs 2 for ETH_1h reflects underlying market structure difference.
  XRP/USDT 1h options have wider bid-ask spreads, more variable fill probability — fill-sim tuning
  has more levers to exploit.

**Dataset bottleneck remains the binding long-term constraint:**
- ETH_1h: ~36 bars, ~4-5 resolved outcomes. ~28.6% outcome resolution rate.
- XRP_1h: ~37 bars, ~4-5 resolved outcomes (at iter79 KEEP state). ~10.8% resolution rate.
- Natural growth at 1 bar/hour = 720 bars/month. At current resolution rates:
  ETH_1h: ~205 new outcomes/month. XRP_1h: ~77 new outcomes/month.
- Statistical power for KEEP/DISCARD decisions at <5 outcomes is very low.
  Results within range: +$0.05/bar on 4-5 outcomes = ~$0.20-0.25 total absolute difference.
- Recommendation: even with fill-sim exhausted, 3-6 months of dataset accumulation would
  dramatically improve experimental statistical power and potentially unlock ETH_15m (71.2% correct_side).

---

## trader_a Benchmark Comparison (after rotation 10, iter 115)

| Pair | PairCost | Target | Gap | AvgProfit | MaxDD% | Status |
|------|----------|--------|-----|-----------|--------|--------|
| BTC_5m | 0.000 | < 0.85 | N/A | -$0.031/bar | 23.4% | FROZEN PERMANENT — fill mechanics (P=5.6%) |
| BTC_15m | 0.000 | < 0.85 | N/A | -$0.019/bar | 12.4% | FROZEN — outcome sparsity + zero pairs |
| BTC_1h | 0.000 | < 0.85 | N/A | -$0.032/bar | 3.9% | FROZEN — extreme sparsity (2.9%) |
| ETH_5m | 0.000 | < 0.85 | N/A | -$0.091/bar | 28.7% | FROZEN — DD WARNING, fill mechanics (P=5.8%) |
| ETH_15m | 0.000 | < 0.85 | N/A | +$0.158/bar | 7.1% | FROZEN — gate exhausted, strong signal wasted |
| ETH_1h | 0.577 | < 0.85 | -0.273 (BEATS) | +$0.190/bar | 11.2% | ACTIVE — cancel_distance=0.03 queued |
| SOL_5m | 0.000 | < 0.85 | N/A | +$0.135/bar | 23.2% | FROZEN — fill mechanics (P=5.3%) |
| SOL_15m | 0.567* | < 0.85 | N/A | -$0.270/bar | 19.8% | FROZEN — correct_side=45.5% < 50% |
| SOL_1h | 0.000 | < 0.85 | N/A | -$0.110/bar | 8.3% | FROZEN — outcome sparsity (8.6%) |
| XRP_5m | N/A | < 0.85 | N/A | N/A | N/A | FROZEN PERMANENT — fill_rate=15.6% floor |
| XRP_15m | 0.950 | < 0.85 | +0.100 (FAILS) | -$0.240/bar | 20.5% | FROZEN — correct_side=49.2% declining |
| XRP_1h | 0.785 | < 0.85 | -0.065 (BEATS) | -$0.026/bar | 10.58% | ACTIVE — cancel_distance=0.03 queued |

*SOL_15m: artificially low pair_cost (near-zero pairs)

**Progress since last strategist (iter 103):**
- ETH_1h: max_chase=3 DISCARD. Profit unchanged +$0.19/bar, pair_cost unchanged 0.577. No regression.
  ETH_1h holding at strong KEEP state. cancel_distance is final lever.
- XRP_1h: max_chase=3 KEEP (iter115). Profit improved -$0.08 -> -$0.026/bar (+$0.054/bar).
  fill_rate improved 69% -> 74.3%. Biggest single-iteration improvement for XRP_1h in R8-R10.
  XRP_1h approaching breakeven — cancel_distance may close the gap.

Best performers (active, pair_cost beats target):
- ETH_1h: pair_cost=0.577 — BENCHMARK ACHIEVED. profit=+$0.19/bar POSITIVE.
  Primary gap: matched_ratio=1.9% too low for deployment confidence. Need >5%.
- XRP_1h: pair_cost=0.785 — BENCHMARK ACHIEVED. profit=-$0.026/bar near-breakeven.
  3 fill-sim KEEPs confirm genuine responsiveness. cancel_distance may push to profitability.

**Trend assessment:**
- ETH_1h: Plateau reached. 3 fill-sim experiments post-R7 KEEP show marginal/zero improvement.
  +$0.01/bar from spread_offset (R9), 0/bar from max_chase (R10). System at ETH_1h structural floor.
- XRP_1h: Still improving. +$0.05/bar from max_chase R7->R8, +$0.054/bar from max_chase R10.
  XRP_1h trajectory is upward; cancel_distance represents a genuine probability of reaching breakeven.

---

## Blacklist Summary

### Per-pair blacklists

- **BTC_5m**: FROZEN PERMANENT. Fill mechanics structural barrier (P=5.6%). No experiments.
- **BTC_15m**: FROZEN. Gate+onesided exhausted; outcome sparsity dominant (7.9%).
- **BTC_1h**: FROZEN. Gate series exhausted; extreme outcome sparsity (2.9%).
- **ETH_5m**: FROZEN. Gate exhausted; DD=28.7% near 30% kill threshold; P=5.8% fill mechanics.
- **ETH_15m**: FROZEN. Gate exhausted; outcome sparsity (9.9%). Strong signal — most promising
  candidate to unfreeze IF outcome resolution engineering delivers more live-log data.
- **ETH_1h**: pace_urgency_lo 0.25/0.30, fill_ticks=2, pace_urgency_hi=1.5, max_chase=3 (inert),
  onesided>5, skip 0.40, risk_ceil 0.20, bar_budget 250/300, conviction_market_start (GLOBAL).
  PACE CATEGORY CLOSED. MAX_CHASE FLOOR=2. fill-sim remaining: cancel_distance only.
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
  PACE_LO FLOOR: 0.35. ONESIDED FLOOR: 5.0. SPREAD_OFFSET FLOOR: 0.01. MAX_CHASE=3 (ACTIVE KEEP).
  fill-sim remaining: cancel_distance only.

### Global Blacklist

- **conviction_market_start**: GLOBALLY BLACKLISTED. Fails across ALL tested pairs.
- **magnitude_gate (all values 0.0/0.02/0.04/0.08)**: Exhausted for ALL pairs.
- **pace_urgency_lo < 0.35**: GLOBALLY BLACKLISTED. COLLAPSE confirmed on XRP_1h.
- **max_onesided_cost < 3.5**: BLACKLISTED for XRP_1h. $2 causes collapse. $3.5 causes profit regression.
- **Any experiment on frozen pairs**: BLOCKED until auditor lifts freeze or structural fix deployed.
- **Pace levers on thin 1h datasets**: Empirically confirmed inert (<10 resolved outcomes). Dead category.
- **spread_offset 0.005 on XRP_1h**: BLACKLISTED — fill_rate reduction confirmed; floor=0.01 for XRP.
- **max_chase=3 on ETH_1h**: BLACKLISTED — inert at fill_rate=86% (iter109). Floor=2 for ETH_1h.

### Structural Engineering Recommendations (for future audit/development)

1. **Outcome resolution rate**: Current 8-14% for 1h pairs is the binding long-term constraint.
   Engineering fix: ingest more live-log data OR implement OHLC-based outcome resolution.
   This would unfreeze ETH_15m (correct_side=71.2%, strong signal) and potentially BTC_1h/SOL_1h.
   Priority: HIGH — would add 2-4 active experimental pairs.
2. **Fill mechanics for 5m pairs**: P(both sides fill in bar)=5.6% for BTC_5m is structural.
   Engineering fix: increase fill_ticks substantially (e.g., 5-10), widen spread_offset, or use
   market orders for small sizes. The 5m pairs require engine redesign, not parameter tuning.
3. **Matched ratio bottleneck**: ETH_1h 1.9%, XRP_1h 3.9% — too low for deployment confidence.
   No parameter tweak can fix this — only time (data accumulation) or structural redesign.
4. **Dataset growth**: ETH_1h/XRP_1h only ~36-37 bars. Statistical power is very low.
   Most parameter changes produce undetectable differences on <5 resolved outcomes.
   Natural growth at 1 bar/hour — 6 months = ~4,380 bars, >500 outcomes at current rate.
   Fill-sim experiments at current stage are largely within statistical noise.
5. **Post-fill-sim-exhaustion plan**: After R11 cancel_distance experiments, if both pairs DISCARD,
   consider (a) limited deployment of ETH_1h/XRP_1h at current performance levels with small position
   sizing, (b) waiting 3-6 months for dataset growth, or (c) investigating non-fill-sim engine changes
   such as the matched_ratio direct optimization or order sizing restructuring.
