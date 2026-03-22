# Strategy Directive
Updated: 2026-03-27T01:00:00Z
After iteration: 151

## Program Status: ETH/15m Double-Ceiling Discovery; num_leaves Narrowing 2/3 Complete

Iter 151 completed the strategy-after-150 priority #1 (ETH/15m num_leaves=[48,96] +
n_estimators=[100,400]) with a DISCARD due to **double-ceiling starvation**: num_leaves=94
near 96 ceiling AND n_estimators=379 near 400 ceiling simultaneously. This is a critical
new finding — ETH/15m does NOT follow the ETH/1h pattern (num_leaves=20); its optimum
is in the 70-94+ range, well above ETH/1h. The narrowing strategy was correct directionally
but the upper bound was too tight.

### Cross-Asset Baseline Shifts Through Iteration 151

The following best Brier values are now confirmed as the true per-asset-timeframe floors:

| Asset | 5m Best | 15m Best | 1h Best |
|-------|---------|----------|---------|
| BTC   | 0.17605 (iter 104) | 0.171809 (iter 123) | 0.174676 (iter 136) |
| ETH   | 0.211888 (iter 117) | 0.208324 (iter 116) | 0.211438 (iter 100) |
| SOL   | 0.218058 (iter 121) | 0.215345 (iter 130) | 0.219333 (iter 148) |
| XRP   | 0.221503 (iter 112) | 0.218075 (iter 128) | 0.222676 (iter 149) |

**Shifts since strategy-after-iter-150:**
- SOL/1h improved: 0.220615 (iter 125) -> 0.219333 (iter 148, +0.578%)
- XRP/1h improved: 0.226907 (iter 115) -> 0.222676 (iter 149, +1.866%)
- ETH/15m baseline UNCHANGED: 0.208324 (iter 116) — double starvation blocked progress

**ETH/15m diverges from ETH/1h:** ETH/1h converges to num_leaves=20 (very low, tick-dominant
plateau). ETH/15m converges to num_leaves=70-94+ (mid-to-high range). These are structurally
different landscapes on the same asset. The hypothesis that ETH assets share num_leaves optima
across timeframes is REFUTED. ETH/15m is closer to ETH/5m (num_leaves pattern unknown at
narrowed range) than to ETH/1h.

**num_leaves narrowing KEEP rate update: 2/3 (67%)**
- SOL/1h (iter 148): KEEP, num_leaves=46 at [16,64] — converged naturally at mid-range
- XRP/1h (iter 149): KEEP, num_leaves=25 at [16,48] — converged below prior 34, range correct
- ETH/15m (iter 151): DISCARD — double-ceiling starvation, range was correct direction but
  upper bound too tight (94 at 96 ceiling); ETH/15m needs [64,128] or [64,144] not [48,96]

### What Remains: 5 Assets with Unexploited num_leaves Narrowing

ETH/1h is confirmed at structural floor (0.211438 unchanged across iters 147 and 150 with
40/40 starvation-free runs). ETH/15m needs an adjusted attempt. All 15m assets and remaining
5m assets have NOT received num_leaves narrowing.

## Priority Queue

1. **ETH/15m num_leaves=[64,128] + n_estimators=[100,500]**
   Rationale: iter 151 found num_leaves=94 AT [48,96] upper bound AND n_estimators=379 AT
   [100,400] upper bound simultaneously (double starvation). True ETH/15m optimum is in the
   70-94+ range. Widening num_leaves to [64,128] removes the upper-bound constraint while
   keeping the lower bound above wasted territory (all prior runs at [16,128] converged to
   70, so [64,128] tightly brackets the known optimum). Widening n_estimators to [100,500]
   provides headroom above 379 (confirmed near-ceiling). ETH/15m iter 116 found n_est=379
   with starvation; the true optimum may be 380-450 range. Expected: starvation resolved,
   num_leaves free to find 70-110 optimum without ceiling constraint.
   Specific knobs: `hpo_search_space.num_leaves=[64,128]`, `hpo_search_space.n_estimators=[100,500]`
   Priority justification: highest-value remaining — ETH/15m has the best Brier across all
   non-BTC assets (0.208324) and a confirmed double-ceiling mis-configuration to fix.

