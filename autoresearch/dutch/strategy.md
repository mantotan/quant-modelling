# Dutch Strategy
Updated: after iteration 140 (2026-03-27T12:30:00Z) — STRATEGIST rotation 12 mid-run analysis

## Summary

Rotation 12 (iters 128-140, ongoing): 0 KEEPs so far from 3 completed active experiments.
- ETH_1h risk_t_start=0.15 DISCARD (iter133): profit regressed +$0.19->+$0.12/bar; inert/noise
- XRP_1h risk_t_start=0.15 DISCARD-DD_BREACH (iter139): DD=16.7% > 15% threshold; matched_ratio improved 3.9%->5.1% (sole positive signal)
- ETH_1h risk_t_end=0.75 DISCARD (iter140): all metrics indistinguishable from KEEP state; inert

**Risk budget category: 0/3 completed experiments = 0% KEEP rate so far**
**Cumulative KEEP rate: 5 KEEPs out of 28+ active experiments = ~17.9%** (declining from 20.8% at iter127)

Pending (planned per researcher_ack iter140-141): XRP_1h risk_t_end 0.80->0.75

If XRP_1h risk_t_end DISCARDs: both pairs proceed to risk_exponent 2.0->1.5 (rotation 12 item 3).
If XRP_1h risk_t_end DISCARDs + risk_exponent DISCARDs: risk_budget category EXHAUSTED both pairs.
Auditor must then assess: escalate to sell category or declare structural floor reached.

**Key finding: risk_t_start=0.15 has asymmetric effects by pair**
- ETH_1h: completely inert (fill_rate, pair_cost, matched_ratio all unchanged) — noise at <5 outcomes
- XRP_1h: matched_ratio IMPROVED 3.9%->5.1% (+1.2pp = +30.8% relative) but DD deteriorated 10.58%->16.7%
  Interpretation: later order placement DOES improve timing quality on XRP_1h (better-resolved prices)
  but disrupts inventory rebalancing leading to drawdown spike. Pure timing-quality vs DD trade-off.
  risk_t_start is NOT simply inert for XRP_1h — it's a double-edged lever. Increasing it too much
  compresses the rebalancing window. Might respond better to a smaller shift (0.10->0.12) but per
  blacklist policy, floor is confirmed at 0.10 after DD breach.

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

## ETH_1h (pair_cost=0.577, KEEP rate 3/12 active experiments=25%, max_dd=11.2%)

### Status: ACTIVE — FILL-SIM EXHAUSTED, RISK_BUDGET in progress (2/3 sub-params done: 0/2 KEEP)

Full trajectory (all rotations):
- Iter 6 (R1): cost=0.000, zero pairs at gate=0.08
- Iter 18 (R2 baseline): cost=0.594, matched=2.0%, profit=-$0.06/bar, DD=13.8%
- Iter 29 (R3 pace=0.25): DISCARD — identical to baseline (pace inert on thin data)
- Iter 41 (R4 baseline pace=0.35): cost=0.594, matched=2.0%, profit=+$0.08/bar, DD=7.6%
- Iter 53 (R5 pace=0.30): DISCARD — identical to baseline (pace lever confirmed inert)
- Iter 66 (R6 fill_ticks=2): DISCARD — profit regression -$0.04/bar; DD=13.8% exceeds threshold
- Iter 78 (R7 chase_threshold=0.05): KEEP — pair_cost=0.577 (-0.017), profit=+$0.18/bar (+$0.10)
- Iter 85 (R8 pace_urgency_hi=1.5): DISCARD — ALL metrics IDENTICAL; pace inert
- Iter 97 (R9 spread_offset=0.005): KEEP — profit=+$0.19/bar (+$0.01/bar marginal), pair_cost stable
- Iter 109 (R10 max_chase=3): DISCARD — ALL METRICS IDENTICAL; max_chase floor confirmed at 2
- Iter 121 (R11 cancel_distance=0.03): DISCARD — fill_rate COLLAPSED 86%->43.6%; fill-sim exhausted
- Iter 133 (R12 risk_t_start=0.15): DISCARD — profit +$0.19->+$0.12/bar; inert/noise (thin dataset)
- Iter 140 (R12 risk_t_end=0.75): DISCARD — all metrics indistinguishable; INERT confirmed

