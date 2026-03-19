# Strategy Directive
Updated: 2026-03-20T04:30:00Z
After iteration: 29

## Priority Queue

1. **ETH: n_splits 8→6 (walk_forward.n_splits).** This is the highest expected-value remaining experiment for ETH given 2 iterations left in the SWITCH ETH window. Current evidence: ETH is averaging only 24 HPO trials per run (last_run.log confirms 24/40) vs BTC's stable 30-34 trials. With 8 splits the per-fold training budget is tighter — reducing to 6 splits eliminates 2 training folds and directly returns ~25% of the wall-clock budget to HPO. At train_bars=14000 with test_bars=2000, 8 splits already requires 8×(14000+2000)=128000 bars, which is near the dataset size limit for ETH. 6 splits requires 96000 bars, allowing more Optuna trials within the same wall-clock budget. Mechanically: if trial count increases from 24 to ~32, the optimizer has a meaningfully better chance of reaching a lower Brier minimum. The Brier gain may be modest (target 0.001-0.003) but the trial count improvement is the primary goal — ETH is currently operating with a systematically under-budgeted HPO. Keep all other knobs at current best: train_bars=14000, purge_period=12, embargo_period=6, time_pcts=[0.30,0.50,0.80]. Monitor: if trials remain <=24 after this change, the bottleneck is not n_splits (possibly GPU transfer overhead per fold); if trials jump to >=30, confirm this as the binding constraint. Do not reinterpret this as a signal about WF rigor — 6 splits is still robust for a 14000-bar train window.

2. **ETH: objective drawdown_penalty_weight 5.0→10.0.** ETH's max drawdown is remarkably low at 0.0175-0.0188 across all iterations (vs BTC's 0.1523-0.4652 range), yet the model is being penalized for drawdown equally. Doubling the drawdown penalty weight will push HPO to select models that trade Brier improvement against drawdown more aggressively — but since ETH drawdown is already near-zero, this penalty relaxes effectively, allowing the optimizer more freedom to optimize Brier directly without defensive over-regularization. The logic: brier_penalty_weight=10.0 combined with drawdown_penalty_weight=10.0 creates a symmetric objective; with ETH drawdown virtually irrelevant, the doubled weight barely affects the objective landscape while ensuring any Brier-improving trial is not accidentally penalized on a non-binding constraint. Expected gain: 0.001-0.003 Brier. Risk: low — if this causes over-trading or drawdown spike, it will appear immediately in metrics. Change only `objective.drawdown_penalty_weight` from 5.0 to 10.0; leave all other objective weights unchanged.

3. **BTC return prep: reset train_bars 14000→10000 and purge_period to best BTC config.** This is not an experiment — it is a mandatory config reset before the auditor SWITCH ETH window closes. The current knobs.json has train_bars=14000 (ETH-optimal). When returning to BTC after iter 31 (ETH iter 10/10), the first BTC run must use BTC's confirmed-optimal config: train_bars=10000 (iter 18 KEEP, iter 22 KEEP), purge_period=12 (iter 22 KEEP), n_splits=8. Running BTC with train_bars=14000 would waste budget and likely cause HPO starvation. Note: this is a planning directive, not an immediate experiment. Execute this reset when the auditor SWITCH ETH window closes. After reset, the BTC queue (listed in item 4 below) can begin.

4. **BTC: test n_splits 8→6 on return.** Evidence from ETH n_splits experiment (item 1 above) will directly inform whether this is viable for BTC. BTC averaged 30-34 HPO trials at n_splits=8 — already better than ETH. If ETH n_splits=6 yields a clear trial-count improvement (item 1 succeeds with >=32 trials), then applying the same change to BTC is a natural follow-on. BTC at n_splits=6 would have 2 fewer train/test fold cycles but more HPO trials per cycle. Given BTC Brier is plateaued at 0.101759 with the current config, the only lever left is either (a) more HPO budget, (b) new features, or (c) objective tuning. This addresses lever (a). Target: Brier < 0.1015. Do not run until ETH n_splits result is known.

5. **BTC: test min_target_corr tightening 0.005→0.010.** After returning to BTC, the feature selection correlation gate can be used to prune low-signal features automatically without manual removal. Current 22-feature set (from BTC best) has not been tested against a stricter correlation gate. At 0.010 threshold, features contributing less than 1% target correlation are dropped — this could eliminate noisy features that are consuming colsample budget without contributing signal, allowing LightGBM to focus colsample draws on high-value features. Risk: if this drops below the 5-feature fallback, the override triggers and this is harmless. Expected outcome: 0-3 features dropped, modest Brier improvement from cleaner feature set. Note: `protected_prefixes` in feature_selection will shield all alpha features (funding_, regime_, liquidation_, etc.) from the threshold. This experiment is low-risk and directly addresses the plateau via feature quality improvement rather than volume.

