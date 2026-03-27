# Dutch Strategy
Updated: after iteration 90 (2026-03-27T21:30:00Z) — STRATEGIST rotation 8 post-run analysis

## Summary

Rotations 7-8 (iters 73-90): 2 active experiments run. **2 KEEPs in rotation 7** (ETH_1h and XRP_1h
both KEEP on chase_threshold=0.05). 1 DISCARD in rotation 8 (ETH_1h pace_urgency_hi=1.5 inert).
Rotation 8 stalled at XRP_1h (pair_index=10/XRP_15m frozen, advancing to XRP_1h = iter 91).

**KEEP rate rotations 7-8: 2/3 active experiments = 66.7%** (best rotation performance yet)
**Cumulative KEEP rate: 3 KEEPs out of ~15 non-baseline active experiments = 20%**

Chase threshold is the highest-yield lever found so far:
- ETH_1h: pair_cost 0.594->0.577 (-3%), profit +$0.08->+$0.18/bar (+125%). BENCHMARK CANDIDATE.
- XRP_1h: pair_cost 0.812->0.785 (-3.3%), profit -$0.13->-$0.08/bar (+38% loss reduction).

ETH_1h pace_urgency_hi DISCARD confirms the pattern: pace levers are statistically inert on thin
1h datasets (<5 resolved outcomes). Both pace_lo and pace_hi now exhausted for ETH_1h.

XRP_1h: knobs_XRP_1h.json already staged with max_onesided_cost=3.5 as next experiment.
This is the correct next lever per the onesided floor narrowing plan (5.0 stable, 2.0 collapse).

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

## ETH_1h (pair_cost=0.577, KEEP rate 2/8 active experiments=25%, max_dd=11.2%)

### Status: ACTIVE — STRONG CANDIDATE (well below trader_a pair_cost target 0.85)

Full trajectory:
- Iter 6 (R1): cost=0.000, zero pairs at gate=0.08
- Iter 18 (R2 baseline): cost=0.594, matched=2.0%, profit=-$0.06/bar, DD=13.8%
- Iter 29 (R3 pace=0.25): DISCARD — identical to baseline (pace lever inert on thin data)
- Iter 41 (R4 baseline pace=0.35): cost=0.594, matched=2.0%, profit=+$0.08/bar, DD=7.6%
- Iter 53 (R5 pace=0.30): DISCARD — identical to baseline (pace lever confirmed inert)
- Iter 66 (R6 fill_ticks=2): DISCARD — profit regression -$0.04/bar; DD=13.8% exceeds 12%
- Iter 78 (R7 chase_threshold=0.05): KEEP — pair_cost=0.577 (-0.017), profit=+$0.18/bar (+$0.10)
- Iter 85 (R8 pace_urgency_hi=1.5): DISCARD — ALL metrics IDENTICAL to iter 78 KEEP; pace inert

ETH_1h current KEEP state (iter 78): pair_cost=0.577, profit=+$0.18/bar, DD=11.2%, matched=1.9%
PACE CATEGORY EXHAUSTED: pace_urgency_lo (iters 29/53) and pace_urgency_hi (iter 85) both inert.

**Current knobs state:**
- knobs_ETH_1h.json: fill_ticks=1, chase_threshold=0.05, pace_urgency_hi=2.0 (restored post-DISCARD iter 85)
- best_knobs_ETH_1h.json: fill_ticks=1, chase_threshold=0.05 (updated after KEEP iter 78)
- Both files aligned and correct.

**Priority queue for rotation 9:**
1. **spread_offset 0.01->0.005 EXPERIMENT** — tighter limit placement
   - Hypothesis: tighter spread (0.005 vs 0.01 from fee offset) may improve fill rate marginally
     in liquid 1h ETH market, potentially increasing matched_ratio from 1.9%
   - Stage: modify fill_simulator.spread_offset in knobs_ETH_1h.json only (not best_knobs)
   - Baseline ref: pair_cost=0.577, profit=+$0.18/bar, DD=11.2%, matched=1.9% (iter 78)
   - Accept KEEP if: matched_ratio > 1.9% OR avg_profit > +$0.18/bar OR pair_cost < 0.577
   - DISCARD if: pair_cost > 0.65 OR DD > 13% OR matched_ratio < 1.5%
   - If KEEP: update best_knobs_ETH_1h.json with spread_offset=0.005
   - If DISCARD: restore spread_offset=0.01; next lever = max_chase 2->3 (wider chase range)