ETH_1h current KEEP state (iter 97): pair_cost=0.577, profit=+$0.19/bar, DD=11.2%, matched=1.9%

FILL-SIM CATEGORY FULLY EXHAUSTED:
| Sub-param | Result | Floor/KEEP value |
|-----------|--------|-----------------|
| fill_ticks | DISCARD (R6 iter66) | 1 (floor) |
| chase_threshold | KEEP (R7 iter78) | 0.05 |
| spread_offset | KEEP (R9 iter97) | 0.005 |
| max_chase | DISCARD-inert (R10 iter109) | 2 (floor) |
| cancel_distance | DISCARD (R11 iter121) | 0.05 (floor) |

RISK_BUDGET CATEGORY (in progress):
| Sub-param | Result | Notes |
|-----------|--------|-------|
| risk_t_start | DISCARD iter133 | 0.15 inert on thin dataset; floor=0.10 |
| risk_t_end | DISCARD iter140 | 0.75 inert on thin dataset; floor=0.80 |
| risk_exponent | PENDING | 2.0->1.5 next experiment |

**Current knobs state (knobs_ETH_1h.json and best_knobs_ETH_1h.json):**
- fill_ticks=1, chase_threshold=0.05, max_chase=2, spread_offset=0.005, cancel_distance=0.05
- risk_t_start=0.10, risk_t_end=0.80, risk_exponent=2.0 (all at floor/KEEP values)

**Priority queue for rotation 12 (remaining):**

1. **risk_exponent 2.0->1.5 EXPERIMENT** (rotation 12 item 3)
   - Hypothesis: Flatter ramp distributes orders more evenly across the bar. On ETH_1h's thin dataset
     (~5 resolved outcomes), quadratic concentration near ramp apex may be timing orders into a narrow
     window that misses the actual trade event. A softer exponent (1.5 = roughly sqrt) spreads order
     flow more uniformly. Given both risk_t_start and risk_t_end were inert, the SHAPE of the ramp
     rather than its timing may matter. Low probability of success given dataset sparsity.
   - Baseline ref: pair_cost=0.577, profit=+$0.19/bar, DD=11.2%, matched=1.9% (iter97)
   - Accept KEEP if: pair_cost < 0.577 OR avg_profit > +$0.19/bar OR matched_ratio > 1.9%
   - DISCARD if: pair_cost > 0.65 OR DD > 13% OR matched_ratio < 1.5%
   - IMPORTANT: improvement must be > $0.05/bar (noise floor) to be meaningful
   - If DISCARD: risk_budget category EXHAUSTED for ETH_1h

2. **If risk_exponent DISCARD: ESCALATE TO AUDITOR**
   - ETH_1h already BEATS all trader_a benchmarks: profit=+$0.19/bar, pair_cost=0.577 < 0.85
   - ETH_1h is functionally deployment-ready
   - Open question: sell parameter category. sell_loss_start=0.7, sell_dump_start=0.9 are untested.
     However, with 0 sell events firing in any backtest, sell params are INERT at current pair formation rate.
   - Auditor ruling: assess formal deployment readiness for ETH_1h

**Structural note on ETH_1h risk budget experiments:**
Both risk_t_start and risk_t_end are confirmed INERT on ETH_1h. This is consistent with the
statistical noise floor (~±$0.05/bar at 4-5 outcomes/36 bars). Any parameter affecting ORDER TIMING
but not OUTCOME MATCHING will be indistinguishable from noise at this sample size. Risk_exponent
has the same constraint. Likelihood of KEEP: LOW. Proceed as procedural completeness, not optimism.

