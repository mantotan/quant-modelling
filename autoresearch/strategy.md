# Strategy Directive
Updated: 2026-03-25T01:00:00Z
After iteration: 113

## Program Status: POST-OVERRIDE Autonomous HPO Phase (Continued)

Iters 109-114 completed the prior strategy's priority queue (items 1-5 executed, item 6 pending).
Results: 2 KEEPs (ETH/15m +0.44%, XRP/5m +0.13%), 3 DISCARDs (SOL/5m, ETH/1h reg_lambda,
BTC/15m train_bars). Critical new finding: **severe HPO starvation escalation** — ETH/15m
dropped from 19/40 to 2/40 trials, SOL/5m dropped from 18/40 to 2/40. Per-trial time is
growing as HPO explores higher n_estimators. This is the priority concern for this directive.

---

## Priority Queue

1. **XRP/1h HPO re-run with num_leaves widened [16, 128] (pending from last directive)**
   - Command: `--asset XRP --timeframe 1h --mode fast --save`
   - Knob change: hpo_search_space.num_leaves = [16, 128] (restore original bounds)
   - Rationale: XRP/1h has the highest Brier in the portfolio (0.226947). The prior strategy
     identified this as item 6 but it was never executed. XRP/1h best_params from single-tp
     iter 91 showed num_leaves=23, below the current lower bound of 32. Opening [16, 128]
     lets HPO recover the shallow-tree optimum. XRP/1h is NOT starvation-prone (40/40 trials
     historically) — this is low-risk, high-upside.
   - KEEP criterion: any Brier improvement from 0.226947
   - Revert num_leaves to [16, 128] default on DISCARD (already in best_knobs.json)

2. **Anti-starvation experiment: n_estimators ceiling reduction to [100, 800]**
   - Command: `--asset ETH --timeframe 15m --mode fast --save`
   - Knob change: hpo_search_space.n_estimators = [100, 800] (reduce from [100, 1500])
   - Rationale: ETH/15m iter 110 had only 2/40 trials (1313s timeout) — worse than iter 96's
     19/40 (moderate starvation). The escalation is almost certainly caused by HPO exploring
     n_estimators near 1500, creating >600s per-trial training time. Reducing the ceiling to
     800 sacrifices the extreme-estimator region (which has never appeared in any KEEP's
     best_params — all optima use 100-500 range) while cutting trial time approximately 40-50%.
     ETH/15m best_params from iter 110 used num_leaves=110 (near the ceiling 128) — combined
     with high n_estimators, this is the source of starvation. Expected trial count: 15-25/40
     (from 2/40). This change is safe because no KEEP has ever used n_estimators > 800.
   - KEEP criterion: any Brier improvement from 0.208899
   - Revert n_estimators to [100, 1500] on DISCARD

3. **ETH/5m HPO re-run — untouched since OVERRIDE baseline**
   - Command: `--asset ETH --timeframe 5m --mode fast --save`
   - No knob changes from what is established post-item-2 (keep n_estimators [100, 800] if item
     2 is a KEEP; otherwise revert and use standard knobs)
   - Rationale: ETH/5m has not been HPO'd since the OVERRIDE baseline (iter ~95). It has the
     same tick-dominant pattern as ETH/15m and likely the same starvation risk. Current ETH/5m
     best is ~0.178 from the OVERRIDE. A fresh HPO run with better trial coverage may improve.
     This is a no-knob-change re-run to establish whether starvation has worsened here too.
   - KEEP criterion: any Brier improvement from ~0.178 (verify exact baseline in results.tsv)

4. **SOL/1h HPO re-run — no post-OVERRIDE coverage**
   - Command: `--asset SOL --timeframe 1h --mode fast --save`
   - No knob changes (keep train_bars=10000, purge_period=24)
   - Rationale: SOL/1h baseline was set during OVERRIDE (iter ~93-102). It has not been
     touched in the post-OVERRIDE phase (iters 103-114). SOL/1h shows 40/40 trial coverage
     (no starvation) at the 1h timeframe — making it a safe re-run. Current best Brier=0.221683.
     With 40 trials each time, this is one of the best candidates for genuine HPO improvement.
   - KEEP criterion: any Brier improvement from 0.221683

5. **XRP/15m HPO re-run — no post-OVERRIDE coverage**
   - Command: `--asset XRP --timeframe 15m --mode fast --save`
   - No knob changes (keep train_bars=10000, purge_period=24)
   - Rationale: XRP/15m was set during OVERRIDE and not touched since. Current best
     Brier=0.218727. XRP/15m had 24/40 trials at baseline — moderate coverage. XRP/5m
     just improved (iter 112, 12/40 trials, 0.13% gain). XRP/15m may similarly benefit.
   - KEEP criterion: any Brier improvement from 0.218727