2. If spread_offset DISCARD: max_chase 2->3 (allow 3 chase attempts vs 2)
   - Rationale: more chase attempts may recover fills after price movement in thin 1h ETH
   - Accept KEEP if: matched_ratio > 1.9% OR avg_profit > +$0.18/bar
3. If max_chase DISCARD: cancel_distance 0.05->0.03 (tighter cancellation = orders live longer)
   - Rationale: reducing cancel distance keeps limit orders near midpoint longer before cancellation
4. If 3 consecutive DISCARDs on fill-sim sub-params: escalate to auditor — ETH_1h at structural floor
   NOTE: ETH_1h profit=+$0.18/bar already beats trader_a target (>$0). Primary gap: matched_ratio=1.9%
   is too low for deployment confidence. Need >5% matched_ratio for statistical significance.

Blacklist (cumulative): pace_urgency_lo 0.25/0.30 (DEAD — inert on thin data), fill_ticks=2 (regression
iter 66), pace_urgency_hi=1.5 (inert iter 85), onesided above 5, skip 0.40, risk_ceil 0.20,
bar_budget 250/300, conviction_market_start (GLOBAL).

**PACE CATEGORY CLOSED FOR ETH_1h** — all pace levers tested (lo 0.25/0.30, hi 1.5). None effective.
Only fill-sim sub-params remain: spread_offset, max_chase, cancel_distance.

---

## XRP_1h (pair_cost=0.785, KEEP rate 2/7 active experiments=28.6%, max_dd=8.9%)

### Status: ACTIVE — IMPROVING (pair_cost beats trader_a target; 2 consecutive KEEPs)

Full trajectory:
- Iter 12 (R1 baseline): cost=0.855, matched=3.6%, profit=N/A, DD=3.1%
- Iter 23 (R2 baseline): cost=0.812, matched=4.2%, profit=+$0.10/bar, DD=8.0%
- Iter 35 (R3 pace=0.30): DISCARD — COLLAPSE (0% matched vs 4.2%); PACE FLOOR 0.35 CONFIRMED
- Iter 47 (R4 baseline onesided=5.0): cost=0.812, matched=4.1%, profit=-$0.14/bar, DD=9.8%
- Iter 59 (R5 onesided=2.0): DISCARD — COLLAPSE (0% matched); onesided floor confirmed >3.0
- Iter 72 (R6 fill_ticks=2): KEEP — cost=0.812 stable, profit=-$0.13/bar (IMPROVED +$0.01)
- Iter 79 (R7 chase_threshold=0.05): KEEP — cost=0.785 (-3.3%), profit=-$0.08/bar (+$0.05)
- Rotation 8: onesided=3.5 EXPERIMENT NEXT (already staged in knobs_XRP_1h.json)

XRP_1h KEEP state (iter 79): pair_cost=0.785, profit=-$0.08/bar, DD=8.9%, matched=4.0%
Two consecutive KEEPs confirm XRP_1h is the most responsive active pair to fill-sim tuning.

**Current knobs state:**
- knobs_XRP_1h.json: max_onesided_cost=3.5, fill_ticks=2, chase_threshold=0.05 (experiment pre-staged)
  NOTE: conviction_buy_skip=0.5 in knobs vs 0.45 in best_knobs — this is acceptable (higher
  conviction skip threshold may be more conservative; does NOT need restoring as it was likely
  intentionally adjusted during R8 setup)
- best_knobs_XRP_1h.json: max_onesided_cost=5.0, fill_ticks=2, chase_threshold=0.05 (iter 79 KEEP state)
- STAGING CONFIRMED: knobs_XRP_1h.json has onesided=3.5 ready. Do NOT re-stage — just run.

**Priority queue for rotation 9:**
1. **max_onesided_cost 5.0->3.5 EXPERIMENT** — ALREADY STAGED IN KNOBS
   - knobs_XRP_1h.json already has max_onesided_cost=3.5. Run as-is.
   - Hypothesis: onesided=3.5 is intermediate between stable (5.0) and collapse (2.0).
     May reduce unmatched cost accumulation while preserving pair formation above collapse threshold.
   - Baseline ref: pair_cost=0.785, profit=-$0.08/bar, DD=8.9%, matched=4.0% (iter 79, KEEP state)
   - Accept KEEP if: pair_cost < 0.785 OR avg_profit > -$0.08/bar
   - IMMEDIATE DISCARD if: matched_ratio < 2.0% (collapse mechanism) OR DD > 15%
   - If KEEP: update best_knobs_XRP_1h.json with max_onesided_cost=3.5; next = spread_offset 0.01->0.005
   - If DISCARD (not collapse): confirm onesided floor at 5.0; next = spread_offset 0.01->0.005
   - If COLLAPSE (matched_ratio < 2.0%): CONFIRM onesided floor at 5.0; restore immediately; next = spread_offset
