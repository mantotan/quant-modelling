# Dutch Audit Report
After iteration 24 (2026-03-27T10:00:00Z)

## Directives

- FREEZE XRP_5m — PERMANENT FREEZE maintained from iter 119 audit; structural dead-end confirmed across 2 full rotations (max_dd=69%, fill_rate structural floor); skip in all rotations
- FREEZE BTC_5m — pair formation structurally blocked at gate=0.08, 0.04, 0.02 across 3 consecutive experiments (iters 1, 13, 24); magnitude_gate alone cannot fix BTC_5m; knobs already at gate=0.0 (correct); rotation 3 must run gate=0.0 baseline as FIRST priority; no other experiments until non-zero matched_ratio confirmed
- FREEZE SOL_15m — correct_side=45.5% at gate=0.04 (below 50%), worsening from 47.7% at gate=0.08; model directionally wrong on this pair more than right; pair formation near-zero (0.3%); must confirm correct_side recovers above 50% at gate=0.04 BASELINE before ANY experiments; hold all experiments pending next baseline
- CONTINUE BTC_15m — gate=0.04 baseline shows zero pairs (iter 14); rotation 3 MUST run max_onesided_cost 5.0->2.0 as the primary untested lever; knobs correctly pre-staged at onesided=2.0; if DISCARD then re-FREEZE
- CONTINUE BTC_1h — gate=0.04 baseline: zero pairs (iter 15); pair formation requires gate experiment series; knobs has pace_urgency_lo=0.45 (staged per prior audit); thin dataset (34 bars) limits experiment validity; run pace_urgency_lo=0.45 experiment in rotation 3
- CONTINUE ETH_5m — gate=0.04 baseline: zero pairs (iter 16); knobs has onesided=1.5, pace_urgency_lo=0.30 (pre-staged one step ahead); rotation 3: run gate=0.04 baseline first properly (zero pairs means baseline is invalid for experiment comparison); check if pace_urgency is the blocking variable
- CONTINUE ETH_15m — gate=0.04 baseline: zero pairs BUT correct_side=71.0% strong signal, avg_profit positive; knobs pre-staged at pace_urgency_lo=0.25 (two steps from best_knobs 0.35); rotation 3: test pace_urgency_lo 0.35->0.30 first (match strategy queue), not 0.25 directly
- CONTINUE ETH_1h — gate=0.04 restored pair formation: 2.0% matched_ratio, pair_cost=0.594 (best post-RESET); knobs correctly at pace_urgency_lo=0.30, onesided=5.0; rotation 3: pace_urgency_lo 0.35->0.30 experiment (knobs already staged; confirm this is the change being applied vs baseline 0.35)
- CONTINUE SOL_5m — gate=0.04 baseline: zero pairs (iter 19); knobs at pace_urgency_lo=0.30, onesided=2.0; same collapse pattern as BTC_5m; pair formation may require gate=0.0 like BTC_5m; rotation 3: test gate=0.0 ONLY IF BTC_5m gate=0.0 shows positive results; otherwise hold
- CONTINUE SOL_1h — gate=0.04 baseline: zero pairs (iter 21); stale bar_budget FIXED (300 confirmed); correct_side=55.0%, fill_rate=57.4%; rotation 3: run with best_knobs as true baseline; dataset extremely thin (34 bars)
- CONTINUE XRP_15m — gate=0.04 restored pair formation: 0.72% matched_ratio, pair_cost=0.950; knobs at pace_urgency_lo=0.30 (correctly matching best_knobs); rotation 3: pace_urgency_lo 0.30->0.25 per strategy queue (XRP_15m showed 18% gain with 0.35->0.30)
- PRIORITIZE XRP_1h — gate=0.04 improved: 4.2% matched_ratio, pair_cost=0.812 (vs 0.855 at gate=0.08); correct_side=70.4% consistent; knobs pre-staged at onesided=2.0; rotation 3: run onesided=2.0 experiment; highest avg_profit potential in system (+$1.08/bar pre-RESET)

