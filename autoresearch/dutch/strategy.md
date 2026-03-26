# Dutch Strategy
Updated: after iteration 24 (2026-03-27T10:00:00Z) — STRATEGIST rotation 2 post-baseline analysis

## Summary

Rotation 2 complete (iters 13-24). 11 baselines run + 1 DISCARD experiment on BTC_5m (gate=0.02).
**KEEP rate this rotation: 0/12 = 0%** (11 BASELINEs + 1 DISCARD — expected for baseline rotation).

**Critical finding from rotation 2:**
- Gate=0.04 restores pair formation for ETH_1h, SOL_15m, XRP_15m, XRP_1h (4 of 11 active pairs)
- Gate=0.04 still collapses 7 pairs: BTC_5m, BTC_15m, BTC_1h, ETH_5m, ETH_15m, SOL_5m, SOL_1h
- BTC_5m confirmed: gate=0.08, 0.04, and 0.02 all fail — gate=0.0 required (auditor directive ACTIVE)
- SOL_15m: correct_side=45.5% at gate=0.04 — still below 50%, AUDITOR FREEZE ACTIVE
- XRP_1h: strongest performer — pair_cost=0.812, correct_side=70.4%, avg_profit=+$0.10/bar
- ETH_1h: gate=0.04 enabled 2% matched_ratio (recovered from collapse at gate=0.08)

**Researcher compliance:** COMPLIANT. Correctly skipped XRP_5m (FROZEN), fixed bar_budget=300 for
SOL_1h before baseline (iter 21), ran gate=0.02 experiment for BTC_5m per strategy queue.