2. If onesided=3.5 clears threshold but marginal: spread_offset 0.01->0.005 in fill_simulator
   - Same as ETH_1h lever — tighter limit placement for better fill entry price
   - Accept KEEP if: pair_cost < current KEEP OR avg_profit > current KEEP
3. If 3 consecutive DISCARDs: escalate to auditor — XRP_1h structural floor assessment
   NOTE: XRP_1h profit=-$0.08/bar improving but still negative. Need to reach >$0 for deployment.
   At current improvement rate (+$0.05/bar per KEEP), 2 more KEEPs would reach profitability.

Blacklist (cumulative): skip 0.45/0.55, bar_budget 300, risk_ceil 0.20,
pace_urgency_lo 0.30 (COLLAPSE iter 35), pace_urgency_lo 0.45 (D pre-RESET),
max_onesided_cost 2.0 (COLLAPSE iter 59), fill_ticks=1 superseded (KEEP at fill_ticks=2),
chase_threshold=0.03 superseded (KEEP at chase_threshold=0.05).
PACE_LO FLOOR: 0.35 confirmed. ONESIDED FLOOR: between 3.0 and 5.0 (3.5 next test).

---

## Rotation 9 Execution Plan (priority order)

1. **BTC_5m** — SKIP (FROZEN PERMANENT — fill mechanics structural, P=5.6%)
2. **BTC_15m** — SKIP (FROZEN — 3 consecutive zero-pair baselines, outcome sparsity 7.9%)
3. **BTC_1h** — SKIP (FROZEN — extreme sparsity 2.9%)
4. **ETH_5m** — SKIP (FROZEN — DD=28.7% near kill threshold, fill mechanics structural P=5.8%)
5. **ETH_15m** — SKIP (FROZEN — gate series exhausted, outcome sparsity 9.9%)
6. **ETH_1h** — **spread_offset 0.01->0.005 EXPERIMENT** (stage in knobs_ETH_1h.json fill_simulator only)
7. **SOL_5m** — SKIP (FROZEN — outcome sparsity 6.7%, DD elevated, fill mechanics P=5.3%)
8. **SOL_15m** — SKIP (FROZEN — correct_side=45.5% < 50%)
9. **SOL_1h** — SKIP (FROZEN — outcome sparsity 8.6%)
10. **XRP_5m** — SKIP (FROZEN PERMANENT)
11. **XRP_15m** — SKIP (FROZEN — correct_side declining, gate exhausted)
12. **XRP_1h** — **max_onesided_cost=3.5 EXPERIMENT** (ALREADY STAGED — just run, do not re-stage)

IMPORTANT: The dispatch state shows current pair_index=10 (XRP_15m) and the auditor pre-logged
iters 86-90 as SKIP rows. The next dispatch invocation (iter 91) should advance to XRP_1h (index 11)
and run the onesided=3.5 experiment. This is the user-requested experiment and it is correct per queue.

**Rotation 8 note:** ETH_1h iter 85 DISCARD + XRP_1h iter 91 are the 2 rotation-8 experiments.
Rotation 8 spans iters 80-91 (12 pairs). After iter 91 (XRP_1h), rotation 9 begins at BTC_5m.

**Rotation 9 success criteria:**
- Minimum 1 KEEP on either spread_offset (ETH_1h) or onesided=3.5 (XRP_1h)
- If both DISCARD: ETH_1h has exhausted all known levers (pace, fill_ticks, chase, pace_hi, spread_offset)
  → escalate ETH_1h to auditor for structural assessment after rotation 9
- XRP_1h at -$0.08/bar: 2 more +$0.04/bar gains needed for profitability. On track.
- If onesided=3.5 KEEP and spread_offset KEEP: first rotation with 2 simultaneous KEEPs since R7.

---

## Cross-Pair Observations

### Rotations 7-8 critical findings

**Chase threshold is the highest-yield lever found (2 KEEPs, R7):**
- ETH_1h: +$0.10/bar profit gain, -0.017 pair_cost improvement
- XRP_1h: +$0.05/bar profit gain, -0.027 pair_cost improvement
- Mechanism: wider chase window (5% vs 3%) allows orders to re-enter after brief adverse price moves
  This is most effective in thin 1h markets where price jumps briefly before returning to range