6. **ETH/1h lr narrowing to [0.005, 0.05]**
   - Command: `--asset ETH --timeframe 1h --mode fast --save`
   - Knob change: hpo_search_space.learning_rate = [0.005, 0.05] (reduce from [0.005, 0.1])
   - Rationale: ETH/1h iter 113 found lr=0.008287. Iter 108 found lr=0.033. Iter 89 (single-tp)
     found lr=0.009. No ETH/1h KEEP has used lr > 0.065 in multi-tp phase. The top half of the
     [0.005, 0.1] range (0.05-0.1) is unexplored and likely wasteful. Narrowing to [0.005, 0.05]
     focuses HPO on the productive zone and recovers ~20-25% of trial budget lost to high-lr
     exploration. ETH/1h has 40/40 trial coverage (no starvation risk), making this safe.
   - KEEP criterion: any Brier improvement from 0.211438
   - Revert learning_rate to [0.005, 0.1] on DISCARD

---

## Observations

- **KEEP rates (iters 109-114, this strategist window):**
  - HPO re-run (no knob change): ETH/15m KEEP (2/40 trials!), SOL/5m DISCARD (2/40 trials),
    XRP/5m KEEP (12/40 trials) = 2/3 (67%) — but starvation is masking true landscape
  - HPO range widening: ETH/1h reg_lambda [1.0, 20.0] DISCARD = 0/1 (0%)
  - Walk-forward config: BTC/15m train_bars=7500 DISCARD = 0/1 (0%)
  - Additional HPO: SOL/15m DISCARD (iter 109, structural starvation) = 0/1 (0%)

- **Cumulative KEEP rates (post-OVERRIDE, iters 103-114):**
  - HPO re-run (no knob change): 4/7 (57%) — BTC/5m, BTC/1h, ETH/15m, XRP/5m kept
  - HPO range narrowing: 0/4 (0%) — lr-range, min_child, num_leaves narrowing all fail
  - HPO range widening: 1/2 (50%) — BTC/1h num_leaves [32,96]+lr widening KEEP; ETH/1h
    reg_lambda widening DISCARD
  - Walk-forward config: 0/2 (0%) — BTC/15m train_bars changes consistently fail

- **CRITICAL: HPO starvation escalation detected (iters 110-111):**
  - ETH/15m: 19/40 (iter 96) → 2/40 (iter 110) — per-trial time increased 7-10x
  - SOL/5m: 18/40 (iter 93) → 2/40 (iter 111) — same pattern, identical lr=0.005318
  - Identical best_params at the extreme lr=0.005318, max_depth=6, num_leaves=110, min_child=291
    appearing in both: this is NOT genuine HPO convergence — it is the HPO running only the
    first trial (Optuna default initialization) before timeout. The 2-trial results are
    unreliable measurements of the true landscape.
  - Root cause hypothesis: n_estimators ceiling at 1500 × high num_leaves (near 128) = very
    long trial time. Neither ETH/15m nor SOL/5m KEEP has ever used n_estimators near 1500.
  - Action required: priority item 2 tests n_estimators ceiling reduction to [100, 800].

- **ETH/1h reg_lambda clarification (iter 113):**
  - Single-tp era optimal reg_lambda=9.42 (iter 89) does NOT carry to multi-tp. In multi-tp,
    ETH/1h optimal reg_lambda=1.396537 (near lower bound 1.0). The tick-dominant pattern in
    multi-tp regime uses LOW L2 regularization. The high reg_lambda signal from iter 89 was
    likely an artifact of single-tp training dynamics.
  - Recommendation: set reg_lambda search space to [1e-8, 5.0] for tick-dominant assets
    (not yet executed — included as observation for future strategist review).

- **BTC/15m starvation confirmed structural (iter 114):**
  - train_bars=7500 gave 17/40 (vs 15/40 at 10000) — marginal improvement confirms that
    starvation is per-fold time, not total dataset volume. Further train_bars reduction would
    sacrifice too much training data for minimal trial gain. Accept 15-17/40 as structural
    floor for BTC/15m. BTC/15m Brier floor is likely near 0.1719 given three attempts at
    the same number all produce ~0.172.

- **XRP/5m new insight (iter 112):**
  - Found lr=0.0116, max_depth=4, num_leaves=31, min_child=822 — despite only 12/40 trials.
  - num_leaves=31 is at the lower end; min_child=822 is very high. This suggests XRP/5m
    benefits from conservative tree structure (low depth, few leaves) and heavy smoothing.
  - Consistency with other tick-dominant assets: partial_bar_position, partial_range,
    time_remaining_pct, elapsed_pct dominate. No funding or alpha features in top-10.

- **ETH/15m lr discovery (iter 110, 2-trial caveat):**
  - lr=0.005318 found below prior lower bound. With only 2 trials this is unreliable. The
    true ETH/15m optimum is unknown post-anti-starvation fix. After n_estimators ceiling
    reduction, a fresh ETH/15m HPO may find a completely different optimum.

---

## Risk Profile

- Max drawdown trend: stable — BTC/5m=0.39 (iter 104), BTC/15m=0.17-0.18, BTC/1h=0.23;
  ETH/SOL/XRP tick-dominant 0.06-0.09 (unchanged)
