# Strategy Directive
Updated: 2026-03-26T17:30:00Z
After iteration: 145

## Program Status: Structural Floor — Switching to Fresh Levers

Iters 141-145 executed items 1-4 from the post-iter-140 queue. All 4 were DISCARD.
The reg_alpha=[0.1,5.0] forcing campaign is now officially exhausted (0/4 KEEP across
BTC/1h iter 139, ETH/5m iter 143, ETH/1h iter 144, XRP/15m iter 140). XRP/15m starvation
is confirmed structural regardless of ceiling (iters 128/132/145: best=218.075 at [100,600]).
All previously identified levers have been fully exercised.

The program must pivot to fresh experiments: ETH/1h anti-starvation, SOL/1h fine-tuning,
BTC/5m reg_alpha (pending item 5 from prior strategy), and walk-forward exploration for
tick-dominant assets.

## Priority Queue

1. **BTC/5m reg_alpha=[0.1,5.0] + n_estimators=[100,800]**
   Rationale: This is item 5 from the post-iter-136 strategy, not yet executed.
   BTC/5m baseline is 0.17605 (iter 104). Best pre-multi-tp was 0.101759 with reg_alpha=2.854
   (significant L1 regularization). The multi-tp model at 0.176 may benefit from forced L1
   regularization to suppress noise across the 5-sample/bar expanded feature space.
   Change: `hpo_search_space.reg_alpha: [0.1, 5.0]`, `n_estimators: [100, 800]`

2. **ETH/1h anti-starvation n_estimators=[100,400]**
   Rationale: ETH/1h current best is 0.176103 (iter 89, pre-multi-tp) and 0.211438
   (iter 100, multi-tp baseline). Iter 144 tried reg_alpha=[0.1,5.0]+n_est=[100,1500]
   and got DISCARD at 0.212163. The 1500 ceiling may cause starvation at 1h (fewer bars
   per fold). Lower ceiling [100,400] to fix HPO starvation first, then evaluate reg_alpha.
   Change: `hpo_search_space.n_estimators: [100, 400]`, restore `reg_alpha: [1e-8, 10.0]`

3. **SOL/1h num_leaves narrowing [16, 64]**
   Rationale: SOL/1h best_params across KEEPs: iter 90 num_leaves=98, iter 101 num_leaves=32.
   High variance in num_leaves optimum suggests the 1h landscape is shallow. Narrow to [16, 64]
   based on iter 101 (multi-tp baseline). SOL/1h current best 0.220615 (iter 125, reg_alpha widen).
   Change: `hpo_search_space.num_leaves: [16, 64]`, `n_estimators: [100, 400]`

4. **ETH/5m purge_period narrowing — try 12 (re-test at multi-tp scale)**
   Rationale: ETH/5m pre-multi-tp best was at purge_period=12 (iter 29 KEEP at 0.177773,
   purge 24->12). Current multi-tp baseline 0.211888 was trained with default purge_period=24.
   The multi-tp model has 5x the sample density — shorter purge may be appropriate.
   Current best ETH/5m 0.211888 (iter 117). Low risk, 1 param change.
   Change: `walk_forward.purge_period: 12` (ETH/5m only)

5. **XRP/1h num_leaves narrowing [16, 48]**
   Rationale: XRP/1h best_params: iter 91 num_leaves=23, iter 102 num_leaves (unknown).
   Best Brier 0.226907 (iter 115). Consistent with narrow-leaf optimum at 1h bars.
   Narrow to [16, 48] based on pre-multi-tp convergence. Low risk.
   Change: `hpo_search_space.num_leaves: [16, 48]`, `n_estimators: [100, 400]`

## Observations

- **KEEP rates by category:**
  - multi-tp revalidation: 11/12 (91%) — program-defining success, all baselines established
  - purge_period tuning: 5/6 (83%) — highest reliability lever (exhausted)
  - train_bars tuning: 16/31 (51%) — productive early, diminishing now
  - hpo_rerun (fresh trials): 2/4 (50%) — useful when starvation resolved
  - feature selection: 7/19 (36%) — mixed, most features already included
  - anti_starvation (ceiling reduction): 8/27 (29%) — produced 8 improvements but now
    exhausted for most asset-timeframes
  - hpo_narrowing: 2/9 (22%) — generally fails due to starvation or wrong direction
  - reg_alpha forcing [0.1,5.0]: 0/4 (0%) — officially exhausted after iters 139-144
  - stochastic_rerun: 0/2 (0%) — confirms stochastic basin is structural, not noise