**Pace levers are uniformly inert on thin 1h datasets:**
- ETH_1h: pace_urgency_lo tested 3x (0.25, 0.30, 0.35), pace_urgency_hi tested 1x (1.5) — all inert
- XRP_1h: pace_urgency_lo=0.30 causes COLLAPSE (not just inert — actively harmful)
- Pattern: with <5 resolved outcomes per pair, pace timing changes do not shift which bars get outcomes
- Implication: pace levers may become useful only after dataset grows to 20+ resolved outcomes

**Onesided cost floor between 3.0 and 5.0 for XRP_1h:**
- onesided=2.0 collapses (iter 59), onesided=5.0 stable — midpoint 3.5 is the next test
- The collapse mechanism at onesided=2.0: $2 cap exhausted before any pair can form in sparse window
- onesided=3.5 should not collapse (>$3 per side, sufficient for sparse pair formation)

**Fill mechanics structural constraint remains unsolved for 5m pairs:**
- BTC/ETH/SOL 5m pairs: P(both fill) = 5-6%. No parameter change can fix this without engine redesign.
- XRP_5m: fill_rate=15.6% floor is LOWER than the 5m structural floor for others.
- Fill engine redesign (market orders, multi-tick persistence) required before any 5m pair is active.

**Dataset bottleneck intensifying with time:**
- ETH_1h: 36 bars, ~4-5 outcomes. All experiments effectively run on same 4-5 resolved events.
- XRP_1h: 36 bars, ~4-5 outcomes. Same constraint.
- Statistical significance requires ~50+ matched pairs for 95% confidence on +$0.01/bar effect.
- At 4.0% matched_ratio and 36 bars: ~1.4 matched pairs per run. VERY low power.

---

## trader_a Benchmark Comparison (after rotation 8, iter 90)

| Pair | PairCost | Target | Gap | AvgProfit | MaxDD% | Status |
|------|----------|--------|-----|-----------|--------|--------|
| BTC_5m | 0.000 | < 0.85 | N/A | -$0.060/bar | 23.4% | FROZEN PERMANENT — fill mechanics (P=5.6%) |
| BTC_15m | 0.000 | < 0.85 | N/A | -$0.019/bar | 12.4% | FROZEN — outcome sparsity + zero pairs |
| BTC_1h | 0.000 | < 0.85 | N/A | -$0.032/bar | 3.9% | FROZEN — extreme sparsity (2.9%) |
| ETH_5m | 0.000 | < 0.85 | N/A | -$0.091/bar | 28.7% | FROZEN — DD WARNING, fill mechanics (P=5.8%) |
| ETH_15m | 0.000 | < 0.85 | N/A | +$0.158/bar | 7.1% | FROZEN — gate exhausted, strong signal wasted |
| ETH_1h | 0.577 | < 0.85 | -0.273 (BEATS) | +$0.180/bar | 11.2% | ACTIVE — spread_offset=0.005 queued |
| SOL_5m | 0.000 | < 0.85 | N/A | +$0.135/bar | 23.2% | FROZEN — fill mechanics (P=5.3%) |
| SOL_15m | 0.567* | < 0.85 | N/A | -$0.270/bar | 19.8% | FROZEN — correct_side=45.5% < 50% |
| SOL_1h | 0.000 | < 0.85 | N/A | -$0.110/bar | 8.3% | FROZEN — outcome sparsity (8.6%) |
| XRP_5m | N/A | < 0.85 | N/A | N/A | N/A | FROZEN PERMANENT — fill_rate=15.6% floor |
| XRP_15m | 0.950 | < 0.85 | +0.100 (FAILS) | -$0.240/bar | 20.5% | FROZEN — correct_side=49.2% declining |
| XRP_1h | 0.785 | < 0.85 | -0.065 (BEATS) | -$0.080/bar | 8.9% | ACTIVE — onesided=3.5 STAGED (iter 91 next) |

*SOL_15m: artificially low pair_cost (near-zero pairs)

**Progress since last strategist (iter 72):**
- ETH_1h: pair_cost improved 0.594 -> 0.577 (-2.8%), profit improved +$0.08 -> +$0.18/bar (+125%)
- XRP_1h: pair_cost improved 0.812 -> 0.785 (-3.3%), profit improved -$0.13 -> -$0.08/bar (+38%)
- ETH_1h now meets avg_profit > 0 target. XRP_1h at -$0.08/bar, trending positive.