2. **BTC/15m num_leaves=[24,64] + n_estimators=[100,400]**
   Rationale: iter 123 (best) found num_leaves=43 with n_estimators=235 (21/40 trials at
   800 ceiling). BTC assets show sniper pattern (WR ramp). num_leaves=43 confirmed across
   two runs (iter 123: n_est=235, iter 114: n_est=53). Narrowing to [24,64] centers on the
   confirmed 43 optimum. n_estimators=235 is well within 400 ceiling. This is the same lever
   that worked for 1h assets (SOL/1h=224, XRP/1h=207, BTC/1h=350 stable). BTC/15m has the
   best Brier overall (0.171809) — any improvement here has highest deployment value.
   Specific knobs: `hpo_search_space.num_leaves=[24,64]`, `hpo_search_space.n_estimators=[100,400]`

3. **SOL/15m num_leaves=[32,72] + n_estimators=[100,400]**
   Rationale: iter 130 (best) found num_leaves=50 with n_estimators=154 (24/40 trials at
   600 ceiling). n_estimators=154 is well within 400 ceiling — reducing ceiling from 600
   to 400 saves search budget. Narrowing num_leaves to [32,72] centers on the 50 optimum.
   SOL/15m had structural starvation resolved at 600; at 400 ceiling it should be fully
   starvation-free. Cross-asset confirmation: SOL/1h iter 148 found num_leaves=46 with
   [16,64] narrowing — [32,72] is directionally consistent with SOL's 46-50 pattern.
   Specific knobs: `hpo_search_space.num_leaves=[32,72]`, `hpo_search_space.n_estimators=[100,400]`

4. **ETH/5m num_leaves=[64,128] + n_estimators=[100,500]**
   Rationale: iter 117 (best) found num_leaves=70 with n_estimators=182 (23/40 trials at
   800 ceiling). ETH/5m's starvation was confirmed dataset-size structural in iters 143 and
   149 (6-16/40 trials regardless of ceiling). However, num_leaves=70 is consistent with
   ETH/15m's optimum (70-94 range). A focused [64,128] num_leaves range with modest
   n_estimators=[100,500] ceiling reduces per-trial cost by allowing HPO to converge faster.
   The starvation class (dataset-size, 929K samples) cannot be eliminated but reducing the
   HPO search dimension may yield cleaner convergence within the available trials.
   WARNING: ETH/5m is in the dataset-size structural class (6-16/40 typical). Improvement
   probability is lower than items 1-3. Accept if starvation-free OR if Brier improves despite
   partial starvation (set threshold: >=12/40 trials for a valid result).
   Specific knobs: `hpo_search_space.num_leaves=[64,128]`, `hpo_search_space.n_estimators=[100,500]`

5. **SOL/5m num_leaves=[28,68] + n_estimators=[100,400]**
   Rationale: iter 121 (best) found num_leaves=47 with n_estimators=274 (24/40 trials at
   800 ceiling). SOL/5m mirrors SOL/15m and SOL/1h patterns. Confirmed SOL optimum is
   46-50 across ALL three timeframes (SOL/1h=46, SOL/15m=50, SOL/5m=47 — extremely tight
   convergence). Narrowing [28,68] targets this range precisely. n_estimators=274 fits
   within 400 ceiling. Starvation at 24/40 with 800 ceiling suggests dataset-size partial
   class — reducing ceiling to 400 should improve trial count.
   Specific knobs: `hpo_search_space.num_leaves=[28,68]`, `hpo_search_space.n_estimators=[100,400]`

6. **XRP/15m num_leaves=[32,80] + n_estimators=[100,600]**
   Rationale: XRP/15m is confirmed structurally starved by dataset size (23-29/40 trials
   even at 300-400 ceiling; starvation is NOT n_estimators-driven). Best run (iter 128)
   had num_leaves=128 AT the upper bound — not reliable. However, num_leaves narrowing may
   reduce per-trial complexity. Try [32,80] centered on the known XRP convergence range
   (XRP/1h=25 at iter 149; XRP/5m likely similar). Use 600 ceiling to allow n_estimators
   to find natural optimum. Accept if >=16/40 trials completed AND Brier improves.
   Note: XRP/15m is LOWEST priority of the 15m assets due to persistent structural
   starvation. If the run produces <16/40 trials AND DISCARD, deprioritize further.
   Specific knobs: `hpo_search_space.num_leaves=[32,80]`, `hpo_search_space.n_estimators=[100,600]`