Blacklist (cumulative): pace_urgency_lo 0.25/0.30 (DEAD), fill_ticks=2 (regression iter66),
pace_urgency_hi=1.5 (inert iter85), max_chase=3 (INERT iter109), cancel_distance=0.03 (COLLAPSE iter121),
risk_t_start=0.15 (DISCARD iter133), risk_t_end=0.75 (DISCARD iter140).
PACE CATEGORY CLOSED. FILL-SIM CATEGORY CLOSED. RISK_BUDGET: 2/3 sub-params done (both DISCARD).

---

## XRP_1h (pair_cost=0.785, KEEP rate 3/11 active experiments=27.3%, max_dd=10.58%)

### Status: ACTIVE — FILL-SIM EXHAUSTED, RISK_BUDGET in progress (1/3 sub-params done: 0/1 KEEP)

Full trajectory (all rotations):
- Iter 12 (R1 baseline): cost=0.855, matched=3.6%, profit=N/A, DD=3.1%
- Iter 23 (R2 baseline): cost=0.812, matched=4.2%, profit=+$0.10/bar, DD=8.0%
- Iter 35 (R3 pace=0.30): DISCARD — COLLAPSE (0% matched); PACE FLOOR 0.35 CONFIRMED
- Iter 47 (R4 baseline onesided=5.0): cost=0.812, matched=4.1%, profit=-$0.14/bar, DD=9.8%
- Iter 59 (R5 onesided=2.0): DISCARD — COLLAPSE (0% matched); onesided floor confirmed >3.0
- Iter 72 (R6 fill_ticks=2): KEEP — cost=0.812 stable, profit=-$0.13/bar (+$0.01 improvement)
- Iter 79 (R7 chase_threshold=0.05): KEEP — cost=0.785 (-3.3%), profit=-$0.08/bar (+$0.05)
- Iter 91 (R8 onesided=3.5): DISCARD — profit REGRESSED -0.26/bar (onesided floor=5.0 confirmed)
- Iter 103 (R9 spread_offset=0.005): DISCARD — pair_cost REGRESSED 0.818, profit -0.21/bar
- Iter 115 (R10 max_chase=3): KEEP — profit=-$0.026/bar IMPROVED (+$0.054/bar=+67.5%)
- Iter 127 (R11 cancel_distance=0.03): DISCARD-COLLAPSE — matched 3.9%->1.6%; fill-sim exhausted
- Iter 139 (R12 risk_t_start=0.15): DISCARD-DD_BREACH — DD=16.7% > 15%; matched improved 3.9%->5.1%

XRP_1h current KEEP state (iter 115): pair_cost=0.785, profit=-$0.026/bar, DD=10.58%, matched=3.9%

FILL-SIM CATEGORY FULLY EXHAUSTED:
| Sub-param | Result | Floor/KEEP value |
|-----------|--------|-----------------|
| fill_ticks | KEEP (R6 iter72) | 2 |
| chase_threshold | KEEP (R7 iter79) | 0.05 |
| spread_offset | DISCARD (R9 iter103) | 0.01 (floor — XRP wider spread) |
| max_chase | KEEP (R10 iter115) | 3 |
| cancel_distance | DISCARD-COLLAPSE (R11 iter127) | 0.05 (floor) |

RISK_BUDGET CATEGORY (in progress):
| Sub-param | Result | Notes |
|-----------|--------|-------|
| risk_t_start | DISCARD iter139 | DD breach 16.7%>15%; timing quality improved (matched +1.2pp) but unacceptable DD cost |
| risk_t_end | PENDING | 0.80->0.75 — planned next experiment (researcher_ack iter141) |
| risk_exponent | PENDING | 2.0->1.5 if risk_t_end DISCARDs |