## Observations

- **KEEP rates by category (all 29 iterations):**
  - Baseline / pipeline correction: 2/2 (100%)
  - train_bars extension: 3/3 (100%) — iters 8 (BTC 5000→8000), 18 (BTC 8000→10000), 25 (ETH 10000→14000)
  - KEEP-VERIFIED: 2/2 (100%)
  - ETH asset baseline: 1/1 (100%)
  - purge_period tuning: 2/3 (67%) — iter 9 DISCARD (BTC 6→12), iter 22 KEEP (BTC 12→24), iter 29 KEEP (ETH 24→12)
  - Alpha features (funding/regime/liquidation, BTC): 2/3 (67%) — iter 2 DISCARD (funding), iters 3 KEEP (regime), 4 KEEP (liquidation)
  - Alpha features (ETH): 0/2 (0%) — iters 24 DISCARD (regime removal), 27 DISCARD (funding add)
  - time_pcts adjustment: 1/5 (20%) — iter 14 KEEP [0.30,0.50,0.80], iters 12, 21, 28 DISCARD (expansion)
  - HPO range narrowing: 0/5 (0%) — iters 10, 13, 15, 19, 20; permanent blacklist
  - Regime config window changes: 0/3 (0%) — iters 17 (BTC 120→240), 26 (ETH 120→60), both DISCARD
  - Feature pruning (manual): 0/2 (0%) — iters 16 (BTC OI), 24 (ETH regime)
  - Interaction features: 0/1 (0%) — iter 6; permanent blacklist
  - n_splits above 8: 0/1 (0%) — iter 11 DISCARD; blacklisted upward, untested downward
  - Overall: 14 KEEP/KEEP-VERIFIED out of 29 completed = 48.3%

- **ETH Brier convergence is shallow.** Total ETH gain over 6 KEEP-bearing iterations: 0.178243→0.177773 = 0.000470. This is 94% smaller than BTC's equivalent gain phase (0.1982→0.101759 = 0.0964). ETH is not following the BTC improvement trajectory. This implies either (a) ETH is already near its achievable Brier floor given the feature set, (b) the HPO trial starvation (24 trials vs 30-34 for BTC) is preventing discovery of a better optimum, or (c) ETH's tick-feature-dominated importance profile means the WF config rather than features is the binding constraint.

- **ETH HPO trial count (24) is consistently lower than BTC (30-34).** This 25-30% trial shortfall is the primary untested hypothesis for ETH's lack of improvement. Addressing it via n_splits reduction (item 1) is the highest-priority remaining lever.

- **ETH both-sides strategy dominates single-side.** bs_pnl ~$14M, bs_sharpe 267.08 (iter 29) vs backtest_pnl $176.50, backtest_sharpe 264.57 (single-side). The 79,500x PnL difference confirms ETH's both-sides market-making captures structural spread value that single-side misses entirely. This pattern has been consistent across all ETH iterations (iters 23-29) regardless of Brier level — ETH both-sides is robust.

- **BTC both-sides also dominates single-side**, but to a lesser degree: bs_pnl ~$583K, bs_sharpe 93.84 (BTC best, iter 22) vs backtest_pnl $45.55, backtest_sharpe 109.25. The ETH/BTC ratio of both-sides performance (~24x in PnL) tracks with ETH's higher intra-bar volatility and tick-feature dominance, consistent with ETH microstructure providing more frequent maker-fill opportunities.

- **BTC is in confirmed plateau.** 7 iterations since last meaningful Brier improvement: iter 14 (0.143724→0.101837, 29.1%) and iter 22 (0.101829→0.101759, 0.007%). Current BTC best 0.101759 has been stable for >4 iterations. The only untested BTC levers are: n_splits reduction, min_target_corr tightening, and objective reweighting. Interaction features and HPO narrowing are both permanently blacklisted.

- **Researcher compliance: full.** Iter 29 ran purge_period 24→12 (autonomous mode after all strategy priorities exhausted), which is the appropriate fallback. The 3-DISCARD sequence (iters 26-28) was handled correctly — researcher did not rerun blacklisted experiments and moved to adjacent untested configuration.

- **ETH regime_vol_zscore absent from top-10 SHAP in all ETH iterations.** Despite iter 24 confirming regime features contribute marginal signal, none of the ETH KEEP iterations show regime_vol_zscore entering top-10. Tick features (bar_position, return_5, vol_ratio, roc_5) dominate ETH top-10 across all iterations. This is a stable ETH structural pattern, not a function of train_bars or purge_period.

