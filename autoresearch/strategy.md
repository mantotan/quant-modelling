# Strategy Directive
Updated: 2026-03-26T22:30:00Z
After iteration: 150

## Program Status: num_leaves Narrowing Is the Live Lever

Iters 146-150 completed the strategy-after-145 queue. The reg_alpha forcing campaign is now
fully confirmed dead (0/5 KEEP across all assets). The pivotal finding from iters 148-149 is
that **num_leaves narrowing + n_estimators=[100,400]** produced back-to-back KEEPs:
- SOL/1h (iter 148): Brier 0.219333, beat best by 0.578% (40/40 trials, starvation resolved)
- XRP/1h (iter 149): Brier 0.222676, beat best by 1.866% (40/40 trials, starvation resolved)

This lever has NOT been applied to any 15m asset or to ETH/5m or SOL/5m. The 15m assets have
clean num_leaves convergence data (BTC=43, ETH=70, SOL=50) that has never been exploited.
Additionally, ETH/1h (iter 150) confirmed starvation is resolved at [100,400] but num_leaves=20
landed too low — a retest with [20,64] (excluding the lower tail) may distinguish the optimum.

## Priority Queue

1. **ETH/15m num_leaves=[48,96] + n_estimators=[100,400]**
   Rationale: iter 116 (best run) found num_leaves=70 with n_estimators=202 at [100,800] ceiling
   (23/40 trials). The 1h pattern (SOL: 46, XRP: 25, ETH: 20) shows tick-dominant assets prefer
   low-to-mid num_leaves. Narrowing to [48,96] centers on iter 116 optimum (70) while excluding
   wasted low range. Reducing ceiling to [100,400] matches 1h pattern (ETH n_estimators=202,
   well within 400). Expected to resolve residual starvation and find cleaner optimum.
   Specific knobs: `hpo_search_space.num_leaves=[48,96]`, `hpo_search_space.n_estimators=[100,400]`

2. **BTC/15m num_leaves=[24,64] + n_estimators=[100,400]**
   Rationale: iter 123 (best) found num_leaves=43 with n_estimators=235 (21/40 trials at 800
   ceiling). BTC assets show sniper pattern (WR ramp). num_leaves=43 confirmed across two runs
   (123: n_est=235, 114: n_est=53). Narrowing to [24,64] with 400 ceiling mirrors 1h success.
   BTC/15m is the second-best Brier overall (0.171809) — incremental improvement here has high
   signal value for deployment. n_estimators optimum ~235 is well within 400 ceiling.
   Specific knobs: `hpo_search_space.num_leaves=[24,64]`, `hpo_search_space.n_estimators=[100,400]`

3. **SOL/15m num_leaves=[32,72] + n_estimators=[100,400]**
   Rationale: iter 130 (best) found num_leaves=50 with n_estimators=154 (24/40 trials at 600
   ceiling). n_estimators=154 is well within 400 ceiling — reducing ceiling from 600 to 400
   saves search budget. Narrowing num_leaves to [32,72] centers on 50 optimum. SOL/15m had
   structural starvation resolved at 600; at 400 ceiling it should be fully starvation-free.
   Specific knobs: `hpo_search_space.num_leaves=[32,72]`, `hpo_search_space.n_estimators=[100,400]`

4. **ETH/5m num_leaves=[48,96] + n_estimators=[100,400]**
   Rationale: iter 117 (best) found num_leaves=70 with n_estimators=182 (23/40 trials at 800
   ceiling). Same profile as ETH/15m — consistent tick-dominant ETH pattern, num_leaves=70.
   n_estimators=182 well within 400 ceiling. Applying the same narrowing that worked for 1h
   assets. ETH/5m structural floor hypothesis can be tested: if starvation-free search at [48,96]
   still yields 0.2118-0.2120, the floor is confirmed. If improvement found, significant signal.
   Specific knobs: `hpo_search_space.num_leaves=[48,96]`, `hpo_search_space.n_estimators=[100,400]`

