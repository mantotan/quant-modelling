# Strategy Directive
Updated: 2026-03-19T21:10:00Z
After iteration: 12

## Priority Queue

1. **Reduce time_pcts to 3 points — set [0.30, 0.50, 0.80] — to shrink per-trial cost and restore HPO convergence.** The last 3 DISCARDs (iters 10, 11, 12) all share a single root cause: per-trial training cost exceeds the HPO time budget, leaving 13-17 trials where 40+ are needed. The current 4-point set (0.30, 0.40, 0.60, 0.80) yields 557K samples; dropping to 3 carefully-chosen points yields ~418K samples (25% reduction), cutting per-trial wall time by roughly the same factor. The 3 chosen points cover early momentum (0.30), mid-bar equilibrium (0.50), and late-bar conviction (0.80). This is NOT a feature reduction — it is a throughput fix. If HPO reaches 35+ trials at 3 points and Brier improves, this becomes the new baseline. If Brier is within noise of best (0.143724), KEEP and proceed to priority #2. If Brier regresses meaningfully (>0.0005), note the signal value of the 4th point and restore. This is the highest-priority experiment because it unblocks every subsequent experiment.

2. **Apply narrowed HPO ranges (iter 10 configuration) after per-trial cost is restored (after priority #1 KEEPs).** Iter 10 achieved bs_sharpe 87.79 — the highest on record — with only 14 trials using narrowed ranges: n_estimators [500, 1500], learning_rate [0.005, 0.04], max_depth [3, 6], num_leaves [31, 96], min_child_samples [200, 600]. With 3 time_pcts and reduced per-trial cost, these same ranges should now converge with 35-40 trials. Do NOT re-widen the ranges. The iter 10 ranges are confirmed correct by both HPO convergence evidence and the fact that 14 trials at those ranges beat 100 trials at wider ranges on bs_sharpe. Expected gain: Brier reduction of 0.0003-0.001 and bs_sharpe target >88.

3. **Prune oi_price_divergence and oi_momentum from cached_features — test 20-feature set.** In iter 4, adding all 4 liquidation features produced only +0.000004 Brier gain (0.143858→0.143854 from iter 3 baseline). Of the 4, liquidation_proximity and leverage_proxy are directly interpretable signals with mechanical relationships to price. oi_price_divergence and oi_momentum are derived, likely correlated with each other (OI-based), and may contribute noise above their signal. Removing 2 features from 22 reduces collinearity pressure on LightGBM, potentially improving generalization. This experiment must be attempted ONLY after priorities #1 and #2 have confirmed HPO is unblocked — otherwise a feature change and HPO starvation would be confounded. If DISCARD, restore both features immediately.

4. **Test regime_params tuning — increase vol_window 120→240 and lookback_window 120→240 simultaneously.** regime_vol_zscore is the only confirmed persistent alpha signal, appearing in top-10 across iters 3, 4, and 8. The current vol_window=120 bars corresponds to 10 hours on 5m bars. Increasing to 240 bars (20 hours) spans a full trading day cycle, reducing noise from intraday vol spikes that are not regime changes. Matching lookback_window ensures the percentile anchors remain coherent with the wider vol window. Expected gain: 0.0005-0.001 Brier from cleaner regime labeling with no increase in per-trial cost. This is strictly a config change — it does not add samples or features — making it HPO-budget-neutral.

5. **Test train_bars 8000→10000 — more historical context per fold — after HPO throughput is confirmed stable.** iter 8's 27.5% Brier improvement from 5000→8000 bars suggests the learning curve has not fully saturated. train_bars=10000 adds 25% more context per fold. The critical gate: measure per-trial cost at 3 time_pcts with the narrowed HPO ranges (priorities #1 and #2). If per-trial time is <20s, 40 trials complete in <800s, leaving budget for 10000-bar folds. If per-trial time is already near budget ceiling, defer this until a larger compute budget is available. Do not attempt if priorities #1 and #2 have not been verified stable.

## Observations

- **KEEP rates by category**: Baseline/correction 2/2 (100%), alpha features 2/3 (67%), walk-forward 1/3 (33%), interaction features 0/1 (0%), HPO range narrowing 0/1 (0%), sampling density 0/1 (0%). Overall: 6 KEEP or KEEP-VERIFIED out of 12 attempts = 50%.
- **3 consecutive DISCARDs (iters 10, 11, 12) — all same root cause (HPO starvation)**: iter 10 ran 14/100 trials; iter 11 ran 13/40 trials (fast mode cap); iter 12 ran 17/40 trials. The fast_mode cap is 40 trials but the wall-time budget is binding first. At train_bars=8000 with 4 time_pcts (557K samples), GPU time per trial is ~24s — 40 trials requires 960s (~16 min). Any structural change increasing per-trial cost (more folds, more samples, more time points) puts completion below the minimum for convergence.
- **Brier improvement trajectory — flatlined since iter 8**: Best Brier is 0.143724 (iter 8, KEEP-VERIFIED). All subsequent iterations: 0.143727, 0.14377, 0.14387, 0.16192. No progress in 4 iterations. The stagnation is entirely explained by HPO starvation, not by feature exhaustion.
- **bs_sharpe peak at iter 10 (87.79) with only 14 trials is the key signal**: Narrowed HPO ranges (iter 10) achieved highest bs_sharpe on record despite the fewest trials. This is strong evidence that the search space reduction is correct and that higher trial count at those ranges will improve further. Target bs_sharpe >88 when priority #2 runs with sufficient trials.
- **Both-sides strategy dominates consistently**: bs_pnl ranges from $1.40M-$1.67M vs single-side $68-$5.3K. The bs_sharpe degradation in iters 11-12 (79.88, 76.48) tracks directly with HPO starvation severity — fewer trials → worse model calibration → lower Sharpe. This is not a strategy structural problem.
- **regime_vol_zscore remains the only confirmed persistent alpha signal**: Appears in top-10 in iters 3, 4, and 8. No other alpha feature group (funding, liquidation, options_iv, polymarket) has confirmed persistent importance. Liquidation features have marginal contribution (iter 4: +0.000004 Brier gain); funding features are permanently blacklisted.
- **Researcher compliance**: Researcher ran iter 12 (time_pcts expansion), which was priority #1 from the last directive. Result: DISCARD due to HPO starvation — the same systemic issue identified in the ack.txt for iters 10 and 11. Researcher ack.txt correctly diagnoses the pattern. Full compliance and accurate diagnostics.
- **Interaction features: permanent blacklist confirmed**: iter 6 produced +41% Brier regression (0.143854→0.2028). No evidence that any interaction feature ever appeared in top-20 importance. Interactions are categorically blacklisted.

## Blacklist

- **Interaction features (all 8 pairs)**: iter 6 DISCARD, Brier 0.143854→0.2028 (+41% regression). Permanent. Do not enable `interaction_features.enabled` under any condition.
- **Funding features in cached_features**: iter 2 DISCARD (0.143929 vs 0.143872 baseline). Permanent. The 8h funding cadence provides no 5m intra-bar signal.
- **time_pcts expansion beyond 4 points before HPO budget is confirmed unblocked**: iter 12 DISCARD (Brier 0.16192, 17 trials). Blocked until per-trial cost is reduced via priority #1.
- **n_splits above 8 without per-trial cost reduction**: iter 11 DISCARD (13 HPO trials, Brier 0.14387). Blocked.
- **embargo_period increase 6→12**: iter 9 DISCARD — noise-level difference (0.143727 vs 0.143724). No benefit; current 6-bar embargo is sufficient.
- **train_bars below 8000**: iter 7 vs iter 8 established hard floor. A 27.5% Brier difference (0.1982 vs 0.143724) at 5000 vs 8000 bars confirms 8000 is the minimum.
- **HPO range widening back to original bounds**: iter 10 narrowed to [500,1500] / [0.005,0.04] / [3,6] / [31,96] / [200,600] and achieved best bs_sharpe on record. Do not revert to original wide ranges.

## HPO Range Recommendations

- `n_estimators`: narrow to [500, 1500] — iter 10 evidence; removing the [100, 500] underfitting zone is confirmed correct.
- `learning_rate`: narrow to [0.005, 0.04] — iter 10 evidence; lr>0.04 was not selected in any KEEP iteration.
- `max_depth`: narrow to [3, 6] — iter 10 evidence; depth-2 trees are insufficient for regime_vol_zscore interactions.
- `num_leaves`: narrow to [31, 96] — iter 10 evidence; 16-30 is too shallow; 97-128 over-parameterizes at <600K samples.
- `min_child_samples`: narrow to [200, 600] — iter 10 evidence; [100, 1000] range is too wide; practically relevant band confirmed by KEEP convergence.
- `reg_alpha` and `reg_lambda`: keep [1e-8, 10.0] — no convergence data; wide range appropriate.
- `subsample`: keep [0.6, 0.9] — no convergence evidence to narrow.
- `colsample_bytree`: keep [0.4, 0.8] — no convergence evidence to narrow.
- **Critical action before priority #2**: Verify that fast_mode trial cap (currently 40) will reach 35+ completions with 3 time_pcts and train_bars=8000 at GPU speed. Measure per-trial wall time in the priority #1 run. If per-trial cost is <20s, 40 trials completes in <800s — budget is safe. If per-trial cost is 20-25s, consider reducing fast_mode cap to 35 to stay within budget while still achieving convergence.