**Critical interpretation for XRP_1h risk_t_start finding:**
Unlike ETH_1h where risk_t_start was purely inert, XRP_1h showed a genuine causal effect:
- BETTER: matched_ratio 3.9%->5.1% (+30.8% relative) — timing improvement is REAL
- WORSE: DD 10.58%->16.7% (+6.1pp) — rebalancing window compression caused drawdown
- Net: DISCARD due to DD breach, but this confirms XRP_1h IS sensitive to order timing
- Implication for risk_t_end: a smaller backward shift (just the ramp END, not the START)
  avoids the rebalancing compression problem while potentially capturing some timing benefit.
  risk_t_end=0.75 shifts the apex 3 minutes earlier, giving slightly more buffer at end-of-bar
  for rebalancing. This should be SAFER than risk_t_start shift. Moderate optimism for risk_t_end.

**Current knobs state (knobs_XRP_1h.json and best_knobs_XRP_1h.json):**
- fill_ticks=2, chase_threshold=0.05, max_chase=3, spread_offset=0.01, cancel_distance=0.05
- risk_t_start=0.10, risk_t_end=0.80, risk_exponent=2.0 (floors confirmed)
- min_buy_time_pct=0.15 (intentional V7.6 setting — NOT related to risk_t_start)

**Priority queue for rotation 12 (remaining):**

1. **risk_t_end 0.80->0.75 EXPERIMENT** (rotation 12 item 2 — NEXT PENDING)
   - Hypothesis: Shifting ramp apex 3 minutes earlier (t=0.75 vs t=0.80) gives additional end-of-bar
     time for rebalancing, potentially preventing the DD spike seen with risk_t_start shift.
     Unlike risk_t_start, this does NOT delay when orders begin — it only shifts when peak sizing
     occurs. On XRP_1h where timing quality matters (iter139 showed matched improved when orders
     placed later), earlier apex means slightly more orders at modest sizing in the final 15 minutes.
     The risk_t_start finding (matched improves with later placement) actually argues AGAINST
     this helping matched_ratio — but it may improve DD by allowing more rebalancing time.
   - Baseline ref: pair_cost=0.785, profit=-$0.026/bar, DD=10.58%, matched=3.9% (iter115)
   - Accept KEEP if: pair_cost < 0.785 OR avg_profit > -$0.026/bar
   - IMMEDIATE DISCARD if: matched_ratio < 2.0% (collapse) OR DD > 15%
   - If KEEP: update best_knobs_XRP_1h.json with risk_t_end=0.75
   - If DISCARD: restore risk_t_end=0.80; proceed to risk_exponent

2. **If risk_t_end DISCARD: risk_exponent 2.0->1.5 EXPERIMENT** (rotation 12 item 3)
   - Hypothesis: Flatter ramp distributes orders more evenly. Given XRP_1h IS timing-sensitive
     (risk_t_start finding), changing the shape of the ramp may matter. Softer exponent front-loads
     orders slightly more vs quadratic backloading. Combined with XRP_1h's finding that later orders
     have better timing quality, this is slightly contrarian — but worth testing as the last risk lever.
   - Accept KEEP if: same criteria as above
   - DISCARD criteria: matched < 2.0% (collapse) OR DD > 15%
   - If DISCARD: risk_budget category EXHAUSTED for XRP_1h

3. **If all risk_budget DISCARDs: ESCALATE TO AUDITOR**
   - XRP_1h at -$0.026/bar is near breakeven. pair_cost=0.785 BEATS trader_a target.
   - Fill-sim improvement trajectory: R6 +$0.01, R7 +$0.05, R10 +$0.054 = cumulative +$0.114/bar
   - XRP_1h needs only +$0.026/bar more to reach breakeven. If risk_budget exhausted, structural floor.
   - Auditor must assess: (a) next unexplored category (sell params), or (b) declare floor reached