5. **SOL/5m num_leaves=[28,68] + n_estimators=[100,400]**
   Rationale: iter 121 (best) found num_leaves=47 with n_estimators=274 (24/40 trials at 800
   ceiling). SOL/5m mirrors SOL/15m and SOL/1h patterns. num_leaves=47 (iter 121), 50 (iter 130
   15m), 46 (iter 148 1h) — extremely consistent SOL optimum ~46-50. Narrowing [28,68] targets
   this range tightly. n_estimators=274 fits within 400 ceiling. Starvation likely resolved.
   Specific knobs: `hpo_search_space.num_leaves=[28,68]`, `hpo_search_space.n_estimators=[100,400]`

6. **ETH/1h num_leaves=[20,48] + n_estimators=[100,400]**
   Rationale: iters 147 and 150 both found num_leaves=20 (at or near lower bound of [16,64]).
   ETH/1h appears to prefer very low num_leaves (20 vs SOL=46, XRP=25). The [16,64] range
   may be too wide — HPO gravitates to lower tail. Test [20,48] to remove wasted upper range
   while allowing the true optimum to emerge cleanly. Both iter 147/150 had 40/40 trials
   starvation-free. No new lever, but tighter range may find 0.211438 improvement.
   Specific knobs: `hpo_search_space.num_leaves=[20,48]`, `hpo_search_space.n_estimators=[100,400]`

7. **XRP/15m num_leaves=[32,80] + n_estimators=[100,600]**
   Rationale: XRP/15m is confirmed structurally starved (23-29/40 trials even at 300-400 ceiling)
   because XRP/15m genuinely prefers n_estimators=599+ (at ceiling in all runs). The best run
   (iter 128) had num_leaves=128 AT the upper bound — this is not reliable. Try a wider
   num_leaves range anchored at a mid point with 600 ceiling to allow n_estimators to find
   its natural optimum while also exploring num_leaves. Lower priority due to structural floor.
   Specific knobs: `hpo_search_space.num_leaves=[32,80]`, `hpo_search_space.n_estimators=[100,600]`

## Observations

- **num_leaves narrowing KEEP rate: 2/2 (100%)** (iters 148 SOL/1h, 149 XRP/1h) — the highest
  single-lever success rate in the entire multi-tp era. Apply to all remaining assets.
- **reg_alpha forcing KEEP rate: 0/5 (0%)**: BTC/1h iter 139, ETH/5m iter 143, ETH/1h iter 144,
  XRP/15m iter 140, BTC/5m iter 146. Permanently blacklisted for all assets.
- **HPO range narrowing (num_leaves only) vs other range changes**: num_leaves narrowing has
  worked where n_estimators ceiling reduction alone did not, because it directly reduces the
  parameter space complexity without constraining the optimal region.
- **n_estimators optimum convergence**: 1h = 200-350 (SOL=224, XRP=207, ETH=342, BTC~350);
  15m = 150-250 (SOL=154, ETH=202, BTC=235); 5m = 182-274 (ETH=182, SOL=274, BTC=103 unstable).
  A ceiling of [100,400] is safe for all assets except BTC/5m (unstable) and XRP/15m (structural).
- **Anti-starvation num_leaves hypothesis**: tick-dominant assets (all ETH, SOL, XRP) show very
  consistent num_leaves optima across timeframes. ETH: 20-26 range (1h=20, 15m=70 outlier);
  SOL: 46-50 range; XRP: 25-34 range. BTC sniper assets: 40-43 range.
- **BTC/5m structural floor confirmed**: 7 consecutive DISCARDs since iter 104 (best 0.17605).
  Runs attempted: HPO re-run (122), n_splits=6 (127), reg_alpha forcing (146). Blacklisted.
- **XRP/15m structural floor confirmed**: starvation persists regardless of ceiling. 8/12 runs
  were DISCARD in multi-tp era. Structural n_estimators preference for 599+ is irresolvable.

## Risk Profile

- Max drawdown trend: stable across recent KEEPs — BTC/1h=1.01%, SOL/1h=0.91%, XRP/1h=6.25%
  (tick-dominant); BTC/5m=39.01% (sniper), BTC/15m=17.75% (sniper), BTC/1h=2.33% (sniper)
- dd/PnL ratio by asset type: sniper (BTC) = higher (0.39/48=$0.81/$ — acceptable);
  tick-dominant (ETH/SOL/XRP 1h) = ~$0.075/$73 = 0.001 (very low)