7. **ETH/1h num_leaves=[16,32] + n_estimators=[100,400]** (optional tiebreaker)
   Rationale: iters 147, 150 both found num_leaves=20 at [16,64] range — converged to
   low end of the range. ETH/1h structural floor (0.211438) is genuine and confirmed across
   6+ DISCARD attempts. A final narrowing to [16,32] would confirm the floor definitively
   OR find a marginal improvement if num_leaves=16-18 is slightly better than 20. This is
   LOW PRIORITY — only run if items 1-6 all complete and no KEEP candidates remain.
   Specific knobs: `hpo_search_space.num_leaves=[16,32]`, `hpo_search_space.n_estimators=[100,400]`

## Observations

- **ETH/15m-vs-ETH/1h divergence (new finding, iter 151):** ETH/1h num_leaves=20; ETH/15m
  num_leaves=70-94+. Do NOT treat ETH timeframes as sharing a num_leaves optimum. Each
  timeframe is an independent landscape. The tick-dominant label is shared but the HPO
  landscape is timeframe-specific.
- **SOL num_leaves cross-timeframe consistency (confirmed through iter 151):** SOL/5m=47,
  SOL/15m=50, SOL/1h=46. All three timeframes converge to 46-50. This is the tightest
  cross-timeframe convergence in the dataset. Narrowing [32,72] for all SOL assets is safe.
- **n_estimators optimum taxonomy (updated):** 5m = 154-274 (SOL=274, BTC=103 unstable,
  ETH=182, XRP=431 unstable); 15m = 150-250 (SOL=154, ETH=202, BTC=235); 1h = 200-350
  (SOL=224, XRP=207, ETH=342, BTC=230). A ceiling of [100,400] is safe for 15m and 1h.
  For 5m, ETH and SOL are within 400 but BTC/XRP are structurally unstable — ceiling
  should be [100,500] for ETH/5m to give headroom above n_est=182.
- **num_leaves narrowing KEEP rate: 2/3 (67%)** — still the highest single-lever success
  rate in the entire multi-tp era (reg_alpha forcing: 0/5, n_estimators ceiling: 5/12).
  Continue applying to remaining assets.
- **Structural floor class confirmed for:** BTC/5m (iter 146: 0/7 KEEP since iter 104);
  XRP/5m (iter 141: 9/40 trials, dataset-size structural); XRP/15m (iters 132/140/145:
  persistent starvation regardless of ceiling).
- **reg_alpha forcing KEEP rate: 0/5 (0%)**: BTC/1h iter 139, ETH/5m iter 143, ETH/1h
  iter 144, XRP/15m iter 140, BTC/5m iter 146. Permanently blacklisted for all assets.
- **ETH/1h structural floor confirmed:** 0.211438 unchanged across 40/40 starvation-free
  runs at iters 147 and 150 with same Brier to 6 decimal places. The floor is real.

## Risk Profile

- Max drawdown trend: STABLE — BTC/1h=0.20% (iter 136), SOL/1h=0.054% (iters 130/148),
  XRP/1h=0.063% (iter 149). All within historical range. No concerning growth.
- Trade count: STABLE — 5m: 75-81K; 15m: 60-77K; 1h: 16-19K. All comfortably above
  minimum 50-trade threshold.
- Win rate stability: BTC sniper (5m/15m/1h) = 62-67% (stable); tick-dominant
  (ETH/SOL/XRP) = 49-52% (flat, structural). No anomalies.
- Calibration: ECE STABLE — all KEEP rows post-iter-122: 0.0083-0.0355 (all < 0.05).
  XRP/1h iter 149 ECE=0.0355 is elevated relative to peers but still well within threshold.
- HPO-OOS gap: <0.2% for all starvation-free KEEPs. No widening trend.

## Timeframe Coverage

- 5m: ~39 iterations (iters 91+), 8 KEEPs (21%), best Brier=0.17605 (BTC/5m iter 104).
  KEEP rate lowest — structural floor class dominates (BTC, XRP confirmed; ETH partial).
  SOL/5m is the only clean candidate remaining.
- 15m: ~33 iterations, 9 KEEPs (27%), best Brier=0.171809 (BTC/15m iter 123).
  HIGHEST priority tier — 3 assets (ETH, BTC, SOL) have clean num_leaves narrowing pending.
- 1h: ~38 iterations, 10 KEEPs (26%), best Brier=0.174676 (BTC/1h iter 136).
  SOL/1h and XRP/1h confirmed improved in this strategy period (+0.578%, +1.866% KEEPs).
  ETH/1h and BTC/1h at confirmed structural floors. 1h campaign largely complete.