- Drawdown/PnL ratio: tick-dominant < 0.01 (excellent), BTC sniper 0.003-0.009 (good)
- Trade count range across recent KEEPs:
  - BTC/5m: ~80,966 (iter 104, stable)
  - BTC/15m: ~60,725-61,758 (iters 114-105, stable)
  - BTC/1h: ~16,213-16,603 (iters 107-106, stable)
  - ETH/15m: ~76,262 (iter 110)
  - XRP/5m: ~80,783 (iter 112)
- Win rate stability:
  - BTC-class sniper: 87-88% (5m), 65-73% (15m), 63-73% (1h) — 1h range wider due to starvation
  - Tick-dominant: 49-51% (near-random, calibrated probability model, stable)
- HPO-OOS gap (recent iterations with data):
  - ETH/15m iter 110: hpo_objective=0.312 vs oos_brier=0.209 — large gap (hpo_objective
    includes penalties, not direct brier comparison)
  - BTC/15m iter 114: hpo_objective=0.176 vs oos_brier=0.172 — tight, consistent with prior
  - NOTE: For tick-dominant assets, hpo_objective >> oos_brier due to trade penalty terms.
    This is not overfitting — it reflects the composite penalty structure. The oos_brier is
    the relevant metric.

---

## Timeframe Coverage

- 5m: 53 iterations, 19 KEEPs (incl. OVERRIDE), best multi-tp Brier: BTC=0.17605,
  ETH=~0.178 (unchanged), SOL=0.218209 (unchanged), XRP=0.221503 (new best iter 112)
- 15m: 28 iterations, 13 KEEPs (incl. OVERRIDE), best multi-tp Brier: BTC=0.171913
  (unchanged), ETH=0.208899 (new best iter 110), SOL=0.215443 (unchanged), XRP=0.218727
  (unchanged)
- 1h: 25 iterations, 11 KEEPs (incl. OVERRIDE), best multi-tp Brier: BTC=0.174864
  (iter 107), ETH=0.211438 (unchanged), SOL=0.221683 (unchanged), XRP=0.226947 (unchanged)
- Recommendation: 1h is slightly under-covered in post-OVERRIDE phase (9 iters 1h vs 10
  each for 5m/15m since iter 103). Priority queue distributes: 3/6 to 1h (items 1, 4, 6
  touch 1h assets), 2/6 to 15m (items 2, 5), 1/6 to 5m (item 3). Balanced coverage.

---

## Blacklist

- **lr lower bound > 0.015 for any BTC-class asset** (iters 103, 106 DISCARD) — BTC sniper
  zone is lr 0.008-0.015, raising lower bound excludes optimum
- **train_bars increase beyond 10000 for BTC-class** (multiple DISCARDs across iters 52, 82) —
  BTC prefers shallower training
- **train_bars reduction to 7500 for BTC/15m** (iter 114 DISCARD) — starvation is structural,
  not improved by train_bars reduction; accept 15-17/40 as floor
- **train_bars increase beyond 14000 for ETH** — ETH ceiling is 14000
- **min_child_samples narrowing for any asset** (0/3 across iters 106, 108, and prior) —
  wide [100, 1000] range is correct for all assets
- **funding features in cached_features** (iters 2, 27, 43 — 0/3 KEEP) — funding never in
  top-10 SHAP
- **interaction features** (iter 6 DISCARD — massive Brier regression) — do not re-enable
- **n_splits reduction to 6** (iters 31, 33) — consistently worse
- **SOL/15m HPO re-run (no knob changes)** (iters 97, 109 — structural 16/40 starvation) —
  pointless without fixing timeout root cause
- **ETH/1h reg_lambda widening above 10.0** (iter 113 DISCARD) — multi-tp regime prefers
  low L2; reg_lambda optimal is near 1.0-1.4 in multi-tp, not 9.42 (single-tp artifact)

---

## HPO Range Recommendations

- **n_estimators for tick-dominant 15m assets**: candidate reduction to [100, 800] —
  evidence: starvation escalation in ETH/15m (2/40 trials, iter 110) and SOL/5m (2/40,
  iter 111). No KEEP has ever used n_estimators near 1500. Priority item 2 tests this.
- **learning_rate for BTC-class**: confirmed [0.005, 0.03] — BTC/5m optimal 0.0127 (iter 44),
  BTC/1h optimal 0.008 (iter 107), BTC/15m optimal 0.012 (iter 105). Already in best_knobs.json.
- **learning_rate for ETH/1h**: candidate narrowing to [0.005, 0.05] — evidence: all ETH/1h
  multi-tp optima in 0.008-0.033 range; high-lr region (0.05-0.10) unexplored and likely
  wasteful. Priority item 6 tests this.
- **reg_lambda for tick-dominant multi-tp assets**: candidate narrowing to [1e-8, 5.0] —
  evidence: ETH/1h optimal=1.397 (iter 113), near lower bound. High L2 region (5-10) appears
  sub-optimal in multi-tp regime. NOT yet tested; recommend in next strategist review if
  more evidence accumulates.
- **num_leaves for BTC/1h**: current [32, 96] confirmed good (iter 107, num_leaves=41).
- **min_child_samples**: keep [100, 1000] for all assets — narrowing 0/3 KEEP rate.