- Trade count range across KEEPs (multi-tp era): 5m/15m: 60K-81K (active); 1h: 16K-19K
  (active for 1h); all counts well above 50-trade minimum
- Win rate stability: BTC sniper = 62-67% (stable, well above 50%); tick-dominant = 49-51%
  (flat, consistent with tick-dominant hypothesis — these WRs are structural)
- HPO-OOS gap: Recent KEEPs show hpo_objective in range 0.17-0.50 vs oos_brier 0.17-0.22;
  gap is larger for tick-dominant assets (hpo includes trade penalty); stable trend, no overfitting

## Timeframe Coverage

- 5m: 16 iterations (iters 91+), 7 KEEPs (44%), best Brier=0.176050 (BTC/5m, iter 104)
- 15m: 18 iterations, 9 KEEPs (50%), best Brier=0.171809 (BTC/15m, iter 123)
- 1h: 24 iterations, 10 KEEPs (42%), best Brier=0.174676 (BTC/1h, iter 136)
- Recommendation: prioritize 15m (highest KEEP rate, best Brier) and underexplored num_leaves
  narrowing for 15m assets (ETH/15m, BTC/15m, SOL/15m) — none have received num_leaves tuning.

## Blacklist

- **reg_alpha=[0.1,5.0] forcing (all assets)**: 0/5 KEEP. Permanently blacklisted.
  Evidence: BTC/1h iter 139, XRP/15m iter 140, ETH/5m iter 143, ETH/1h iter 144, BTC/5m iter 146.
  Pattern: reg_alpha forcing causes or worsens starvation across all asset types.
- **BTC/5m optimization (any lever)**: 0/7 KEEP since iter 104. Permanently blacklisted.
  Evidence: iters 122, 127, 134, 146 all DISCARD. Structural dataset-size floor.
- **XRP/15m ceiling reduction below 600**: confirmed structural (iters 132, 140, 145).
  n_estimators prefers 500+ but per-trial cost prevents full search. Soft floor.
- **min_child_samples narrowing (ETH assets)**: 0/2 KEEP (iter 108 ETH/1h, iter 129 ETH/5m).
  Range contraction confirmed problematic: audit note 3 — range contraction KEEP rate = 0/6.
- **SOL/15m starvation at n_estimators=[100,800]**: confirmed structural (iters 97, 109, 126).
  Must use [100,600] or lower for SOL/15m.
- **BTC/1h lr=[0.005,0.03]**: iter 131 confirmed binding (lr=0.028 at ceiling). Use [0.005,0.05].

## HPO Range Recommendations

- **n_estimators (1h assets)**: narrow to [100, 400] — confirmed optimum in 200-350 range.
  Evidence: SOL/1h=224 (iter 148), XRP/1h=207 (iter 149), ETH/1h=342 (iters 147/150),
  BTC/1h=350 (at ceiling iter 136, ~230 range iters 137-138).
- **n_estimators (15m assets)**: narrow to [100, 400] — confirmed optimum 150-235.
  Evidence: SOL/15m=154 (iter 130), ETH/15m=202 (iter 116), BTC/15m=235 (iter 123).
- **num_leaves (ETH assets)**: narrow to [20, 48] — consistent ETH/1h convergence to 20-26.
  Evidence: iters 100 (26), 147 (20), 150 (20); ETH/15m=70 is an outlier to investigate.
- **num_leaves (SOL assets)**: narrow to [28, 68] — consistent SOL convergence to 46-50.
  Evidence: SOL/1h=46 (iter 148), SOL/15m=50 (iter 130), SOL/5m=47 (iter 121).
- **num_leaves (XRP assets)**: narrow to [16, 48] — confirmed XRP/1h=25 (iter 149), XRP/5m=31.
  Note: XRP/15m=128 unreliable (at ceiling with starvation, iter 128).
- **num_leaves (BTC assets)**: narrow to [24, 64] — BTC/15m=43 (iter 123), BTC/1h=76-87 range.
  Note: BTC/1h num_leaves higher than other assets (BTC sniper pattern, not tick-dominant).
- **learning_rate (BTC/1h)**: keep [0.005, 0.05] — resolved binding at [0.005, 0.03].
  Evidence: iter 133 lr=0.022, iter 136 lr=0.017, iter 137 lr=0.037 — all within 0.05 ceiling.