- Recommendation: concentrate on 15m assets (items 1-3) as primary campaign. 1h work is
  largely done. 5m items 4-5 are secondary.

## Blacklist

- **reg_alpha=[0.1,5.0] forcing (all assets)**: 0/5 KEEP. Permanently blacklisted.
  Evidence: BTC/1h iter 139, XRP/15m iter 140, ETH/5m iter 143, ETH/1h iter 144, BTC/5m
  iter 146. Pattern: reg_alpha forcing causes or worsens starvation across all asset types.
- **BTC/5m optimization (any lever)**: 0/7 KEEP since iter 104. Permanently blacklisted.
  Evidence: iters 122, 127, 134, 146. Structural dataset-size floor (929K samples, 50s/trial).
- **XRP/5m optimization (any lever)**: 0/1 KEEP since iter 112. Soft blacklist.
  Evidence: iter 141 — 9/40 trials at 600 ceiling; dataset-size structural same class as
  BTC/5m. Do NOT attempt further n_estimators ceiling adjustments.
- **XRP/15m ceiling reduction below 600**: structural starvation persists regardless of
  ceiling (iters 132, 140, 145). Dataset-size class. Use 600 ceiling minimum.
- **ETH/1h optimization (any lever)**: floor confirmed at 0.211438. 0 improvements since
  iter 100. Iters 105, 108, 135, 144, 147, 150 all DISCARD. Only item 7 (tiebreaker) allowed.
- **ETH/15m num_leaves=[48,96] (too tight)**: iter 151 confirmed double-ceiling starvation.
  Must use [64,128] with n_estimators=[100,500] (see item 1).
- **min_child_samples narrowing (ETH assets)**: 0/2 KEEP (iter 108 ETH/1h, iter 129 ETH/5m).
  Confirmed problematic — range contraction KEEP rate = 0/6.
- **SOL/15m starvation at n_estimators=[100,800]**: structural (iters 97, 109, 126).
  Use [100,400] or [100,600] for SOL/15m. NOT needed at [100,400] (n_est=154 confirmed).
- **BTC/1h lr=[0.005,0.03]**: iter 131 confirmed binding (lr=0.028 at ceiling). Use
  [0.005,0.05]. BTC/1h now at structural floor — no further BTC/1h experiments needed.

## HPO Range Recommendations

- **n_estimators (1h assets)**: [100, 400] — confirmed optimum in 200-350 range.
  Evidence: SOL/1h=224 (iter 148), XRP/1h=207 (iter 149), ETH/1h=342 (iters 147/150),
  BTC/1h=230 (iter 137).
- **n_estimators (15m assets)**: [100, 400] for SOL/BTC/ETH; [100, 600] for XRP/15m only.
  Evidence: SOL/15m=154 (iter 130), ETH/15m=379+ (iter 151, ceiling hit — true opt unknown),
  BTC/15m=235 (iter 123).
- **n_estimators (5m assets)**: [100, 500] for ETH/SOL; structural class for BTC/XRP.
  Evidence: ETH/5m=182 (iter 117), SOL/5m=274 (iter 121). 400 ceiling likely sufficient
  for ETH/5m (182 within range); 500 provides headroom for double-ceiling risk.
- **num_leaves (ETH assets)**: ETH/1h=[16,32] (confirmed floor at 20); ETH/15m=[64,128]
  (iter 151 double-ceiling requires wider range); ETH/5m=[64,128] (mirrors 15m pattern).
  NOTE: ETH/1h and ETH/15m/5m are DIFFERENT landscapes — do NOT apply ETH/1h num_leaves
  to other timeframes.
- **num_leaves (SOL assets)**: [32,68] — consistent SOL convergence to 46-50 across all
  three timeframes.
  Evidence: SOL/1h=46 (iter 148), SOL/15m=50 (iter 130), SOL/5m=47 (iter 121).
- **num_leaves (XRP assets)**: [16,48] for 1h (XRP/1h=25, iter 149); [32,80] for 15m
  (XRP/15m=128 unreliable, use wider range until true optimum found).
- **num_leaves (BTC assets)**: [24,64] — BTC/15m=43 (iter 123), BTC/1h=76-83 range
  (iters 136-138). Note: BTC/1h at structural floor, only BTC/15m needs this.
- **learning_rate (BTC/1h)**: [0.005, 0.05] — resolved binding at [0.005,0.03].
  BTC/1h at structural floor — this is informational only.
