# Strategy Directive
Updated: 2026-03-19T08:50:00Z
After iteration: 4

## Priority Queue
1. **Further time_pcts exploration**: Try dropping 0.01 as well (keeping [0.05, 0.10, 0.20, 0.30, 0.40, 0.60, 0.80]). The 1% elapsed point (~3s into a 5m bar) still has very little tick information. Evidence: dropping 0.003 gave 3.34% Brier improvement (iter 4 KEEP-VERIFIED).
2. **Denser mid-range time_pcts**: Try adding 0.15 and 0.50 to current time_pcts [0.01, 0.05, 0.10, 0.15, 0.20, 0.30, 0.40, 0.50, 0.60, 0.80]. More sampling points in the 10-50% range where tick signal ramps up. May increase training time — monitor.
3. **Feature selection — drop low-value cached features**: Try removing `hour_sin`, `hour_cos` from cached_features. Time-of-day features may add noise if the 5m market is active 24/7 without strong hourly patterns. Look at top_features — hour_sin/cos never appear in top-10.
4. **Walk-forward: increase test_bars**: Try test_bars=2000 (from 1000). The current 1000-bar test window is ~3.5 days at 5m cadence — may be too short for stable Brier estimation. Evidence: best_params are identical across all runs → HPO is converging to same params regardless of changes, suggesting the evaluation metric itself needs more data for differentiation.
5. **Objective tuning: increase brier_penalty_weight**: Try brier_penalty_weight=20.0 (from 10.0). With sharpe-primary, a stronger Brier penalty may push HPO to care more about calibration quality. Currently the objective returns 0.0 for all trials (Brier < threshold) so the penalty never fires — the threshold may be too generous.

## Observations
- **KEEP rates**: HPO range narrowing: 0/2 (0%), Sampling density: 1/1 (100%), Baseline: 1/1 (100%)
- **Brier trajectory**: 0.205489 → 0.198617 (3.34% improvement in 4 iters)
- **Best params converge identically**: All 4 runs found n_estimators=624, lr=0.086, max_depth=5, num_leaves=83, min_child=240 — the HPO is fully converged. Changing HPO ranges is pointless unless we shift the converged optimum.
- **Top features stable**: vol_norm_distance, distance_from_open, partial_bar_position always top-3. Tick features dominate (indices 0-5 = top 6). Historical features contribute via realized_vol_10, parkinson_vol_10, rsi_14.
- **Alpha features not yet active**: No alpha features (funding, liquidation, IV, polymarket) in top-10. Expected — alpha data has not been downloaded yet (stores empty, features graceful no-op). Alpha features will only appear after running download scripts + cache regeneration.
- **Both-sides strategy highly volatile**: PnL swings from -$470K to +$358K across iterations. Single-side PnL is much more stable ($5.51 to $19.77). The both-sides strategy is sensitive to model changes — monitor but don't optimize for it.
- **HPO objective always 0.0**: The sharpe-primary objective with brier_threshold=0.25 returns 0.0 for every trial because Brier is always well below threshold. The objective is not differentiating between trials — this is a problem. Consider lowering brier_threshold to 0.20 so the penalty actually fires, or switching to brier-primary for a few iterations.

## Blacklist
- HPO range narrowing on regularization params: reg_alpha [0.01,5.0] + reg_lambda [0.0001,1.0] — iter 2 DISCARD, marginal regression
- HPO range narrowing on tree structure: max_depth [4,6] + num_leaves [31,128] — iter 3 DISCARD, significant regression (-$470K both-sides)

## HPO Range Recommendations
- **Do NOT narrow HPO ranges** — all 4 runs converge to identical best_params. The search space is fine; the TPE sampler finds the optimum consistently. Narrowing only risks excluding the optimum (as iter 2-3 showed).
- **learning_rate**: converges to 0.086 — consider trying a fixed learning_rate=0.086 to reduce search dimensionality, giving other params more exploration budget.
- **Consider**: If HPO always converges to the same params, the research leverage is NOT in HPO tuning — it's in data/feature/objective changes. Focus on categories 1-5 in the priority queue.