## Per-Pair Assessment

| Pair | BestCost (pre-RESET) | R2 Baseline Cost | MatchedRatio | CorrectSide | MaxDD% | KnobsStatus | Trajectory | Action |
|------|---------------------|-----------------|--------------|-------------|--------|-------------|------------|--------|
| BTC_5m | 0.922 | 0.000 (gate=0.02, iter 24) | 0% | 62.9% | 23.0% | gate=0.0 staged | BLOCKED — 3 gates all zero pairs | FREEZE (gate=0.0 baseline needed) |
| BTC_15m | 0.933 | 0.000 (gate=0.04, iter 14) | 0% | 56.5% | 22.1% | onesided=2.0 staged | Baseline only; onesided test needed | CONTINUE |
| BTC_1h | 0.799 | 0.000 (gate=0.04, iter 15) | 0% | 68.4% | 4.8% | pace_urgency_lo=0.45 staged | Thin dataset (34 bars); blocked | CONTINUE |
| ETH_5m | 0.633 | 0.000 (gate=0.04, iter 16) | 0% | 52.0% | 29.2% | onesided=1.5, pace=0.30 staged | High DD from unmatched; blocked | CONTINUE |
| ETH_15m | 0.560 | 0.000 (gate=0.04, iter 17) | 0% | 71.0% | 7.1% | pace=0.25 (2 steps ahead) | Strong signal; need true baseline | CONTINUE |
| ETH_1h | 0.706 | 0.594 (gate=0.04, iter 18) | 2.0% | 62.1% | 13.8% | pace=0.30 staged (vs best=0.35) | BEST post-RESET; improving | CONTINUE |
| SOL_5m | 0.676 | 0.000 (gate=0.04, iter 19) | 0% | 56.4% | 20.0% | pace=0.30 staged | Same collapse as BTC_5m | CONTINUE |
| SOL_15m | 0.696 | 0.567 (gate=0.04, iter 20) | 0.3% | 45.5% | 19.8% | pace=0.30 staged | correct_side BELOW 50% and worsening | FREEZE (wait for signal recovery) |
| SOL_1h | 0.655 | 0.000 (gate=0.04, iter 21) | 0% | 55.0% | 7.3% | bar_budget=300 fixed | Thin dataset; need true baseline | CONTINUE |
| XRP_5m | 0.909 | N/A (FROZEN) | 0% | 57.8% | 13.4% | FROZEN | PERMANENT FREEZE | FREEZE |
| XRP_15m | 0.638 | 0.950 (gate=0.04, iter 22) | 0.72% | 50.0% | 19.3% | pace=0.30 (matches best) | Pairs returned; pace series next | CONTINUE |
| XRP_1h | 0.674 | 0.812 (gate=0.04, iter 23) | 4.24% | 70.4% | 8.0% | onesided=2.0 staged | BEST trajectory; pair cost dropping | PRIORITIZE |

## trader_a Gap Analysis

| Pair | R2 Cost | Pre-RESET Best | Target | Cost Gap | Profit | DD | ETA (rotations) |
|------|---------|----------------|--------|----------|--------|----|-----------------|
| XRP_1h | 0.812 | 0.674 | <0.85 | -4.5% (BEATS) | +$0.10/bar | 8.0% | 1-2 |
| ETH_1h | 0.594 | 0.706 | <0.85 | -30% (BEATS) | -$0.06/bar | 13.8% | 2-3 |
| SOL_15m | 0.567* | 0.696 | <0.85 | -33%* (misleading) | -$0.27/bar | 19.8% | blocked |
| XRP_15m | 0.950 | 0.638 | <0.85 | +11.8% (FAILS) | -$0.23/bar | 19.3% | 3-4 |
| ETH_5m | N/A | 0.633 | <0.85 | N/A | N/A | N/A | blocked |
| BTC_1h | N/A | 0.799 | <0.85 | N/A | N/A | N/A | blocked |
| ETH_15m | N/A | 0.560 | <0.85 | N/A | N/A | N/A | blocked |
| SOL_1h | N/A | 0.655 | <0.85 | N/A | N/A | N/A | blocked |
| SOL_5m | N/A | 0.676 | <0.85 | N/A | N/A | N/A | blocked |
| BTC_5m | N/A | 0.922 | <0.85 | N/A | N/A | N/A | blocked |
| BTC_15m | N/A | 0.933 | <0.85 | N/A | N/A | N/A | blocked |
| XRP_5m | FROZEN | 0.909 | <0.85 | FROZEN | -$0.32/bar | 13.4% | never |