**Knobs state issues (must fix before experiments):**
- BTC_1h: risk_ceil=0.20 in knobs — auditor directive says revert to 0.15. FIX BEFORE ANY EXPERIMENT.
- SOL_15m: max_onesided_cost=5.0 in knobs — BLACKLISTED for SOL_15m. Irrelevant while frozen.
- ETH_15m: pace_urgency_lo=0.25 in knobs — this is AHEAD of queue (0.30->0.25 is item #2).
  Need gate=0.04 BASELINE first to confirm this is pre-staged correctly.
- ETH_1h: pace_urgency_lo=0.30 in knobs — this is queue item #2 (0.35->0.30). Was this ever
  baselined at 0.35? Iter 18 baseline used gate=0.04, matched_ratio=2.0%, pair_cost=0.594.
  The knobs already at 0.30 means the baseline was likely run with 0.30 active. This is OK:
  if the baseline showed pair_cost=0.594, further experiment tests will compare to that.

---

## AUDITOR FREEZES (active)

- **BTC_5m**: FROZEN pending gate=0.0 baseline. Next: run gate=0.0 baseline only; do not run
  any other experiment until gate=0.0 baseline is confirmed and reviewed.
- **SOL_15m**: FROZEN pending auditor review (correct_side=45.5% below 50% threshold).
  Do NOT run any experiment until auditor lifts freeze. Current BASELINE iters 8 and 20
  both show correct_side below 50% — directional signal is negative, not just weak.
- **XRP_5m**: FROZEN (permanent — structural dead-end confirmed across all rotations).

---

## BTC_5m (pair_cost=0.000 at gate=0.04, KEEP rate 0% post-RESET)

Auditor directive: FREEZE pending gate=0.0 baseline.
Gate history: 0.08=0 pairs (iter 1), 0.04=0 pairs (iter 13), 0.02=0 pairs (iter 24 DISCARD).
Knobs shows: magnitude_gate=0.0 (already pre-staged by researcher).
Prior best (pre-RESET): pair_cost=0.922 at gate=0.0.

Priority queue for rotation 3:
1. magnitude_gate=0.0 BASELINE — REQUIRED per auditor. Knobs already set.
   Accept as BASELINE. This is the only BTC_5m task in rotation 3.
   Expected: pair formation should return with gate disabled (matches pre-RESET behavior).
   If pairs still fail at gate=0.0: escalate to auditor immediately.
2. HOLD all other experiments until gate=0.0 baseline evaluated.

Blacklist: gate=0.02, gate=0.04, gate=0.08 (all confirmed collapse BTC_5m).
Inherited pre-RESET blacklist: skip 0.45/0.55, cheap_threshold 0.07/0.12,
onesided 2.0->1.5 (COLLAPSE iter 117), conviction_market_start (GLOBAL BLACKLIST).

---

## BTC_15m (pair_cost=0.000 at gate=0.04, KEEP rate 0% post-RESET)

Gate=0.04 baseline (iter 14): matched_ratio=0%, pair_cost=0.000.
8 live-log outcomes in 136 bars confirms extreme outcome sparsity.
correct_side=56.5% moderate signal. fill_rate=44.5%.
Current knobs: magnitude_gate=0.04, max_onesided_cost=2.0, pace_urgency_lo=0.35, bar_budget=200.

Issue: Zero pair formation persists despite gate=0.04. This means the gate threshold is NOT
the pair formation bottleneck for BTC_15m — unlike XRP_1h and ETH_1h which recovered.
Hypothesis: BTC_15m outcome sparsity (8/136 bars with outcomes) means very few bars qualify.

Priority queue for rotation 3:
1. magnitude_gate=0.0 BASELINE — same approach as BTC_5m. Disable gate entirely to test
   whether any pairs form. If gate=0.0 also fails: investigate engine/dataset (outcome sparsity
   may be preventing pair evaluation entirely).
   Knobs: set magnitude_gate=0.0 before running.
2. pace_urgency_lo 0.35->0.30 — only AFTER gate=0.0 baseline shows non-zero pairs.
   XRP_15m showed 18% gain from 0.35->0.30. Medium confidence.
3. max_onesided_cost 2.0 is already set — already applied (knobs shows 2.0, best_knobs shows 5.0).
   Do NOT further reduce (floor at 2.0 confirmed pre-RESET for BTC-family).

Blacklist: skip=0.45 (definitive 3x collapse), bar_budget 400,
conviction_market_start (GLOBAL BLACKLIST), gate=0.04 (zero pairs confirmed).

---

## BTC_1h (pair_cost=0.000 at gate=0.04, KEEP rate 0% post-RESET)

Gate=0.04 baseline (iter 15): matched_ratio=0%, pair_cost=0.000.
1 live-log outcome in 34 bars (extreme sparsity — 3% outcome resolution).
correct_side=68.4% strong signal. fill_rate=52.9%.
Current knobs: magnitude_gate=0.04, max_onesided_cost=2.0, pace_urgency_lo=0.45, risk_ceil=0.20.

CRITICAL KNOBS FIX: risk_ceil=0.20 in knobs — auditor directive says revert to 0.15.
FIX risk_ceil=0.15 in knobs_BTC_1h.json BEFORE any experiment.

Priority queue for rotation 3:
1. FIX STALE KNOBS: risk_ceil 0.20->0.15 in knobs_BTC_1h.json immediately.
2. magnitude_gate=0.0 BASELINE — same approach. Only 1 outcome in 34 bars means
   outcome sparsity is extreme. Gate=0.0 may not help if outcomes don't resolve.
   Knobs: set magnitude_gate=0.0 before running.
3. If gate=0.0 still shows 0 pairs: this pair is outcome-sparsity limited. Flag for auditor.
4. max_onesided_cost: knobs=2.0, best_knobs=5.0. The 2.0 was already set. Do not reduce further.

Blacklist: risk_ceil 0.10, skip 0.50 (D iter 64), onesided 5->3 (D iter 91),
conviction_market_start (GLOBAL BLACKLIST), gate=0.04 (zero pairs).

---

## ETH_5m (pair_cost=0.000 at gate=0.04, KEEP rate 0% post-RESET)

Gate=0.04 baseline (iter 16): matched_ratio=0%, pair_cost=0.000.
27 live-log outcomes in 406 bars (6.6% outcome resolution).
correct_side=52.0% minimal edge. max_dd=29.2% (dangerously close to 30% threshold).
Current knobs: magnitude_gate=0.04, max_onesided_cost=1.5, pace_urgency_lo=0.30, skip=0.45.

Observation: pace_urgency_lo=0.30 already set in knobs (strategy queue item #2 was 0.35->0.30).
This was already applied pre-emptively. Baseline ran with 0.30 active.

Issue: Zero pair formation AND dangerously high max_dd (29.2%) from unmatched inventory.
correct_side=52.0% is near-random — model has minimal edge on ETH_5m.

Priority queue for rotation 3:
1. magnitude_gate=0.0 BASELINE — gate reduction series exhausted at 0.04; try gate=0.0.
   If pairs still fail: ETH_5m may be outcome-sparsity limited (27/406 outcomes = 6.6%).
   CAUTION: max_dd=29.2% means even unmatched inventory is high-risk.
2. If gate=0.0 gives non-zero pairs AND pair_cost < 0.85: KEEP and proceed.
   If gate=0.0 still zero pairs: hold all experiments, flag for auditor (max_dd risk).
3. pace_urgency_lo 0.30->0.25 — only after gate=0.0 baseline shows non-zero pairs.

Blacklist: skip 0.60, onesided 1.5->1.0 (COLLAPSE iter 119), gate=0.04 (zero pairs),
conviction_market_start (GLOBAL BLACKLIST).

---

## ETH_15m (pair_cost=0.000 at gate=0.04, KEEP rate 0% post-RESET)

Gate=0.04 baseline (iter 17): matched_ratio=0%, pair_cost=0.000.
8 live-log outcomes in 136 bars (5.9% outcome resolution). correct_side=71.0% strong signal.
avg_profit=+$0.13/bar positive (encouraging even with zero pairs). max_dd=7.1% safe.
Current knobs: magnitude_gate=0.04, max_onesided_cost=1.5, pace_urgency_lo=0.25, skip=0.45.

Observation: pace_urgency_lo=0.25 in knobs — this is AHEAD of queue (strategy item #2 was
0.30->0.25). Baseline at iter 17 ran with 0.25 active. This means queue item #2 is already staged.

Priority queue for rotation 3:
1. magnitude_gate=0.0 BASELINE — zero pairs at gate=0.04 same as gate=0.08.
   correct_side=71.0% is the 2nd highest 15m signal in system — high-value pair if pairs form.
   Knobs: set magnitude_gate=0.0 before running.
2. pace_urgency_lo 0.25->0.20 — knobs already at 0.25; if gate=0.0 baseline shows non-zero
   pairs, continue the series to 0.20. Monitor collapse risk.
3. bar_budget 200->300 — positive avg_profit signals capital scaling potential.
   Only after pace series resolves and baseline is stable.

Blacklist: skip above 0.50, onesided above 1.5, onesided 1.5->1.0 (COLLAPSE iter 94),
conviction_market_start (GLOBAL BLACKLIST), gate=0.04 (zero pairs).

---

## ETH_1h (pair_cost=0.594 at gate=0.04, KEEP rate 0% post-RESET)

Gate=0.04 baseline (iter 18): matched_ratio=2.0%, pair_cost=0.594.
PAIR FORMATION RESTORED at gate=0.04 (vs 0% at gate=0.08, iter 6).
correct_side=62.1% solid signal. fill_rate=83.3% excellent. max_dd=13.8% safe.
Current knobs: magnitude_gate=0.04, max_onesided_cost=5.0, pace_urgency_lo=0.30, skip=0.45.

Observation: pace_urgency_lo=0.30 in knobs (baseline ran with this). pair_cost=0.594 is
WELL BELOW 0.85 target — closest to pre-RESET best of 0.706. This is the 2nd best pair
in rotation 2 for pairs that have actually formed.

Priority queue for rotation 3:
1. pace_urgency_lo 0.30->0.25 — knobs already at 0.30; continue series.
   ETH_1h at 2% matched_ratio; earlier urgency may improve pair quality further.
   Accept KEEP if pair_cost improves >2% vs baseline 0.594.
2. max_onesided_cost 5.0->2.0 — knobs shows 5.0. Strategy queue flagged this as needed.
   pair_cost=0.594 already good; onesided reduction may lock in gains.
   Test after pace_urgency series resolves.
3. pace_urgency_lo 0.25->0.20 — follow series if item #1 KEEPs.

Blacklist: onesided above 5 (D iter 55), skip 0.40, risk_ceil 0.20, bar_budget 250/300,
pace_urgency_lo 0.35->0.45 (D iter 103 — zero effect on 1h TF — but this is XRP_1h history;
verify ETH_1h specifics), conviction_market_start (GLOBAL BLACKLIST).

---

## SOL_5m (pair_cost=0.000 at gate=0.04, KEEP rate 0% post-RESET)

Gate=0.04 baseline (iter 19): matched_ratio=0%, pair_cost=0.000.
28 live-log outcomes in 407 bars (6.9% outcome resolution). correct_side=56.4% weak.
total_profit=$55.26 (unmatched inventory, not pairs). max_dd=20.0%.
Current knobs: magnitude_gate=0.04, max_onesided_cost=2.0, pace_urgency_lo=0.30, skip=0.45.

Observation: pace_urgency_lo=0.30 already set in knobs. Baseline at iter 19 ran with 0.30 active.
SOL_5m showed total_profit positive ($55.26) from unmatched inventory despite zero pairs.

Priority queue for rotation 3:
1. magnitude_gate=0.0 BASELINE — gate series exhausted (0.08=0, 0.04=0). Try gate=0.0.
   Pre-RESET SOL_5m achieved pair_cost=0.676 at gate=0.0. This should restore pair formation.
   Knobs: set magnitude_gate=0.0 before running.
2. If gate=0.0 gives non-zero pairs: pace_urgency_lo 0.30->0.25 — continue series.
   SOL_5m collapse risk is HIGH (pre-RESET iter 109 showed instability). Monitor matched_ratio.
3. conviction_buy_skip 0.45->0.40 — only if baseline is stable. Collapse risk remains high.

Blacklist: skip 0.55 (D iter 41), onesided 2.0->1.5 (COLLAPSE iter 97),
conviction_market_start (GLOBAL BLACKLIST), gate=0.04 (zero pairs).

---

## SOL_15m (pair_cost=0.567 at gate=0.04, KEEP rate 0% post-RESET)

AUDITOR FREEZE ACTIVE — correct_side=45.5% (below 50% threshold).
Gate=0.04 baseline (iter 20): matched_ratio=0.3%, pair_cost=0.567. correct_side=45.5%.
This is the 2nd consecutive rotation showing correct_side below 50% (iter 8: 47.7%, iter 20: 45.5%).
The trend is WORSENING — signal quality is degrading with each gate reduction.
Current knobs: magnitude_gate=0.04, max_onesided_cost=5.0 (BLACKLISTED), pace_urgency_lo=0.30.

CRITICAL: max_onesided_cost=5.0 in knobs is BLACKLISTED for SOL_15m (COLLAPSE confirmed).
This must be corrected when freeze lifts, but do NOT run experiments while frozen.

Priority queue for rotation 3:
1. HOLD — auditor freeze active. Do NOT run any SOL_15m experiments.
2. When auditor reviews: if correct_side recovers above 50% on gate=0.0 test — lift freeze.
   The strategist recommends auditor investigate whether gate reduction itself is degrading
   correct_side by sampling lower-quality predictions (below magnitude threshold).
3. If freeze is lifted: magnitude_gate=0.0 BASELINE first, then watch correct_side closely.
   If correct_side still below 50% at gate=0.0: PERMANENT FREEZE recommended.

Blacklist: skip 0.40 (COLLAPSE iter 85), onesided 5.0->2.0 (COLLAPSE — BLACKLISTED entirely),
bar_budget 400 (D iter 112), conviction_market_start (GLOBAL BLACKLIST).
NOTE: onesided=5.0 currently in knobs IS the blacklisted value — fix before any future experiment.

---

## SOL_1h (pair_cost=0.000 at gate=0.04, KEEP rate 0% post-RESET)

Gate=0.04 baseline (iter 21): matched_ratio=0%, pair_cost=0.000. bar_budget=300 fix applied.
1 live-log outcome in 34 bars (extreme outcome sparsity — 3%). correct_side=55.0% moderate.
Current knobs: magnitude_gate=0.04, max_onesided_cost=5.0, pace_urgency_lo=0.35, bar_budget=300.

Issue: Zero pair formation despite bar_budget fix. SOL_1h outcome sparsity is extreme (1/34 bars).
Prior best (pre-RESET): pair_cost=0.655, avg_profit=+$1.49/bar — high-value target.

Priority queue for rotation 3:
1. magnitude_gate=0.0 BASELINE — gate series shows 0.08=0, 0.04=0. Try gate=0.0.
   SOL_1h pre-RESET had pairs with gate=0.0. Outcome sparsity may still limit evaluation.
   Knobs: set magnitude_gate=0.0 before running.
2. If gate=0.0 gives non-zero pairs: pace_urgency_lo 0.35->0.30 next.
   SOL_1h 1.9% matched_ratio pre-RESET; earlier urgency may improve quality.
3. bar_budget 300->400 — avg_profit=+$1.49/bar pre-RESET is excellent; capital scale pending.
   Only after baseline confirms stability.

Blacklist: skip 0.35 (COLLAPSE iter 57), skip 0.40 (D iter 74), risk_ceil 0.20 (D iters 100-101),
conviction_market_start (GLOBAL BLACKLIST).

---

## XRP_5m (FROZEN — permanent)

FROZEN — auditor directive permanent. Structural dead-end.
fill_rate=15.6% (structural microstructure limit), zero pairs at all tested gates.
Correct_side=57.8% marginal. max_dd would be critical given structural limitations.

Do NOT run experiments. Skip in all rotations unless auditor formally lifts freeze.

---

## XRP_15m (pair_cost=0.950 at gate=0.04, KEEP rate 0% post-RESET)

Gate=0.04 baseline (iter 22): matched_ratio=0.72%, pair_cost=0.950.
PAIR FORMATION RETURNED at gate=0.04 (vs 0% at gate=0.08, iter 11).
But pair_cost=0.950 vs pre-RESET best 0.638 — significant regression.
correct_side=50.0% (down from 53.7% at gate=0.08). 9 live-log outcomes in 138 bars (6.5%).
Current knobs: magnitude_gate=0.04, max_onesided_cost=2.0, pace_urgency_lo=0.30, skip=0.45.

Observation: pace_urgency_lo=0.30 is the confirmed KEEP from pre-RESET (LANDMARK 18% gain).
pair_cost=0.950 is higher than expected — pre-RESET best was 0.638. This is rotation 2 baseline;
need rotation 3 experiments to recover.

Priority queue for rotation 3:
1. pace_urgency_lo 0.30->0.25 — primary lever. XRP_15m showed 18% gain from 0.35->0.30.
   Series continuation: test 0.25 next. Risk: matched_ratio=0.72% may collapse at 0.25.
   Accept KEEP if pair_cost improves >5% vs baseline 0.950. Floor 0.30 if collapse occurs.
2. bar_budget 200->250 — cautious capital scale on near-profitable pair.
   Only after pace series resolves. prior KEEP at 200 only.
3. magnitude_gate=0.0 — if pace_urgency tests don't reduce pair_cost below 0.85, try gate=0.0
   to expand pair formation pool and improve cost.

Blacklist: skip 0.40 (COLLAPSE iter 60), bar_budget 300 (D iter 75), risk_ceil 0.20 (D iter 87),
conviction_market_start (GLOBAL BLACKLIST).

---

## XRP_1h (pair_cost=0.812 at gate=0.04, KEEP rate 0% post-RESET)

Gate=0.04 baseline (iter 23): matched_ratio=4.2%, pair_cost=0.812.
BEST PERFORMER in rotation 2. pair_cost=0.812 (gap 0.85 target = only 0.038 remaining).
correct_side=70.4% strong signal. fill_rate=74.0% high. max_dd=8.0% safe.
avg_profit=+$0.10/bar positive (only 2 live-log outcomes — but positive).
Prior best (pre-RESET): pair_cost=0.674, avg_profit=+$1.08/bar — system-best avg_profit.
Auditor directive: PRIORITIZE XRP_1h (pair_cost improving).
Current knobs: magnitude_gate=0.04, max_onesided_cost=2.0, pace_urgency_lo=0.35, skip=0.50.

Note: knobs shows max_onesided_cost=2.0 (down from 5.0 in best_knobs) — this already happened.
Was this tested and KEPT? Results.tsv shows no KEEP for XRP_1h in rotation 2 — this was
pre-staged. The baseline at iter 23 ran with onesided=2.0 active. pair_cost=0.812 may already
reflect onesided=2.0 benefit.

Priority queue for rotation 3:
1. pace_urgency_lo 0.35->0.30 — primary lever from strategy queue. pair_cost=0.812 is close
   to 0.85 target; 0.30 urgency may push it below 0.85.
   Accept KEEP if pair_cost improves >2% (< 0.796) vs baseline 0.812.
2. pace_urgency_lo 0.30->0.25 — follow series if item #1 KEEPs.
3. pace_urgency_hi 0.85->0.75 — alternative urgency gate tuning if pace_lo series exhausts.
   Untested lever with potential upside on 1h TF.

Note: max_onesided_cost baseline effect needs documentation. Iter 23 effectively serves as the
onesided=2.0 baseline. No separate experiment needed unless pair_cost regresses.

Blacklist: skip 0.45/0.55, bar_budget 300, risk_ceil 0.20, pace_urgency_lo->0.45 (D iter 103),
conviction_market_start (GLOBAL BLACKLIST).
BOTH SKIP DIRECTIONS EXHAUSTED. BUDGET OPTIMUM AT 200. PACE_LO SERIES ACTIVE.

---

## Cross-Pair Observations

**Rotation 2 critical finding — gate=0.04 is still too aggressive for most pairs:**
- 7 of 11 active pairs: 0% matched_ratio at gate=0.04 (same collapse as gate=0.08)
- 4 pairs recovered at gate=0.04: ETH_1h (2%), SOL_15m (0.3%), XRP_15m (0.72%), XRP_1h (4.2%)
- Recovery pattern: 1h timeframe pairs recover first; 5m/15m pairs still collapse
- The 5m/15m pair formation is likely gated by outcome resolution, not the magnitude gate

**Outcome sparsity is the systemic bottleneck:**
- BTC_5m: 24/403 outcomes (6%) — gate=0.02 still fails
- BTC_15m: 8/136 outcomes (6%) — gate=0.04 fails
- BTC_1h: 1/34 outcomes (3%) — extreme sparsity
- ETH_5m: 27/406 outcomes (7%) — gate=0.04 fails
- ETH_15m: 8/136 outcomes (6%) — gate=0.04 fails
- SOL_5m: 28/407 outcomes (7%) — gate=0.04 fails
- SOL_1h: 1/34 outcomes (3%) — extreme sparsity
- XRP_1h: 2/34 outcomes (6%) — but pairs form because 1h moves clear gate threshold

**Implication:** The gate threshold reduction may not be the primary lever for 5m/15m pairs.
If matched_ratio remains 0% even at gate=0.0 on BTC_5m, the issue is that no buy/sell pairs
resolve within the same backtest window — structural dataset issue.

**Rotation 3 primary focus:**
1. Gate=0.0 baseline for all 7 failed pairs (BTC_5m, BTC_15m, BTC_1h, ETH_5m, ETH_15m, SOL_5m, SOL_1h)
2. XRP_1h pace_urgency series (highest immediate return potential, already near target)
3. XRP_15m pace_urgency series (pair_cost=0.950, needs reduction)
4. ETH_1h pace_urgency series (pair_cost=0.594, already good, continue improving)

**Pre-RESET structural knowledge retained:**
- pace_urgency_lo series: primary lever for 5m/15m/1h pairs (NOT for pairs with zero formation)
- Onesided floors: ETH_5m=1.5, ETH_15m=1.5, SOL_5m=2.0, BTC_5m=2.0, BTC_15m=2.0
- SOL_15m onesided: GLOBALLY BLACKLISTED for SOL_15m at any value below 5.0
- Skip floors: BTC_1h=0.40, ETH/SOL/XRP pairs floor=0.45; BTC_5m/XRP_1h floor=0.50
- BTC_15m skip=0.45 definitively fails (3x confirmed collapse)

---

## trader_a Benchmark Comparison (after rotation 2, iter 24)

| Pair | PairCost | Target | Gap | AvgProfit | MaxDD% | Status |
|------|----------|--------|-----|-----------|--------|--------|
| BTC_5m | 0.000 | < 0.85 | N/A | -$0.027/bar | 23.0% | FROZEN (gate=0.0 baseline needed) |
| BTC_15m | 0.000 | < 0.85 | N/A | -$0.218/bar | 22.1% | gate=0.0 baseline needed |
| BTC_1h | 0.000 | < 0.85 | N/A | -$0.240/bar | 4.8% | gate=0.0 baseline needed; fix risk_ceil |
| ETH_5m | 0.000 | < 0.85 | N/A | -$0.110/bar | 29.2% | gate=0.0 needed; DD WARNING |
| ETH_15m | 0.000 | < 0.85 | N/A | +$0.130/bar | 7.1% | gate=0.0 baseline needed |
| ETH_1h | 0.594 | < 0.85 | -0.256 | -$0.060/bar | 13.8% | ACTIVE — pace_urgency_lo test next |
| SOL_5m | 0.000 | < 0.85 | N/A | +$0.136/bar | 20.0% | gate=0.0 baseline needed |
| SOL_15m | 0.567 | < 0.85 | -0.283 | -$0.270/bar | 19.8% | FROZEN (correct_side=45.5%) |
| SOL_1h | 0.000 | < 0.85 | N/A | -$0.160/bar | 7.3% | gate=0.0 baseline needed |
| XRP_5m | N/A | < 0.85 | N/A | N/A | N/A | FROZEN (permanent) |
| XRP_15m | 0.950 | < 0.85 | +0.100 | -$0.234/bar | 19.3% | pace_urgency_lo 0.30->0.25 next |
| XRP_1h | 0.812 | < 0.85 | -0.038 | +$0.099/bar | 8.0% | PRIORITY — pace_urgency_lo 0.35->0.30 |

Pre-RESET best (expected to return with gate=0.0):
BTC_5m=0.922, BTC_15m=0.933, BTC_1h=0.799, ETH_5m=0.633, ETH_15m=0.560,
ETH_1h=0.706, SOL_5m=0.676, SOL_15m=0.696, SOL_1h=0.655, XRP_15m=0.638, XRP_1h=0.674

---

## Blacklist (per-pair)

- BTC_5m: gate=0.02/0.04/0.08 (collapse), skip 0.45/0.55, onesided 2.0->1.5 (COLLAPSE)
- BTC_15m: gate=0.04 (collapse), skip=0.45 (definitive 3x collapse), bar_budget 400
- BTC_1h: gate=0.04 (collapse), risk_ceil 0.10/0.20, skip 0.50, onesided 5->3
- ETH_5m: gate=0.04 (collapse), skip 0.60, onesided 1.5->1.0 (COLLAPSE)
- ETH_15m: gate=0.04 (collapse), skip above 0.50, onesided above 1.5 or below 1.5 (COLLAPSE at 1.0)
- ETH_1h: onesided above 5, skip 0.40, risk_ceil 0.20, bar_budget 250/300
- SOL_5m: gate=0.04 (collapse), skip 0.55, onesided 2.0->1.5 (COLLAPSE)
- SOL_15m: skip 0.40 (COLLAPSE), onesided ANY reduction from 5.0 (COLLAPSE), bar_budget 400
- SOL_1h: skip 0.35 (COLLAPSE), skip 0.40, risk_ceil 0.20
- XRP_5m: ALL (FROZEN permanent)
- XRP_15m: skip 0.40 (COLLAPSE), bar_budget 300, risk_ceil 0.20
- XRP_1h: skip 0.45/0.55, bar_budget 300, risk_ceil 0.20, pace_urgency_lo->0.45

## Global Blacklist

- conviction_market_start: GLOBALLY BLACKLISTED — fails across ALL tested pairs.
  DO NOT TEST on any remaining pair under any circumstances.
- magnitude_gate=0.08: confirmed too aggressive for 11/12 pairs.
  Rotation 2 confirms gate=0.04 still too aggressive for 7/11 active pairs.
  Next step: test gate=0.0 for all zero-formation pairs.
- magnitude_gate=0.04: still collapses BTC_5m, BTC_15m, BTC_1h, ETH_5m, ETH_15m, SOL_5m, SOL_1h.
  Do not expect improvement from gate=0.04 on these 7 pairs.
