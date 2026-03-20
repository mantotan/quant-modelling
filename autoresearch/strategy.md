# Strategy Directive
Updated: 2026-03-24T00:00:00Z
After iteration: 108

## Program Status: POST-OVERRIDE Autonomous HPO Phase (Continued)

All 12 pulse_v2 baselines established. The prior strategy (after iter 103) assigned a 6-item
priority queue. All 6 items are now executed (iters 104-109). Results: 2 KEEPs (BTC/5m
+0.70%, BTC/1h +0.46%), 4 DISCARDs. This directive assigns the next priority queue.

---

## Priority Queue

1. **ETH/15m HPO re-run — most underpowered non-BTC target**
   - Command: `--asset ETH --timeframe 15m --mode fast --save`
   - No knob changes (keep train_bars=14000 — ETH unique preference confirmed)
   - Rationale: Only 19/40 HPO trials ran at iter 96 baseline (moderate starvation). ETH/15m
     multi-tp Brier=0.209819 vs single-tp 0.174283 (+20.4% gap). Among all tick-dominant assets,
     ETH/15m had the second-fewest trials. Full-coverage HPO may find lower lr/num_leaves combo.
   - KEEP criterion: any Brier improvement from 0.209819
   - Expected outcome: push toward 0.205-0.208 range

2. **SOL/5m HPO re-run — second-lowest trial count in 5m group**
   - Command: `--asset SOL --timeframe 5m --mode fast --save`
   - No knob changes (keep train_bars=10000, purge_period=12)
   - Rationale: Only 18/40 HPO trials at iter 93 baseline. SOL/5m Brier=0.218209, single-tp
     floor was 0.189372. HPO starvation risk is high. tick-flat assets tend to have wider
     HP optima but higher variance on short trial counts.
   - KEEP criterion: any Brier improvement from 0.218209

3. **XRP/5m HPO re-run — 24/40 trials, consistent tick-flat pattern**
   - Command: `--asset XRP --timeframe 5m --mode fast --save`
   - No knob changes (keep train_bars=10000, purge_period=24)
   - Rationale: 24/40 trials at iter 94. XRP/5m Brier=0.221782 is highest in 5m tier.
     Tick-flat pattern means HPO landscape is smooth — more trials should find better
     lr/num_leaves combination.
   - KEEP criterion: any Brier improvement from 0.221782

4. **ETH/1h regularization exploration — try reg_lambda narrowing [1.0, 20.0]**
   - Command: `--asset ETH --timeframe 1h --mode fast --save`
   - Knob change: hpo_search_space.reg_lambda = [1.0, 20.0] (narrow from [1e-8, 10.0])
   - Rationale: ETH/1h iter 89 best_params showed reg_lambda=9.42 (unique highest L2
     regularization across all assets, near the prior 10.0 ceiling). The iter 108 min_child
     narrowing failed (+2.05% regression), but the reg_lambda ceiling hit at iter 89 suggests
     there may be a better solution slightly above 9.42. Widening the ceiling to 20.0 lets HPO
     explore this direction. Keep reg_alpha default [1e-8, 10.0].
   - KEEP criterion: any Brier improvement from 0.211438
   - Revert reg_lambda on DISCARD

5. **BTC/15m timeout fix — reduce train_bars to 7500 to escape starvation**
   - Command: `--asset BTC --timeframe 15m --mode fast --save`
   - Knob change: walk_forward.train_bars = 7500 (reduce from 10000)
   - Rationale: BTC/15m shows STRUCTURAL starvation — 15/40 trials (iter 95) and 15/40 trials
     (iter 105), both hitting the 420s timeout. The 7500 bar reduction sacrifices ~4.6% training
     data but buys approximately 30-35% more HPO trials (should get 20-25/40). Given BTC's sniper
     pattern converges reliably, more trials matter more than extra training bars here. Current
     best is 0.171913.
   - KEEP criterion: any Brier improvement from 0.171913
   - Revert train_bars to 10000 on DISCARD (BTC/15m optimum is 10K, not 14K like ETH)

6. **XRP/1h HPO re-run with num_leaves widened [16, 128]**
   - Command: `--asset XRP --timeframe 1h --mode fast --save`
   - Knob change: hpo_search_space.num_leaves = [16, 128] (restore to original bounds)
   - Rationale: XRP/1h has the highest Brier in the portfolio (0.226947). Iter 102 used
     best_knobs.json which now has num_leaves [32, 96] (from iter 107 update). XRP/1h best_params
     from iter 91 (single-tp) showed max_depth=4, num_leaves=23 — this is BELOW the current lower
     bound of 32. Opening the full range may recover the shallow-tree optimum for XRP 1h.
   - KEEP criterion: any Brier improvement from 0.226947
   - Revert num_leaves on DISCARD

---

## Observations

- **KEEP rates (post-multi-tp phase, iters 103-109):**
  - HPO range narrowing: 1/4 (25%) — min_child and lr-range narrowing mostly fail
  - HPO re-run (no knob change): 2/3 (67%) — BTC/5m KEEP (0.70%), BTC/15m DISCARD (timeout), SOL/15m DISCARD (structural starvation)
  - Overall post-OVERRIDE: 2/7 KEEPs (29%)

- **BTC sniper convergence confirmed:**
  - lr optimal zone: 0.008-0.015 across BTC/5m, BTC/15m, BTC/1h
  - max_depth: 4-5 (never 6 for BTC)
  - num_leaves: 31-98 range (wide, HPO-dependent)
  - min_child: 363-794 range (wide, consistent with high trade count 14K-80K)

- **Tick-dominant convergence confirmed:**
  - lr: 0.017-0.065 (wider range, less sensitive than BTC sniper)
  - max_depth: 4-6 (no ceiling preference)
  - min_child: 416-794 for 15m/1h; wider at 5m