- **reg_alpha forcing conclusion:** BTC/1h iter 139 confirmed HPO gravitates to lower bound
  0.1073 when bounded [0.1,5.0] — near-minimum viable regularization, not zero. But Brier
  still misses floor by 0.032%. All 4 attempts (BTC/1h, ETH/5m, ETH/1h, XRP/15m) failed.
  DO NOT retry reg_alpha forcing for any asset currently at structural floor.

- **XRP/15m structural conclusion:** 3 independent ceiling reductions (600, 400, 300) all
  show 23-29/40 trials with starvation PERSISTING. Unlike ETH/15m (resolved at 800) and
  SOL/15m (resolved at 600), XRP/15m starvation is dataset-size driven — fewer samples per
  fold at 15m resolution. No further ceiling reduction experiments for XRP/15m.

- **BTC/1h basin confirmed:** Stochastic re-runs at [100,250] both miss 0.174676 by <0.03%
  (iters 137 and 138: 0.175037 and 0.174979). Basin floor ~0.1746-0.1750 is structural.
  n_estimators optimum ~180-230. The BTC/1h floor is not improvable by HPO alone.

- **Multi-tp Brier inflation pattern (systematic):** All 12 multi-tp models show Brier
  increase vs pre-multi-tp (10-82% higher). BTC-class assets show larger increases (BTC/5m
  +74%, BTC/1h +82%) vs tick-dominant assets (ETH/5m +20%, SOL/5m +15%). This is expected
  — multi-tp averages across all time buckets including early low-signal snapshots.

- **HPO-OOS gap analysis (hpo_objective vs oos_brier):**
  - BTC-class assets: gap small (BTC/1h iters 107/136: gap ~0.001) — well-calibrated HPO
  - Tick-dominant 5m: large gap (SOL/5m 0.237, XRP/5m 0.241) — trade penalty composite
    dominates hpo_objective, not a sign of overfitting
  - ETH/15m: moderate gap (0.086-0.103) — stable across KEEPs, no drift
  - Gap trend: STABLE. No widening detected across the post-OVERRIDE period.

- **n_estimators convergence (post-anti-starvation):**
  - ETH/15m: optimum ~350-500 (resolved at ceiling [100,800])
  - SOL/15m: optimum ~400-600 (resolved at ceiling [100,600])
  - XRP/15m: optimum ~273 at [100,300] but starvation structural — XRP dataset smaller
  - BTC/1h: optimum ~180-230 at [100,350] — confirmed by 3 independent runs
  - BTC/15m: optimum resolved at [100,800]
  - SOL/5m: resolved at [100,800]

## Risk Profile

- **Max drawdown trend:** Stable across post-OVERRIDE KEEP rows
  - BTC/5m: 0.39 (consistent with large trade volume 80K+)
  - BTC/1h: 0.23 (iters 107, expected malformed row 136)
  - Tick-dominant assets: 0.054-0.088 (low and stable)
  - No asset shows drawdown growth trend. All well within 30% threshold.
- **Drawdown / PnL ratio:**
  - BTC/5m: maxdd/sharpe ratio stable (0.39/79 = 0.005 — excellent)
  - Tick-dominant 5m/15m: maxdd very low relative to Sharpe (0.07/140+ = 0.0005)
  - BTC/1h: 0.23/24 = 0.010 — slightly elevated but acceptable
- **Trade count range across KEEPs:**
  - 5m assets: 80,783-81,000 (very stable, no sudden drops)
  - 15m assets: 62,509-77,369 (ETH/15m slightly lower due to train_bars=14K)
  - 1h assets: 16,213-19,345 (stable, expected 4x fewer than 15m)