*SOL_15m: pair_cost=0.567 artificially low (only 0.3% matched_ratio — very few pairs)

**Only 2 pairs with meaningful baseline costs post-RESET (ETH_1h and XRP_1h).** 9 others blocked due to pair formation collapse at gate=0.04. This is the defining challenge of rotation 3.

## Critical Findings from Rotation 2 (iters 13-24)

### 1. Pair formation collapse is STRUCTURAL for most 5m pairs

BTC_5m has now tested gate=0.08 (iter 1), gate=0.04 (iter 13), and gate=0.02 (iter 24) with 0% matched_ratio across all three. This confirms magnitude_gate alone cannot enable pair formation for BTC_5m. The pre-RESET baseline with gate=0.0 (disabled) achieved pair_cost=0.922 — gate is actively preventing pair formation by filtering out ALL bar movements on 5m timeframes. The researcher correctly advanced knobs to gate=0.0.

SOL_5m shows the identical pattern (gate=0.08 iter 7, gate=0.04 iter 19 both 0%). ETH_5m also zero at both gate levels (iters 4, 16).

Implication: ALL 5m pairs may require gate=0.0 (disabled). This is a systemic finding about 5m price magnitude in Polymarket — 5m bars simply do not move enough to clear a 2-4% gate.

### 2. 1h pairs uniquely benefit from magnitude_gate

XRP_1h formed pairs at both gate=0.08 (3.6%) and gate=0.04 (4.24%). ETH_1h: zero at gate=0.08 but 2.0% at gate=0.04 — gate=0.04 is the right value for ETH_1h. 1h bars have sufficient movement to clear the gate.

For 15m pairs: XRP_15m returned pair formation at gate=0.04 (0.72% vs 0% at gate=0.08). ETH_15m zero at both — may also need gate=0.0.

### 3. SOL_15m signal quality alarm — below-50% correct_side

SOL_15m correct_side: 47.7% at gate=0.08 (iter 8) and now 45.5% at gate=0.04 (iter 20). This is the only pair in the system where lower gate threshold WORSENS direction quality. The model is consistently wrong on SOL_15m direction when pairs form. This pair should be FROZEn until signal quality investigation can determine if this is a dataset window issue or structural model weakness. Do not run experiments on SOL_15m in rotation 3.

### 4. ETH_1h is the star of rotation 2 — pair_cost=0.594 at baseline

ETH_1h post-RESET baseline at gate=0.04: pair_cost=0.594, matched_ratio=2.0%, fill_rate=83.3%, max_dd=13.8%. This is BETTER than its pre-RESET best of 0.706. The RESET + fresh dataset window appears to have improved ETH_1h significantly. This pair is already beating the trader_a target of <0.85 at baseline. Aggressive optimization here can push below 0.55.

### 5. Knobs drift detected — multiple pairs pre-staged beyond queue

