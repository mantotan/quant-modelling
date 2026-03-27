# Dutch Strategy
Updated: after iteration 127 (2026-03-27T10:30:00Z) — STRATEGIST rotation 11 post-run analysis

## Summary

Rotation 11 (iters 116-127): 0 KEEPs (ETH_1h cancel_distance DISCARD iter121, XRP_1h cancel_distance DISCARD-COLLAPSE iter127).
**KEEP rate rotation 11: 0/2 active experiments = 0%** (down from rotation 10's 50%).
**Cumulative KEEP rate: 5 KEEPs out of 24 non-baseline active experiments = 20.8%**

Fill-sim category is now FULLY EXHAUSTED for BOTH active pairs (ETH_1h and XRP_1h).
All 5 fill-sim sub-params tested and settled:
- ETH_1h: fill_ticks=1, chase_threshold=0.05, spread_offset=0.005, max_chase=2, cancel_distance=0.05
- XRP_1h: fill_ticks=2, chase_threshold=0.05, max_chase=3, spread_offset=0.01, cancel_distance=0.05

cancel_distance=0.03 collapses both pairs identically — falls within normal 1h price noise, causing
over-cancellation before fills can execute. Floor confirmed at 0.05 for all tested pairs.

**Rotation 12 priority: RISK BUDGET category (first untested high-leverage category)**

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

## ETH_1h (pair_cost=0.577, KEEP rate 3/11 active experiments=27.3%, max_dd=11.2%)

### Status: ACTIVE — FILL-SIM EXHAUSTED, TRANSITION TO RISK BUDGET CATEGORY

Full trajectory:
- Iter 6 (R1): cost=0.000, zero pairs at gate=0.08
- Iter 18 (R2 baseline): cost=0.594, matched=2.0%, profit=-$0.06/bar, DD=13.8%
- Iter 29 (R3 pace=0.25): DISCARD — identical to baseline (pace inert on thin data)
- Iter 41 (R4 baseline pace=0.35): cost=0.594, matched=2.0%, profit=+$0.08/bar, DD=7.6%
- Iter 53 (R5 pace=0.30): DISCARD — identical to baseline (pace lever confirmed inert)
- Iter 66 (R6 fill_ticks=2): DISCARD — profit regression -$0.04/bar; DD=13.8% exceeds threshold
- Iter 78 (R7 chase_threshold=0.05): KEEP — pair_cost=0.577 (-0.017), profit=+$0.18/bar (+$0.10)
- Iter 85 (R8 pace_urgency_hi=1.5): DISCARD — ALL metrics IDENTICAL; pace inert
- Iter 97 (R9 spread_offset=0.005): KEEP — profit=+$0.19/bar (+$0.01/bar marginal), pair_cost stable
- Iter 109 (R10 max_chase=3): DISCARD — ALL METRICS IDENTICAL; fill_rate 86% too high for extra chase;
  max_chase floor confirmed at 2 for ETH_1h
- Iter 121 (R11 cancel_distance=0.03): DISCARD — fill_rate COLLAPSED 86%->43.6% (-42.4pp);
  profit REGRESSED +$0.19->+$0.06/bar (-68%); cancel_distance floor confirmed at 0.05

ETH_1h current KEEP state (iter 97): pair_cost=0.577, profit=+$0.19/bar, DD=11.2%, matched=1.9%

FILL-SIM CATEGORY FULLY EXHAUSTED:
| Sub-param | Result | Floor/KEEP value |
|-----------|--------|-----------------|
| fill_ticks | DISCARD (R6 iter66) | 1 (floor) |
| chase_threshold | KEEP (R7 iter78) | 0.05 |
| spread_offset | KEEP (R9 iter97) | 0.005 |
| max_chase | DISCARD-inert (R10 iter109) | 2 (floor) |
| cancel_distance | DISCARD (R11 iter121) | 0.05 (floor) |

**Current knobs state (both knobs_ETH_1h.json and best_knobs_ETH_1h.json):**
- fill_ticks=1, chase_threshold=0.05, max_chase=2, spread_offset=0.005, cancel_distance=0.05 (confirmed aligned)

**Priority queue for rotation 12:**

1. **risk_t_start 0.1->0.15 EXPERIMENT** — shift order-sizing ramp start point later in bar
   - Hypothesis: ETH_1h matched_ratio=1.9% is the primary performance gap. Orders placed very early
     in the bar (t=0.10, 6 minutes into 1h bar) may face adverse selection before price settles.
     Shifting risk_t_start from 0.1 to 0.15 (9 min into bar) means the order sizing ramp starts
     slightly later, concentrating buys in better-resolved price regions. On thin 1h market, early
     placement into unsettled price contributes to poor matching. Test: small shift first.
   - Baseline ref: pair_cost=0.577, profit=+$0.19/bar, DD=11.2%, matched=1.9% (iter97)
   - Accept KEEP if: pair_cost < 0.577 OR avg_profit > +$0.19/bar OR matched_ratio > 1.9%
   - DISCARD if: pair_cost > 0.65 OR DD > 13% OR matched_ratio < 1.5%
   - If KEEP: update best_knobs_ETH_1h.json with risk_t_start=0.15
   - If DISCARD: restore risk_t_start=0.10; try risk_t_end next

2. **Fallback if risk_t_start DISCARD: risk_t_end 0.8->0.75 EXPERIMENT**
   - Hypothesis: Ending the order-sizing ramp at 0.75 (instead of 0.80) gives 3 more minutes of
     bar time after ramp peak for final pair formation attempts before bar closes. On 1h bars,
     this is 3 extra minutes where matched pairs can form at peak sizing. Small directional shift.
   - Baseline ref: same as above (iter97 KEEP state)
   - Accept KEEP if: same criteria as risk_t_start experiment
   - DISCARD if: same criteria as risk_t_start experiment; restore risk_t_end=0.80

3. **If both risk_t experiments DISCARD: risk_exponent 2.0->1.5 EXPERIMENT**
   - Hypothesis: Linear-ish ramp (exponent 1.5 vs 2.0) means more orders are placed at moderate
     urgency earlier in bar vs concentrated near peak. Given thin dataset, this changes order
     distribution. Could improve matched_ratio if current quadratic concentration is mismatched
     to ETH_1h price distribution.
   - DISCARD if: same thresholds. If DISCARD: risk budget sub-category exhausted for ETH_1h.

4. **If all risk_budget DISCARD: escalate to auditor for structural assessment**
   - ETH_1h with profit=+$0.19/bar and pair_cost=0.577 ALREADY BEATS trader_a benchmarks.
   - The matched_ratio=1.9% is a statistical floor driven by dataset sparsity (4-5 outcomes/backtest).
   - Auditor should assess: (a) deploy ETH_1h at current performance level, or (b) wait for dataset
     growth. ETH_1h at +$0.19/bar is the system's best-performing pair — deployment case is strong.

Blacklist (cumulative): pace_urgency_lo 0.25/0.30 (DEAD), fill_ticks=2 (regression iter66),
pace_urgency_hi=1.5 (inert iter85), onesided>5 (not tested — default 5.0 is floor),
skip 0.40, risk_ceil 0.20, bar_budget 250/300, conviction_market_start (GLOBAL),
max_chase=3 (INERT iter109), cancel_distance=0.03 (COLLAPSE iter121).
PACE CATEGORY CLOSED. FILL-SIM CATEGORY CLOSED.

---

## XRP_1h (pair_cost=0.785, KEEP rate 3/10 active experiments=30%, max_dd=10.58%)

### Status: ACTIVE — FILL-SIM EXHAUSTED, TRANSITION TO RISK BUDGET CATEGORY

Full trajectory:
- Iter 12 (R1 baseline): cost=0.855, matched=3.6%, profit=N/A, DD=3.1%
- Iter 23 (R2 baseline): cost=0.812, matched=4.2%, profit=+$0.10/bar, DD=8.0%
- Iter 35 (R3 pace=0.30): DISCARD — COLLAPSE (0% matched); PACE FLOOR 0.35 CONFIRMED
- Iter 47 (R4 baseline onesided=5.0): cost=0.812, matched=4.1%, profit=-$0.14/bar, DD=9.8%
- Iter 59 (R5 onesided=2.0): DISCARD — COLLAPSE (0% matched); onesided floor confirmed >3.0
- Iter 72 (R6 fill_ticks=2): KEEP — cost=0.812 stable, profit=-$0.13/bar (+$0.01 improvement)
- Iter 79 (R7 chase_threshold=0.05): KEEP — cost=0.785 (-3.3%), profit=-$0.08/bar (+$0.05)
- Iter 91 (R8 onesided=3.5): DISCARD — profit REGRESSED -0.26/bar (onesided floor=5.0 confirmed)
- Iter 103 (R9 spread_offset=0.005): DISCARD — pair_cost REGRESSED 0.818, profit -0.21/bar
- Iter 115 (R10 max_chase=3): KEEP — profit=-$0.026/bar IMPROVED (+$0.054/bar=+67.5%);
  fill_rate 69.0%->74.3% (+5.3pp); pair_cost=0.785 stable; matched_ratio=3.9% stable
- Iter 127 (R11 cancel_distance=0.03): DISCARD-COLLAPSE — matched_ratio 3.9%->1.6% (below 2.0%
  threshold TRIGGERED); fill_rate HALVED 74.3%->34.2%; profit REGRESSED -$0.026->-$0.384/bar;
  cancel_distance floor confirmed at 0.05; knobs restored

XRP_1h current KEEP state (iter 115): pair_cost=0.785, profit=-$0.026/bar, DD=10.58%, matched=3.9%

FILL-SIM CATEGORY FULLY EXHAUSTED:
| Sub-param | Result | Floor/KEEP value |
|-----------|--------|-----------------|
| fill_ticks | KEEP (R6 iter72) | 2 |
| chase_threshold | KEEP (R7 iter79) | 0.05 |
| spread_offset | DISCARD (R9 iter103) | 0.01 (floor — XRP wider spread) |
| max_chase | KEEP (R10 iter115) | 3 |
| cancel_distance | DISCARD-COLLAPSE (R11 iter127) | 0.05 (floor) |

**Current knobs state (both knobs_XRP_1h.json and best_knobs_XRP_1h.json):**
- fill_ticks=2, chase_threshold=0.05, max_chase=3, spread_offset=0.01, cancel_distance=0.05 (confirmed aligned)

**Priority queue for rotation 12:**

1. **risk_t_start 0.1->0.15 EXPERIMENT** — shift ramp start point later in bar
   - Hypothesis: XRP_1h profit=-$0.026/bar is near breakeven. fill_rate=74.3% is solid but
     matched_ratio=3.9% is partially constrained by order timing. Orders placed at t=0.10 (6 min)
     face less-resolved XRP price movement vs t=0.15 (9 min). Shifting start point reduces adverse
     selection in early bar ordering. Unlike ETH_1h, XRP_1h has fill_rate headroom (74% not 86%)
     so timing change may produce cleaner KEEP/DISCARD signal.
   - Baseline ref: pair_cost=0.785, profit=-$0.026/bar, DD=10.58%, matched=3.9% (iter115)
   - Accept KEEP if: pair_cost < 0.785 OR avg_profit > -$0.026/bar
   - IMMEDIATE DISCARD if: matched_ratio < 2.0% (collapse) OR DD > 15%
   - If KEEP: update best_knobs_XRP_1h.json with risk_t_start=0.15
   - If DISCARD: restore risk_t_start=0.10; try risk_t_end next

2. **Fallback if risk_t_start DISCARD: risk_t_end 0.8->0.75 EXPERIMENT**
   - Same hypothesis as ETH_1h but XRP_1h context: XRP_1h has more fill headroom, so giving 3
     extra minutes of peak-sized ordering may recover additional matched pairs.
   - Accept KEEP if: pair_cost < 0.785 OR avg_profit > -$0.026/bar
   - DISCARD if: collapse (matched<2%) OR DD>15%

3. **If both risk_t experiments DISCARD: risk_exponent 2.0->1.5 EXPERIMENT**
   - Flat ramp may better distribute orders across bar on XRP_1h's 74% fill environment.
   - DISCARD if: same thresholds. If DISCARD: risk budget sub-category exhausted for XRP_1h.

4. **If all risk_budget DISCARD: escalate to auditor for deployment assessment**
   - XRP_1h at -$0.026/bar with pair_cost=0.785 beats trader_a cost benchmark.
   - At current trajectory (+$0.054/bar per fill-sim KEEP), 3 fill-sim KEEPs yielded +$0.114/bar
     improvement. Risk budget is the next lever; if exhausted, structural floor is reached.

Blacklist (cumulative): skip 0.45/0.55, bar_budget 300, risk_ceil 0.20,
pace_urgency_lo 0.30 (COLLAPSE iter 35), max_onesided_cost 2.0 (COLLAPSE iter 59),
max_onesided_cost 3.5 (DISCARD iter 91 — profit regression),
spread_offset=0.005 (DISCARD iter103 — XRP natural spread floor=0.01),
cancel_distance=0.03 (COLLAPSE iter127). PACE_LO FLOOR: 0.35. ONESIDED FLOOR: 5.0.
FILL-SIM CATEGORY CLOSED.

---

## Rotation 12 Execution Plan (priority order)

1. **BTC_5m** — SKIP (FROZEN PERMANENT)
2. **BTC_15m** — SKIP (FROZEN — outcome sparsity structural)
3. **BTC_1h** — SKIP (FROZEN — extreme sparsity 2.9%)
4. **ETH_5m** — SKIP (FROZEN — DD near kill threshold, fill mechanics structural)
5. **ETH_15m** — SKIP (FROZEN — gate series exhausted)
6. **ETH_1h** — **risk_t_start 0.10->0.15 EXPERIMENT** (stage in knobs_ETH_1h.json only, not best_knobs)
7. **SOL_5m** — SKIP (FROZEN — fill mechanics structural, DD elevated)
8. **SOL_15m** — SKIP (FROZEN — correct_side=45.5% < 50%)
9. **SOL_1h** — SKIP (FROZEN — outcome sparsity structural)
10. **XRP_5m** — SKIP (FROZEN PERMANENT)
11. **XRP_15m** — SKIP (FROZEN — correct_side declining, gate exhausted)
12. **XRP_1h** — **risk_t_start 0.10->0.15 EXPERIMENT** (stage in knobs_XRP_1h.json only, not best_knobs)

Execution note: risk_t_start appears as a top-level key in knobs.json (not inside fill_simulator).
For ETH_1h: current risk_t_start=0.10 → stage 0.15 in knobs_ETH_1h.json only.
For XRP_1h: current risk_t_start=0.10 → stage 0.15 in knobs_XRP_1h.json only.

---

## Cross-Pair Observations

### Rotation 11 key finding: cancel_distance=0.03 UNIVERSAL FAILURE

Both ETH_1h and XRP_1h collapsed at cancel_distance=0.03 with strikingly similar profiles:
- ETH_1h: fill_rate 86%->43.6% (-42.4pp), profit +$0.19->+$0.06/bar (-68%)
- XRP_1h: fill_rate 74.3%->34.2% (-40.1pp), profit -$0.026->-$0.384/bar (-1378%), matched 3.9%->1.6% (COLLAPSE)
Pattern: 3% cancel threshold falls within normal 1h price noise for both ETH and XRP.
The 5% cancel distance is at the minimum viable threshold for 1h Polymarket bars.
**Global rule established: cancel_distance=0.03 is universally destructive for 1h bars. Floor=0.05.**

### Fill-sim category effectiveness by sub-param (across all pairs):

| Sub-param | ETH_1h | XRP_1h | Pattern |
|-----------|--------|--------|---------|
| fill_ticks | DISCARD (2 hurts) | KEEP (2 helps) | Pair-specific: fill_rate saturation |
| chase_threshold | KEEP (0.05 helps) | KEEP (0.05 helps) | UNIVERSAL — best sub-param |
| spread_offset | KEEP (0.005 helps) | DISCARD (0.005 hurts) | Pair-specific: natural spread |
| max_chase | DISCARD-inert | KEEP (3 helps) | Pair-specific: fill_rate saturation |
| cancel_distance | DISCARD (0.03 hurts) | DISCARD-COLLAPSE | UNIVERSAL FAILURE at 0.03 |

**Chase_threshold=0.05 is the only universally beneficial fill-sim lever across both active pairs.**
Fill-sim overall KEEP rate: 5 KEEPs from 10 active fill-sim experiments = 50% (best category in system).

### Category KEEP rates (cumulative):

| Category | KEEPs | Experiments | Rate | Status |
|----------|-------|-------------|------|--------|
| fill-sim | 5 | 10 | 50% | EXHAUSTED (both pairs) |
| magnitude_gate | 0 | ~6 | 0% | EXHAUSTED (all pairs) |
| pace | 0 | 6 | 0% | EXHAUSTED (inert on thin data) |
| onesided | 0 | 4 | 0% | EXHAUSTED/floor confirmed |
| risk_budget | 0 | 0 | N/A | NEXT CATEGORY (rotation 12) |
| sell params | 0 | 0 | N/A | QUEUED (rotation 13+) |

### Performance trajectory (active pairs):

ETH_1h: R4 baseline +$0.08 → R7 KEEP +$0.18 → R9 KEEP +$0.19 → R10 DISCARD unchanged → R11 DISCARD unchanged
Plateau confirmed at +$0.19/bar. No further fill-sim improvement possible. Structural ceiling reached
for fill mechanics. Current performance BEATS trader_a: profit>0 AND pair_cost=0.577<0.85.

XRP_1h: R2 baseline +$0.10 → R4 baseline -$0.14 → R6 KEEP -$0.13 → R7 KEEP -$0.08 → R10 KEEP -$0.026 → R11 DISCARD unchanged
Strong improving trajectory: 3 KEEPs over R6-R10 yielded +$0.114/bar total improvement.
At -$0.026/bar approaching breakeven. pair_cost=0.785 BEATS trader_a target.
Fill-sim fully exhausted. Risk budget is the logical next lever.

### Statistical power warning:

Both 1h pairs operate on ~36-37 bars with only 4-5 resolved outcomes per backtest run.
The noise floor is approximately ±$0.05/bar per experiment at this sample size.
ETH_1h spread_offset KEEP (+$0.01/bar) and XRP_1h fill_ticks KEEP (+$0.01/bar) are marginal improvements
that may be within statistical noise. The clear signal KEEPs are chase_threshold (both pairs, +$0.05-0.10/bar)
and XRP_1h max_chase (+$0.054/bar). These are large-effect improvements well above noise floor.
Risk budget experiments should be evaluated with the same ±$0.05/bar noise context:
- A KEEP requires improvement > $0.05/bar to be confidently above noise.
- Small improvements 0.01-0.03/bar should be treated as marginal/noise (DISCARD unless other metrics improve).

---

## trader_a Benchmark Comparison (after rotation 11, iter 127)

| Pair | PairCost | Target | Gap | AvgProfit | MaxDD% | Status |
|------|----------|--------|-----|-----------|--------|--------|
| BTC_5m | 0.000 | < 0.85 | N/A | -$0.031/bar | 23.4% | FROZEN PERMANENT — fill mechanics (P=5.6%) |
| BTC_15m | 0.000 | < 0.85 | N/A | -$0.019/bar | 12.4% | FROZEN — outcome sparsity + zero pairs |
| BTC_1h | 0.000 | < 0.85 | N/A | -$0.032/bar | 3.9% | FROZEN — extreme sparsity (2.9%) |
| ETH_5m | 0.000 | < 0.85 | N/A | -$0.091/bar | 28.7% | FROZEN — DD WARNING, fill mechanics (P=5.8%) |
| ETH_15m | 0.000 | < 0.85 | N/A | +$0.158/bar | 7.1% | FROZEN — gate exhausted, strong signal wasted |
| ETH_1h | 0.577 | < 0.85 | -0.273 (BEATS) | +$0.190/bar | 11.2% | ACTIVE — risk_t_start queued for R12 |
| SOL_5m | 0.000 | < 0.85 | N/A | +$0.135/bar | 23.2% | FROZEN — fill mechanics (P=5.3%) |
| SOL_15m | 0.567* | < 0.85 | N/A | -$0.270/bar | 19.8% | FROZEN — correct_side=45.5% < 50% |
| SOL_1h | 0.000 | < 0.85 | N/A | -$0.110/bar | 8.3% | FROZEN — outcome sparsity (8.6%) |
| XRP_5m | N/A | < 0.85 | N/A | N/A | N/A | FROZEN PERMANENT — fill_rate=15.6% floor |
| XRP_15m | 0.950 | < 0.85 | +0.100 (FAILS) | -$0.240/bar | 20.5% | FROZEN — correct_side=49.2% declining |
| XRP_1h | 0.785 | < 0.85 | -0.065 (BEATS) | -$0.026/bar | 10.58% | ACTIVE — risk_t_start queued for R12 |

*SOL_15m: artificially low pair_cost (near-zero pairs)

**Progress since last strategist (iter 115):**
- ETH_1h: cancel_distance=0.03 DISCARD (iter121). Profit unchanged +$0.19/bar, pair_cost unchanged 0.577.
  Fill-sim fully exhausted. ETH_1h holds at strong KEEP state, BEATS both trader_a benchmarks.
- XRP_1h: cancel_distance=0.03 DISCARD-COLLAPSE (iter127). Profit unchanged -$0.026/bar, pair_cost 0.785.
  Fill-sim fully exhausted. XRP_1h holding at best KEEP state, near-breakeven, approaching target.

**Deployment readiness:**
- ETH_1h: profit=+$0.19/bar, pair_cost=0.577 — BENCHMARK ACHIEVED. Primary concern is matched_ratio=1.9%
  (statistical floor at ~4-5 outcomes). ETH_1h is technically ready for limited live deployment.
  Recommend auditor assessment of matched_ratio adequacy before live capital commitment.
- XRP_1h: profit=-$0.026/bar — NOT YET PROFITABLE. pair_cost=0.785 BEATS target. Near-breakeven.
  1-2 more risk_budget KEEPs could push XRP_1h to profitability. Not yet deployment-ready.

---

## Blacklist Summary

### Per-pair blacklists

- **BTC_5m**: FROZEN PERMANENT. Fill mechanics (P=5.6%). No experiments.
- **BTC_15m**: FROZEN. Outcome sparsity dominant (7.9%).
- **BTC_1h**: FROZEN. Extreme outcome sparsity (2.9%).
- **ETH_5m**: FROZEN. DD=28.7% near kill threshold; P=5.8% fill mechanics.
- **ETH_15m**: FROZEN. Gate exhausted; outcome sparsity (9.9%). HIGHEST LATENT POTENTIAL (correct_side=71.2%).
- **ETH_1h**: pace_urgency_lo 0.25/0.30, fill_ticks=2, pace_urgency_hi=1.5, max_chase=3 (inert),
  cancel_distance=0.03 (COLLAPSE iter121). PACE CLOSED. FILL-SIM CLOSED.
- **SOL_5m**: FROZEN. Fill mechanics dominant.
- **SOL_15m**: FROZEN. correct_side=45.5% both measurements below 50%.
- **SOL_1h**: FROZEN. Outcome sparsity (8.6%).
- **XRP_5m**: FROZEN PERMANENT.
- **XRP_15m**: FROZEN. correct_side declining (53.7%->50.0%->49.2%).
- **XRP_1h**: pace_urgency_lo 0.30 (COLLAPSE), max_onesided_cost 2.0 (COLLAPSE),
  max_onesided_cost 3.5 (DISCARD), spread_offset=0.005 (DISCARD),
  cancel_distance=0.03 (COLLAPSE iter127). PACE_LO FLOOR: 0.35. ONESIDED FLOOR: 5.0.
  FILL-SIM CLOSED.

### Global Blacklist

- **conviction_market_start**: GLOBALLY BLACKLISTED. Fails across ALL tested pairs.
- **magnitude_gate (all values 0.0/0.02/0.04/0.08)**: Exhausted for ALL pairs.
- **pace_urgency_lo < 0.35**: GLOBALLY BLACKLISTED. COLLAPSE confirmed on XRP_1h.
- **max_onesided_cost < 3.5**: BLACKLISTED for XRP_1h. $2 causes collapse. $3.5 causes regression.
- **cancel_distance=0.03**: GLOBALLY BLACKLISTED FOR 1h PAIRS. Both ETH_1h and XRP_1h collapse.
  3% threshold falls within normal 1h price noise. Floor=0.05 for all 1h pairs.
- **Any experiment on frozen pairs**: BLOCKED until auditor lifts freeze or structural fix deployed.
- **Pace levers on thin 1h datasets**: Empirically confirmed inert (<10 resolved outcomes). Dead category.
- **spread_offset 0.005 on XRP_1h**: BLACKLISTED — fill_rate reduction confirmed; floor=0.01 for XRP.
- **max_chase=3 on ETH_1h**: BLACKLISTED — inert at fill_rate=86% (iter109). Floor=2 for ETH_1h.

### Structural Engineering Recommendations (for future audit/development)

1. **Outcome resolution rate**: ETH_1h ~4-5 outcomes per 36-37 bar backtest window is the binding
   statistical constraint. At 4-5 outcomes, noise floor ~±$0.05/bar means marginal improvements
   cannot be detected. Engineering fix: outcome resolution via OHLC-based resolution or live-log
   expansion would unfreeze ETH_15m (correct_side=71.2%) and increase statistical power for ETH_1h.
   Priority: HIGH — ETH_15m unlock alone would add another active experimental pair.
2. **Fill mechanics for 5m pairs**: P=5.6% structural floor on BTC_5m. Only engine redesign can fix.
   Increase fill_ticks to 5-10, widen spread_offset, or switch to market orders for small sizes.
3. **ETH_1h deployment case**: profit=+$0.19/bar, pair_cost=0.577 ALREADY BEATS all trader_a benchmarks.
   matched_ratio=1.9% is the only concern. On a live deployment basis, 1.9% matched_ratio means
   the strategy forms a pair roughly every 53 bars (53 hours = ~2.2 days). This is a very low
   activity rate for live trading but all pairs that do form are profitable. Recommend auditor to
   formally assess whether ETH_1h is deployment-ready at current activity rate.
4. **XRP_1h 1-2 more improvements needed**: At -$0.026/bar, XRP_1h needs ~$0.03-0.05/bar more
   improvement to reach clear profitability. Risk budget levers (risk_t_start, risk_t_end,
   risk_exponent) represent the next best-probability category after fill-sim's 50% KEEP rate.
5. **Dataset growth**: 6 months at 1 bar/hour = ~4,380 bars per pair. Current 36-37 bars is extremely
   thin for backtesting. Natural growth at current live session rate will dramatically improve
   experimental statistical power and potentially unlock frozen pairs.