- **Win rate stability:**
  - BTC-class assets: 62-87% (regime-sensitive, monotonically increasing with volatility)
  - Tick-dominant assets: 49-54% (flat — calibrated probability output, not directional)
  - Win rates STABLE across iterations within each class. No fragility detected.
- **HPO-OOS gap:** Latest gap stable (see above). Trend: STABLE across all 12 asset-TFs.

## Timeframe Coverage

- **5m:** 75 iterations, 24 KEEPs (32%), best Brier by asset:
  BTC=0.17605 (iter 104), ETH=0.211888 (iter 117), SOL=0.218058 (iter 121), XRP=0.221503 (iter 112)
  Recommendation: One more BTC/5m attempt (item 1 reg_alpha), then 5m is effectively closed.

- **15m:** 35 iterations, 17 KEEPs (48%), best Brier by asset:
  BTC=0.171809 (iter 123), ETH=0.208324 (iter 116), SOL=0.215345 (iter 130), XRP=0.218075 (iter 128)
  Recommendation: All 15m assets at structural floors. No further 15m experiments pending.

- **1h:** 32 iterations, 15 KEEPs (46%), best Brier by asset:
  BTC=0.174676 (iter 136), ETH=0.176103 (pre-multi-tp iter 89)/0.211438 (multi-tp iter 100),
  SOL=0.220615 (iter 125), XRP=0.226907 (iter 115)
  Recommendation: ETH/1h and SOL/1h have remaining headroom. Focus 1h efforts here (items 2-3).

- **Overall recommendation:** Balanced across 5m (1 experiment) and 1h (2-3 experiments).
  15m is fully exhausted. Explore walk-forward params for 1h tick-dominant assets next.

## Blacklist

- **reg_alpha=[0.1,5.0] forcing (all assets):** 0/4 KEEP (iters 139, 140, 143, 144).
  HPO collapses to lower bound without escaping structural floor. PERMANENT BLACKLIST.
- **XRP/15m ceiling reduction below [100,400]:** Starvation confirmed structural
  (iters 128, 132, 145). n_estimators=273 optimum is not near any tested ceiling.
  Dataset-size class limits are the binding constraint, not HPO ceiling. PERMANENT BLACKLIST.
- **BTC/1h n_estimators=[100,250]:** Stochastic basin confirmed (iters 137, 138).
  Both independent runs miss 0.174676 by <0.03%. Floor is ~0.1746-0.1750. BLACKLIST.
- **Stochastic re-runs when basin confirmed:** 0/2 KEEP. If 2 independent runs miss by
  <0.05%, the basin is structural. Do not add a 3rd run. PROTOCOL BLACKLIST.
- **BTC/5m time_pcts 4+ points:** 0/3 KEEP (iters 12, 21, starvation-confirmed).
  HPO starvation makes wide time_pct sets non-viable for 5m bar datasets.
- **SOL max_depth > 6:** 0/1 KEEP (iter 41). max_depth=6 confirmed as SOL optimum.
- **Funding features for tick-dominant assets:** 0/3 KEEP (BTC iter 2, ETH iter 27, SOL iter 43).
  Funding absent from top-10 SHAP for all tick-dominant assets. PERMANENT BLACKLIST.

## HPO Range Recommendations

- **n_estimators (BTC/1h):** confirmed optimal [180, 230]; narrow to [100, 350] for ceiling
  (iter 136 KEEP). Already implemented in best_knobs for BTC/1h runs.
- **n_estimators (ETH/15m):** resolved at [100, 800] ceiling — optimum 350-500 range.
- **n_estimators (SOL/15m):** resolved at [100, 600] ceiling — optimum 400-600 range.
- **num_leaves (BTC-class assets at 1h):** consistently optimum 20-50; narrow to [16, 64].
- **learning_rate (BTC/1h):** optimal at [0.005, 0.03]; iter 136 used this range.
- **learning_rate (tick-dominant 5m):** wide range still useful [0.005, 0.1] — diverse optima.
- **reg_alpha (default):** Restore [1e-8, 10.0] for all experiments NOT forcing L1.
  Forced [0.1, 5.0] is blacklisted. Free-range often collapses to near-zero for tick-dominant.
- **min_child_samples:** Keep [100, 1000] — no strong evidence for narrowing at any TF.