- BTC_15m knobs: max_onesided_cost=2.0 (pre-staged, not yet run) vs best_knobs=5.0. This is the correct next experiment (strategy queue #1 for rotation 3). Acceptable staging.
- ETH_15m knobs: pace_urgency_lo=0.25 but best_knobs=0.35. Queue says run 0.35->0.30 first, then 0.30->0.25. Knobs jumped TWO steps ahead. Must revert to 0.35 for first pace test, then stage 0.30 after KEEP.
- ETH_1h knobs: pace_urgency_lo=0.30 vs best_knobs=0.35. The strategy specified "test 0.35->0.30" — knobs correctly staged at 0.30 for that experiment.
- SOL_15m knobs: pace_urgency_lo=0.30 vs best_knobs=0.35. Same correct staging for 0.35->0.30 test.
- XRP_1h knobs: max_onesided_cost=2.0 vs best_knobs=5.0. Correct staging for onesided test.

**Action required**: ETH_15m researcher must revert knobs_ETH_15m.json pace_urgency_lo from 0.25 to 0.35 (matching best_knobs), then apply 0.35->0.30 as first experiment.

### 6. BTC_1h has stale risk_ceil in best_knobs

best_knobs_BTC_1h.json shows risk_ceil=0.2, but the previous auditor (iter 119) identified this as stale — iter 80 DISCARD confirmed risk_ceil=0.20 fails, correct floor is 0.15. The best_knobs_BTC_1h.json needs updating. However knobs_BTC_1h.json also shows risk_ceil=0.2 — researcher should set this to 0.15 in both files before running BTC_1h experiments.

### 7. Researcher compliance — good but one ETH_15m staging error

Rotation 2 compliance: GOOD overall. Researcher correctly:
- Ran all 11 active pairs in sequence (skipping frozen XRP_5m)
- Fixed SOL_1h bar_budget before baseline
- Ran gate=0.02 experiment on BTC_5m when gate=0.04 also yielded zero pairs
- Advanced to gate=0.0 in BTC_5m knobs (correct inference)
- Maintained XRP_5m FREEZE

Single error: ETH_15m knobs staged two steps ahead (0.25 vs required 0.35 start). Minor issue — easy to correct.

## Risk Flags

- **BTC_5m, SOL_5m, ETH_5m pair formation**: All 3 five-minute pairs have zero pairs at gate=0.04. If gate=0.0 does not restore pair formation on SOL_5m and ETH_5m, these pairs are structurally unable to form pairs in the current dataset window. A 5m regime change may have occurred.

- **SOL_15m correct_side below 50%**: Two consecutive baselines at 47.7% and 45.5%. Running optimization experiments on a pair where the model is directionally wrong yields meaningless results. The SOL_15m model quality issue must be diagnosed before further experimentation.

- **XRP_15m matched_ratio critically low**: 0.72% at gate=0.04 with pair_cost=0.950. Pair formation is barely active. The pace_urgency_lo=0.30->0.25 experiment carries meaningful collapse risk. Accept KEEP only if matched_ratio stays above 0.3%.

- **Thin datasets on all 1h pairs**: BTC_1h (34 bars), SOL_1h (34 bars), ETH_1h (33 bars), XRP_1h (34 bars). High variance per experiment result. No single experiment should be treated as definitive on 1h pairs — prefer consistency across 2 experiments.

- **BTC_1h best_knobs_BTC_1h.json has stale risk_ceil=0.20**: Must be corrected to 0.15 before any BTC_1h experiment to prevent incorrect baseline comparison.

## Recommendations for Rotation 3 (iters 25-36)

### Tier 1 — Gate=0.0 unlock experiments (CRITICAL — 5 pairs blocked)

1. **BTC_5m**: magnitude_gate=0.0 BASELINE. Knobs already staged. This is the ONLY experiment for BTC_5m in rotation 3. Accept as baseline (not KEEP/DISCARD). Expected: pair formation should return (pre-RESET had pair_cost=0.922 at gate=0.0).

2. **SOL_5m**: After BTC_5m gate=0.0 result — if BTC_5m shows non-zero pairs, test SOL_5m with gate=0.0 as BASELINE. If BTC_5m also fails at gate=0.0: investigate dataset window (may need outcome resolution refresh).

3. **ETH_5m**: Same gate=0.0 test after BTC_5m and SOL_5m results. Zero pairs at gate=0.04 with only 27 outcomes loaded vs 406 bars suggests outcome resolution is the actual bottleneck — magnitude_gate may be irrelevant if outcomes aren't loading. Investigate outcome source.

### Tier 2 — Active optimization on pairs with pair formation (HIGH VALUE)

4. **XRP_1h**: max_onesided_cost 5.0->2.0. Knobs pre-staged at onesided=2.0. pair_cost=0.812 at baseline; onesided cap historically drives cost down on pairs with good signal. DD=8% provides headroom. Most promising experiment in rotation 3.

5. **ETH_1h**: pace_urgency_lo 0.35->0.30. Knobs at 0.30 (correctly staged). pair_cost=0.594 already excellent — pace optimization can push further. XRP_15m showed 18% gain with this move.

6. **XRP_15m**: pace_urgency_lo 0.30->0.25. Knobs at 0.30 (correctly matching best_knobs). Continue the series that gave 18% gain at 0.30. Risk: matched_ratio=0.72% may collapse at 0.25.

### Tier 3 — Baseline-required pairs

7. **BTC_15m**: max_onesided_cost 5.0->2.0. Knobs pre-staged. Zero pairs at gate=0.04 — but strategy notes BTC_15m had 12% matched_ratio pre-RESET (the highest in the system). Run the experiment; if it unlocks pair formation, this is a significant result.

8. **BTC_1h**: pace_urgency_lo 0.35->0.45. Knobs pre-staged at 0.45. FIRST: fix risk_ceil in both knobs_BTC_1h.json and best_knobs_BTC_1h.json from 0.20 to 0.15. Then run pace experiment.

9. **ETH_15m**: FIRST fix knobs_ETH_15m.json pace_urgency_lo from 0.25 back to 0.35 (matching best_knobs). Then run pace_urgency_lo 0.35->0.30 as rotation 3's experiment.

10. **SOL_1h**: Run with best_knobs (bar_budget=300, pace_urgency_lo=0.35, gate=0.04) as true baseline. Bar_budget stale fix confirmed. Expect zero pairs — same gate=0.04 blocked pattern.

### Tier 4 — Hold

11. **SOL_15m**: HOLD all experiments. correct_side=45.5% is disqualifying. Researcher must monitor if the next baseline at gate=0.04 shows recovery. Do not run experiments on a pair where the model is directionally wrong.

12. **XRP_5m**: PERMANENT FREEZE. No experiments.

### Pair experiment order for rotation 3

Recommended sequence: BTC_5m (gate=0.0 baseline), BTC_15m (onesided=2.0), BTC_1h (pace=0.45), ETH_5m (gate=0.0 baseline), ETH_15m (fix+pace=0.30), ETH_1h (pace=0.30), SOL_5m (gate=0.0 baseline), SOL_15m (SKIP), SOL_1h (baseline), XRP_15m (pace=0.25), XRP_1h (onesided=2.0)

### Required knobs fixes before experiments

| Pair | File | Current Value | Must Be | Reason |
|------|------|---------------|---------|--------|
| BTC_1h | knobs_BTC_1h.json | risk_ceil=0.20 | risk_ceil=0.15 | Stale — iter 80 DISCARD |
| BTC_1h | best_knobs_BTC_1h.json | risk_ceil=0.20 | risk_ceil=0.15 | Same stale value |
| ETH_15m | knobs_ETH_15m.json | pace_urgency_lo=0.25 | pace_urgency_lo=0.35 | Jumped 2 steps ahead; revert to best_knobs baseline |

## Researcher Compliance Assessment

Rotation 2 (iters 13-24): GOOD with one correction needed.
- Correctly ran all 11 active pairs in order (XRP_5m skipped per FREEZE)
- Correctly fixed SOL_1h bar_budget=300 before baseline (iter 21)
- Correctly inferred gate=0.0 needed for BTC_5m after 3 failures (gate=0.08, 0.04, 0.02)
- Correctly maintained XRP_5m FREEZE directive
- ERROR: ETH_15m knobs pre-staged at pace_urgency_lo=0.25 (two steps ahead — correct queue is 0.35->0.30 first)
- No dangerous experiments run on frozen/blocked pairs

Compliance rate: 10/11 correct = 91%. One staging error to fix before rotation 3.