Blacklist (cumulative): skip 0.45/0.55, bar_budget 300, risk_ceil 0.20,
pace_urgency_lo 0.30 (COLLAPSE iter 35), max_onesided_cost 2.0 (COLLAPSE iter 59),
max_onesided_cost 3.5 (DISCARD iter 91), spread_offset=0.005 (DISCARD iter103),
cancel_distance=0.03 (COLLAPSE iter127), risk_t_start=0.15 (DISCARD-DD_BREACH iter139).
FILL-SIM CLOSED. RISK_BUDGET: 1/3 sub-params done.

---

## Rotation 12 Execution Plan (remaining items)

1. **BTC_5m through ETH_15m** — SKIP (all FROZEN, no change)
2. **ETH_1h** — **risk_exponent 2.0->1.5 EXPERIMENT** (stage in knobs only, not best_knobs)
3. **SOL_5m, SOL_15m, SOL_1h** — SKIP (all FROZEN)
4. **XRP_5m, XRP_15m** — SKIP (all FROZEN)
5. **XRP_1h** — **risk_t_end 0.80->0.75 EXPERIMENT** (NEXT — stage in knobs only, not best_knobs)
   Then: risk_exponent 2.0->1.5 if risk_t_end DISCARDs

**Order for remaining iters (dispatch rotation continues at XRP_1h, then wraps to next rotation):**
- Current position: iter141 = XRP_1h risk_t_end (planned, per researcher_ack)
- iter142: BTC_5m SKIP (rotation 13 begins)
- ... through SOL_1h/XRP_5m/XRP_15m SKIPS
- Next ETH_1h: risk_exponent 2.0->1.5
- Next XRP_1h: risk_exponent 2.0->1.5 (if risk_t_end DISCARDs at iter141)

---

## Cross-Pair Observations

### Rotation 12 key finding: risk_budget is largely inert on thin 1h datasets

All 3 completed risk_budget experiments (iter133, iter139, iter140) produced DISCARDs.
Pattern analysis:
- ETH_1h timing levers (risk_t_start, risk_t_end): completely inert — changes fall within noise floor
  at ~4-5 outcomes/36 bars. Sample size too small to detect timing differences.
- XRP_1h risk_t_start: NOT inert (matched improved +30%) but DD penalty was severe (+6.1pp breach).
  This confirms XRP_1h has genuine timing sensitivity but the current risk budget parameters represent
  a near-optimal balance for DD management. Moving the ramp start disrupts this balance.

### Divergence between ETH_1h and XRP_1h timing sensitivity:

| Metric | ETH_1h (iter133) | XRP_1h (iter139) | Interpretation |
|--------|------------------|------------------|----------------|
| fill_rate change | 86.1%->83.8% (-2.3pp) | 74.3%->72.4% (-1.9pp) | Both slightly reduce |
| matched_ratio change | 1.9%->1.83% (-4%) | 3.9%->5.1% (+31%) | XRP benefits, ETH inert |
| DD change | 11.2%->11.2% (0) | 10.58%->16.7% (+6.1pp) | ETH stable, XRP spikes |
| profit change | +$0.19->+$0.12 (-37%) | -$0.026->-$0.45 (-1630%) | Both regress (DD-driven) |

ETH_1h: Timing is genuinely inert at current dataset size. Matched ratio is locked at ~4-5 outcomes.
XRP_1h: Timing affects BOTH matching quality (positively) AND rebalancing dynamics (negatively).
XRP_1h is a more complex, timing-sensitive system than ETH_1h. risk_t_end (shifting only the ramp end)
may capture some of the positive matching benefit while avoiding the rebalancing penalty.

### Fill-sim vs risk_budget category effectiveness:

| Category | ETH_1h KEEPs | XRP_1h KEEPs | Total | Rate |
|----------|-------------|-------------|-------|------|
| fill-sim | 2/5 (40%) | 3/5 (60%) | 5/10 | 50% |
| pace | 0/3 (0%) | 0/1 (0%) | 0/4 | 0% |
| risk_budget | 0/2 (0%) so far | 0/1 (0%) so far | 0/3 | 0% |
| sell | 0/0 (N/A) | 0/0 (N/A) | 0/0 | N/A |