- **HPO starvation hierarchy** (worst to best trial coverage):
  - SOL/15m: 16/40 structural (dataset-size bottleneck at 10K x 15m)
  - BTC/15m: 15/40 structural (train_bars=10K x folds bottleneck)
  - BTC/5m (post-OVERRIDE): 11/40 then 22/40 (high variance, depends on HPO trial timing)
  - ETH/15m: 19/40 moderate
  - BTC/1h: 13/40 to 27/40 (high variance)
  - ETH/1h: 40/40 (no starvation)
  - SOL/1h: 40/40 (no starvation)
  - XRP/1h: 40/40 (no starvation)

- **Feature importance stability:**
  - BTC-class top features: vol_norm_distance, distance_from_open, elapsed_pct, time_remaining_pct, partial_bar_position (consistent across 5m/15m/1h)
  - Tick-dominant top features: partial_bar_position, partial_range, bar_position, rsi_14, rsi_7 (consistent)
  - regime_vol_zscore appears in BTC-class models but NOT tick-dominant — confirmed reliable signal detector

- **Brier floor trajectory (multi-tp):**
  - All single-to-multi-tp gaps now measured: BTC +74-83% (sniper), ETH/SOL/XRP +14-21% (tick-flat)
  - Post-OVERRIDE improvements: BTC/5m -0.70%, BTC/1h -0.46% — small but consistent
  - Tick-dominant assets show minimal improvement potential from HPO alone

---

## Risk Profile

- Max drawdown trend: stable — latest BTC/5m 0.39 (iter 104), BTC/15m 0.17-0.18, BTC/1h 0.22-0.23; ETH/SOL/XRP tick-flat at 0.06-0.09
- Drawdown/PnL ratio: tick-dominant < 0.01 (excellent), BTC sniper 0.003-0.009 (good)
- Trade count range across KEEPs:
  - BTC/5m: ~80,000-81,000 (stable sniper high frequency)
  - BTC/15m: ~14,700-15,000 (stable)
  - BTC/1h: ~3,650-3,680 (stable, consistent)
  - ETH/SOL/XRP 1h: ~3,700-4,000 (stable)
  - 15m tick-dominant: ~14,000-15,500 (stable)
- Win rate stability:
  - BTC-class sniper: 87-88% (highly stable, 5m), 87% (15m), 82-86% (1h)
  - Tick-dominant: 49-52% (near-random, calibrated probability model)
- HPO-OOS gap: stable — hpo_objective 0.168-0.180 vs oos_brier 0.174-0.178 for BTC/5m (gap ~0.002-0.004, consistent)

---

## Timeframe Coverage

- 5m: 51 iterations, 17 KEEPs (incl. 4 multi-tp KEEP), best multi-tp Brier: BTC=0.17605, ETH≈0.178, SOL=0.218209, XRP=0.221782
- 15m: 26 iterations, 12 KEEPs (incl. 4 multi-tp KEEP), best multi-tp Brier: BTC=0.171913, ETH=0.209819, SOL=0.215443, XRP=0.218727
- 1h: 23 iterations, 10 KEEPs (incl. 4 multi-tp KEEP), best multi-tp Brier: BTC=0.174864, ETH=0.211438, SOL=0.221683, XRP=0.226947
- Recommendation: balanced coverage — all timeframes have recent activity; priority queue above distributes 2/6 to 1h, 2/6 to 5m, 2/6 to 15m

---

## Blacklist

- **lr lower bound > 0.015 for any BTC-class asset** (iters 103, 106 DISCARD) — BTC sniper zone is lr 0.008-0.015, raising the lower bound excludes the optimum
- **train_bars increase beyond 10000 for any BTC-class asset** (iters 52, 82, 66+67 pattern) — BTC prefers shallower training at all timeframes
- **train_bars increase beyond 14000 for ETH** (iter 52 XRP analog, iter 72 ETH 15m DISCARD) — ETH ceiling is 14000
- **min_child_samples narrowing for tick-dominant assets** (iters 106, 108 DISCARD) — tick-flat assets have wide min_child optima; narrowing to [400,800] or [200,600] excludes viable solutions
- **funding features in cached_features** (iters 2, 27, 43 — 0/3 KEEP across BTC/ETH/SOL) — funding never appears in top-10 SHAP for any asset
- **interaction features** (iter 6 DISCARD — massive Brier regression) — interactions disabled, do not re-enable
- **n_splits reduction to 6** (iters 31, 33) — consistently worse or equal to n_splits=8
- **SOL/15m HPO re-run (no knob changes)** (iters 97, 109 — structural 16/40 starvation) — pointless without fixing the timeout root cause first

---

## HPO Range Recommendations

- **learning_rate for BTC-class**: converge to [0.005, 0.03] — evidence: BTC/5m optimal 0.0127 (iter 44), BTC/1h optimal 0.009 (iter 99), BTC/15m optimal 0.0053 (iter 77); iter 107 confirmed lr=0.008 within [0.005, 0.03]. This range is already set in best_knobs.json.
- **num_leaves for BTC/1h**: current [32, 96] — confirmed good by iter 107 (num_leaves=41). Do not widen further; BTC/1h consistently uses shallow trees (31-51 range).
- **reg_lambda for ETH/1h**: candidate widening to [1.0, 20.0] — evidence: iter 89 optimal=9.42 (near prior ceiling 10.0). Priority item #4 tests this.
- **min_child_samples**: keep at [100, 1000] for all assets — narrowing consistently fails (0/3 KEEP rate for narrowing attempts in iters 103-108)
- **max_depth**: keep at [2, 6] for all assets — BTC converges to 4-5, tick-dominant to 4-6; ceiling at 6 is appropriate