- **Interaction features: definitively blacklisted.** Iter 6 produced Brier 0.2028 (+41% regression). No interaction feature has appeared in any top-10 SHAP across 29 iterations. With interaction_features.enabled=false confirmed, no further testing is warranted.

## Blacklist

- **Interaction features (all 8 pairs):** iter 6 DISCARD, Brier regression +41%. Permanent for all assets.
- **Funding features in BTC cached_features:** iter 2 DISCARD (0.143929 vs 0.143872 baseline). BTC-specific permanent.
- **Funding features in ETH cached_features:** iter 27 DISCARD (0.178154 vs ETH best 0.177789). ETH-specific permanent.
- **HPO range narrowing (all configurations):** iters 10, 13, 15, 19, 20 — 0/5 KEEP rate. Wall-clock timeout binds at ~24-34 trials regardless of search space width. Permanent for all assets.
- **time_pct 0.10 (early-bar sampling):** iter 21 DISCARD, Brier regression +63%. Permanent for all assets.
- **time_pcts expansion beyond 3 points:** iters 12, 21 (BTC) and 28 (ETH) all DISCARD or no improvement. 3-point set [0.30,0.50,0.80] confirmed optimal for BTC and ETH.
- **time_pct 0.95 for ETH:** iter 28 DISCARD (0.177789 identical — no strict improvement). ETH-specific permanent.
- **embargo_period increase 6→12 (BTC):** iter 9 DISCARD, noise-level difference. No benefit.
- **n_splits above 8:** iter 11 DISCARD (13 trials, HPO starvation). Blacklisted upward for all assets.
- **train_bars above 10000 on BTC:** iter 18 shows learning curve saturation (0.000008 Brier gain at 10000). Ceiling confirmed.
- **train_bars below 8000 on BTC:** iter 8 baseline (27.5% improvement from 5000 confirmed floor). Do not revert.
- **train_bars above 14000 on ETH:** iter 25 produced only 0.000454 gain at 14000; iter 28 priority #4 gate (< 0.005 gain) triggered correctly; ETH ceiling may be 14000, confirmed after n_splits experiment.
- **Static manual feature pruning:** iters 16 (BTC OI features) and 24 (ETH regime features) both DISCARD. LightGBM internal selection handles pruning more efficiently. Do not remove features from cached_features without SHAP zero-contribution across 3+ KEEP iterations.
- **regime_params vol_window change on BTC:** iter 17 DISCARD (identical Brier at 240 bars).
- **regime_params vol_window change on ETH:** iter 26 DISCARD (0.177794 vs ETH best 0.177789).
- **Regime feature removal for ETH:** iter 24 DISCARD (0.178946 vs 0.178243). Regime features stay in ETH even absent from top-10 SHAP.

## HPO Range Recommendations

- `n_estimators`: maintain [100, 1500] — 0/5 KEEP rate on narrowing; wall-clock binds before range matters.
- `learning_rate`: maintain [0.005, 0.1] — no convergence data under non-starvation conditions.
- `max_depth`: maintain [2, 6] — no convergence data.
- `num_leaves`: maintain [16, 128] — no convergence data.
- `min_child_samples`: maintain [100, 1000] — no convergence data.
- `reg_alpha`, `reg_lambda`: maintain [1e-8, 10.0] — no convergence data.
- `subsample`: maintain [0.6, 0.9] — no convergence data.
- `colsample_bytree`: maintain [0.4, 0.8] — no convergence data.
- **Operational note:** 24 trials (ETH) and 30-34 trials (BTC) are the natural per-run budgets. Wide bounds are appropriate — TPE exploration across the full manifold is more valuable than exploitation in a narrow range at this trial count. No further range experiments are warranted under current conditions. If n_splits reduction (priority #1) succeeds in pushing ETH to >=32 trials, recheck whether a single HPO range experiment would be worth attempting in the final ETH iteration.

## BTC Return Plan (after ETH iter 10/10)

When the auditor SWITCH ETH window closes (2 iterations remaining: iters 30 and 31), execute the following mandatory reset before the first BTC experiment:

1. Set walk_forward.train_bars back to 10000 (BTC-optimal, confirmed iters 18 and 22).
2. Set walk_forward.purge_period to 12 (BTC-optimal, confirmed iter 22).
3. Set walk_forward.n_splits to 8 initially (may reduce to 6 per priority #4 above).
4. Keep time_pcts=[0.30,0.50,0.80], embargo_period=6, and all feature sets at current state.

The BTC research queue on return: (a) n_splits 8→6 informed by ETH result, (b) min_target_corr 0.005→0.010 feature selection tightening, (c) objective reweighting if Brier remains plateaued. Do not re-attempt any blacklisted experiments.