Fill-sim remains the only productive category (50% KEEP rate). Risk budget following pace's 0% pattern.

---

## trader_a Benchmark Comparison (after rotation 12 partial, iter 140)

| Pair | PairCost | Target | Gap | AvgProfit | MaxDD% | Status |
|------|----------|--------|-----|-----------|--------|--------|
| BTC_5m | 0.000 | < 0.85 | N/A | -$0.031/bar | 23.4% | FROZEN PERMANENT — fill mechanics (P=5.6%) |
| BTC_15m | 0.000 | < 0.85 | N/A | -$0.019/bar | 12.4% | FROZEN — outcome sparsity + zero pairs |
| BTC_1h | 0.000 | < 0.85 | N/A | -$0.032/bar | 3.9% | FROZEN — extreme sparsity (2.9%) |
| ETH_5m | 0.000 | < 0.85 | N/A | -$0.091/bar | 28.7% | FROZEN — DD WARNING, fill mechanics (P=5.8%) |
| ETH_15m | 0.000 | < 0.85 | N/A | +$0.158/bar | 7.1% | FROZEN — gate exhausted, strong signal wasted |
| ETH_1h | 0.577 | < 0.85 | -0.273 (BEATS) | +$0.190/bar | 11.2% | ACTIVE — risk_exponent queued |
| SOL_5m | 0.000 | < 0.85 | N/A | +$0.135/bar | 23.2% | FROZEN — fill mechanics (P=5.3%) |
| SOL_15m | 0.567* | < 0.85 | N/A | -$0.270/bar | 19.8% | FROZEN — correct_side=45.5% < 50% |
| SOL_1h | 0.000 | < 0.85 | N/A | -$0.110/bar | 8.3% | FROZEN — outcome sparsity (8.6%) |
| XRP_5m | N/A | < 0.85 | N/A | N/A | N/A | FROZEN PERMANENT — fill_rate=15.6% floor |
| XRP_15m | 0.950 | < 0.85 | +0.100 (FAILS) | -$0.240/bar | 20.5% | FROZEN — correct_side=49.2% declining |
| XRP_1h | 0.785 | < 0.85 | -0.065 (BEATS) | -$0.026/bar | 10.58% | ACTIVE — risk_t_end pending iter141 |

*SOL_15m: artificially low pair_cost (near-zero pairs)

**Deployment readiness update:**
- ETH_1h: STILL DEPLOYMENT-READY. All trader_a benchmarks beaten. No rotation 12 improvements found.
  risk_exponent is the final risk_budget lever — treat as procedural. If DISCARD, deployment case
  is formally confirmed: ETH_1h has exhausted all known levers at +$0.19/bar.
- XRP_1h: Not yet profitable (-$0.026/bar). risk_t_end and risk_exponent remain untested.
  If both DISCARD: structural floor confirmed at -$0.026/bar. Borderline deployment case
  (pair_cost beats benchmark, near-breakeven profit, improving trajectory).

---

## Blacklist Summary

### Per-pair blacklists

- **BTC_5m**: FROZEN PERMANENT. Fill mechanics (P=5.6%). No experiments.
- **BTC_15m**: FROZEN. Outcome sparsity dominant (7.9%).
- **BTC_1h**: FROZEN. Extreme outcome sparsity (2.9%).
- **ETH_5m**: FROZEN. DD=28.7% near kill threshold; P=5.8% fill mechanics.
- **ETH_15m**: FROZEN. Gate exhausted; outcome sparsity (9.9%). HIGHEST LATENT POTENTIAL (correct_side=71.2%).
- **ETH_1h**: pace_urgency_lo 0.25/0.30, fill_ticks=2, pace_urgency_hi=1.5, max_chase=3 (inert),
  cancel_distance=0.03 (COLLAPSE), risk_t_start=0.15 (DISCARD), risk_t_end=0.75 (DISCARD).
  PACE CLOSED. FILL-SIM CLOSED. RISK_BUDGET: 2/3 done (both DISCARD).