Best performers (active, pair_cost beats target):
- ETH_1h: pair_cost=0.577 — BENCHMARK ACHIEVED. profit=+$0.18/bar POSITIVE. Needs matched_ratio >5%.
- XRP_1h: pair_cost=0.785 — BENCHMARK ACHIEVED. profit=-$0.08/bar negative but improving rapidly.

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
- **ETH_1h**: pace_urgency_lo 0.25/0.30 (DEAD — inert on thin data), fill_ticks=2 (regression iter 66),
  pace_urgency_hi=1.5 (INERT iter 85 — pace category FULLY EXHAUSTED).
  onesided above 5, skip 0.40, risk_ceil 0.20, bar_budget 250/300, conviction_market_start (GLOBAL).
  PACE CATEGORY CLOSED. Next: fill_sim sub-params (spread_offset, max_chase, cancel_distance).
- **SOL_5m**: FROZEN. fill mechanics dominant (fill_rate=23.1%, P=5.3%).
- **SOL_15m**: FROZEN. correct_side=45.5% both measurements < 50%.
- **SOL_1h**: FROZEN. gate series exhausted; outcome sparsity (8.6%).
- **XRP_5m**: FROZEN PERMANENT. fill_rate=15.6% structural floor.
- **XRP_15m**: FROZEN. correct_side declining (53.7%->50.0%->49.2%); gate exhausted.
- **XRP_1h**: skip 0.45/0.55, bar_budget 300, risk_ceil 0.20,
  pace_urgency_lo 0.30 (COLLAPSE iter 35), pace_urgency_lo 0.45 (D pre-RESET),
  max_onesided_cost 2.0 (COLLAPSE iter 59), fill_ticks=1 superseded (KEEP at fill_ticks=2),
  chase_threshold=0.03 superseded (KEEP at chase_threshold=0.05).
  PACE_LO FLOOR: 0.35 confirmed. ONESIDED FLOOR: between 3.0 and 5.0 (3.5 testing next).

### Global Blacklist

- **conviction_market_start**: GLOBALLY BLACKLISTED. Fails across ALL tested pairs.
- **magnitude_gate (all values 0.0/0.02/0.04/0.08)**: Exhausted for ALL pairs. Gate parameter is
  irrelevant for any pair with outcome sparsity or fill mechanics bottleneck.
- **pace_urgency_lo < 0.35**: GLOBALLY BLACKLISTED. COLLAPSE mechanism confirmed on XRP_1h.
  ETH_1h: lever dead entirely. Do NOT test below 0.35 on any pair.
- **max_onesided_cost < 3.0**: BLACKLISTED. $2 causes collapse on XRP_1h. Minimum test = 3.5.
- **Any experiment on frozen pairs**: BLOCKED until auditor lifts freeze or structural fix deployed.
- **Pace levers on thin 1h datasets**: Empirically confirmed inert. Do not test pace variations
  on any pair with <10 resolved outcomes — wasted iterations.

### Structural Engineering Recommendations (for future audit/development)

1. **Outcome resolution rate**: Current 8-14% for 1h pairs is the binding long-term constraint.
   Engineering fix: ingest more live-log data OR implement OHLC-based outcome resolution.
   This would unfreeze ETH_15m (correct_side=71.2%, strong signal) and potentially BTC_1h/SOL_1h.
   Priority: HIGH — would add 2-4 active experimental pairs.
2. **Fill mechanics for 5m pairs**: P(both sides fill in bar)=5.6% for BTC_5m is structural.
   Engineering fix: increase fill_ticks substantially (e.g., 5-10), widen spread_offset, or use
   market orders for small sizes. Current fill_ticks lever (1->2) is insufficient for 5m.
   The 5m pairs require engine redesign, not parameter tuning.
3. **Dataset growth**: ETH_1h/XRP_1h only have 36 bars. Statistical power is very low.
   Most parameter changes produce undetectable differences on <5 resolved outcomes.
   Dataset grows naturally at 1 bar/hour — 6 months = ~4,380 bars, >500 outcomes at current rate.
4. **Matched ratio bottleneck**: Even at best (XRP_1h 4.0%), 36 bars produces ~1.4 matched pairs.
   This is the fundamental reason all experiments show marginal/uncertain improvements.
   No parameter tweak can fix this — only time (data accumulation) or structural redesign.