- **SOL_5m**: FROZEN. Fill mechanics dominant.
- **SOL_15m**: FROZEN. correct_side=45.5% both measurements below 50%.
- **SOL_1h**: FROZEN. Outcome sparsity (8.6%).
- **XRP_5m**: FROZEN PERMANENT.
- **XRP_15m**: FROZEN. correct_side declining (53.7%->50.0%->49.2%).
- **XRP_1h**: pace_urgency_lo 0.30 (COLLAPSE), max_onesided_cost 2.0 (COLLAPSE),
  max_onesided_cost 3.5 (DISCARD), spread_offset=0.005 (DISCARD),
  cancel_distance=0.03 (COLLAPSE), risk_t_start=0.15 (DISCARD-DD_BREACH iter139).
  FILL-SIM CLOSED. RISK_BUDGET: 1/3 done.

### Global Blacklist

- **conviction_market_start**: GLOBALLY BLACKLISTED. Fails across ALL tested pairs.
- **magnitude_gate (all values 0.0/0.02/0.04/0.08)**: Exhausted for ALL pairs.
- **pace_urgency_lo < 0.35**: GLOBALLY BLACKLISTED. COLLAPSE confirmed on XRP_1h.
- **max_onesided_cost < 3.5**: BLACKLISTED for XRP_1h. $2 causes collapse. $3.5 causes regression.
- **cancel_distance=0.03**: GLOBALLY BLACKLISTED FOR 1h PAIRS. Floor=0.05 for all 1h pairs.
- **Any experiment on frozen pairs**: BLOCKED until auditor lifts freeze or structural fix deployed.
- **Pace levers on thin 1h datasets**: Empirically confirmed inert. Dead category.
- **spread_offset 0.005 on XRP_1h**: BLACKLISTED — floor=0.01 for XRP.
- **max_chase=3 on ETH_1h**: BLACKLISTED — inert at fill_rate=86% (iter109).
- **risk_t_start=0.15 on XRP_1h**: BLACKLISTED — DD breach; rebalancing window too compressed.
- **risk_t_start=0.15 on ETH_1h**: BLACKLISTED — inert (below noise floor at current dataset size).
- **risk_t_end=0.75 on ETH_1h**: BLACKLISTED — inert (below noise floor at current dataset size).

### Structural Engineering Recommendations (for future audit/development)

1. **Outcome resolution rate remains binding constraint**: ETH_1h ~4-5 outcomes per 36-37 bar window
   is the fundamental statistical floor. Risk budget experiments are now confirming this: ALL timing
   changes are inert on ETH_1h because changes affect individual bar ordering but not the ~5 outcomes
   that determine performance. Fix: OHLC-based outcome resolution or live-log dataset expansion.
   Priority: CRITICAL — blocks risk_budget experiments from being meaningful on ETH_1h.
2. **ETH_15m high-value frozen asset**: correct_side=71.2%, +$0.158/bar unmatched profit.
   If outcome resolution rate could be improved, ETH_15m might be unlockable.
3. **XRP_1h timing sensitivity finding**: risk_t_start experiments showed XRP_1h IS sensitive to
   order timing (unlike ETH_1h). This suggests risk_exponent (ramp SHAPE) may also affect XRP_1h
   more meaningfully. Monitor for non-trivial matched_ratio and DD changes in risk_exponent experiment.
4. **Fill mechanics remain structurally blocking 10 of 12 pairs**: All frozen pairs except ETH_15m
   are blocked by fill mechanics (5m pairs) or outcome sparsity (1h pairs). No parameter tuning can
   fix these — requires either engine redesign or dataset growth.
5. **Sell category largely irrelevant at current pair formation rate**: 0 sell events firing in any
   backtest means sell params (sell_loss_start, sell_dump_start) are structurally inert until the
   strategy forms enough pairs to trigger sell conditions. Sell category de-prioritized.
