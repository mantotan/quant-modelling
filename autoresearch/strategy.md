# Strategy Directive
Updated: 2026-03-20T05:00:00Z
After iteration: 30

## Priority Queue

1. **ETH iter 9/10: n_splits 8→6 (walk_forward.n_splits).** This was priority #1 from the previous directive and was skipped — the researcher ran embargo_period 6→3 instead (iter 30, DISCARD). Execute it now. Evidence: ETH is averaging 24-29 HPO trials per run vs BTC's 30-34. Reducing from 8 to 6 splits removes 2 fold cycles, returning ~25% of wall-clock budget to HPO. With train_bars=14000, 8 splits requires 8×(14000+2000)=128000 bars; 6 splits requires only 96000 bars, freeing budget for ~8 additional Optuna trials. This is the last high-expected-value lever for ETH. All other ETH levers have been exhausted (funding blacklisted iter 27, regime window DISCARD iter 26, time_pcts expansion DISCARD iter 28, embargo reduction DISCARD iter 30). Target: Brier < 0.1775 or trial count increase to >=32. Mechanically: set `walk_forward.n_splits` to 6; keep all other knobs at current best (train_bars=14000, purge_period=12, embargo_period=6, time_pcts=[0.30,0.50,0.80]).

2. **ETH iter 10/10: objective drawdown_penalty_weight 5.0→10.0 (objective.drawdown_penalty_weight).** Final ETH experiment. ETH max drawdown is remarkably low at 0.0162-0.0188 across all 8 iterations — this constraint is near-non-binding. Doubling the drawdown penalty weight effectively relaxes the optimization objective on a non-binding constraint, allowing TPE to explore lower-Brier regions without false penalization. Evidence: ETH drawdown never exceeded 0.0188 (iter 26) while BTC drawdown reached 0.4652 (iter 12). With drawdown_penalty_weight=10.0 and an actual drawdown of ~0.018, the penalty term contributes 10.0×(0.018/0.30)=0.6 vs. the Brier term contributing ~1.77. The doubling makes the drawdown term 1.2, still dominated by Brier. Net effect: essentially neutral on the landscape while allowing confirmation that the objective formulation is not suppressing valid Brier improvements. Set only `objective.drawdown_penalty_weight` to 10.0; leave all other objective weights unchanged.

3. **BTC return: mandatory config reset before first BTC experiment after ETH iter 10/10.** This is a planning directive, not an experiment. After iter 32 (ETH iter 10/10) closes the SWITCH ETH window, reset knobs.json to BTC-optimal before running any BTC experiment: set `walk_forward.train_bars` to 10000 (BTC ceiling confirmed iters 18+22), set `walk_forward.purge_period` to 12 (BTC-optimal confirmed iter 22), set `walk_forward.n_splits` to 8 initially, keep `walk_forward.embargo_period` at 6 (BTC-optimal default), keep `time_pcts=[0.30,0.50,0.80]`, keep all feature sets at current state (22 features including all 4 liquidation alpha features). Do NOT use ETH's train_bars=14000 for BTC — it will cause HPO starvation below 30 trials based on iter 11 evidence.

4. **BTC: n_splits 8→6 informed by ETH priority #1 result.** After resetting to BTC config (priority #3), test n_splits reduction for BTC. This applies the ETH lesson to BTC. BTC at n_splits=8 achieves 30-34 trials — already adequate. Expected gain is lower than ETH but worth one attempt given BTC's confirmed Brier plateau (0.101759, unchanged for 8 iterations). Target: Brier < 0.1015. Conditional on ETH priority #1 showing a trial-count improvement; if ETH n_splits=6 shows no trial improvement, lower this priority. At BTC, 6 splits × (10000+2000) = 72000 bars, leaving more dataset for HPO. Keep all other BTC knobs at optimal.

5. **BTC: min_target_corr feature selection tightening 0.005→0.010.** After completing BTC n_splits experiment (priority #4), test stricter feature correlation gate. At 0.010 threshold, features with <1% target correlation are automatically pruned while `protected_prefixes` shields all alpha features (regime_, liquidation_, oi_, etc.). With BTC in plateau, this is a low-risk way to reduce feature noise without manual selection (which has a 0/2 KEEP rate — iters 16, 24 both DISCARD). Expected: 1-3 weak features dropped, modest Brier improvement via cleaner colsample draws. Set only `feature_selection.min_target_corr` to 0.010; keep `feature_selection.max_pairwise_corr` at 0.90.

6. **BTC: objective reweighting — brier_threshold 0.20→0.15 (tighten acceptance gate).** After feature tightening, if BTC Brier remains plateaued above 0.1015, tighten the Brier penalty threshold from 0.20 to 0.15. At current BTC Brier of 0.1018, the model is 29% below the 0.20 gate and receives no Brier penalty. Tightening to 0.15 means the model is 32% above the new threshold, activating the brier_penalty_weight=10.0 term and pushing HPO to select models with lower Brier above all else. This changes the objective landscape materially and may reveal a local minimum below 0.101 that was invisible under the 0.20 gate. Set only `objective.brier_threshold` to 0.15.

## Observations

- **KEEP rates by category (all 30 iterations):**
  - Baseline / pipeline correction: 2/2 (100%)
  - train_bars extension: 3/3 (100%) — iters 8 (BTC 5000→8000), 18 (BTC 8000→10000), 25 (ETH 10000→14000)
  - KEEP-VERIFIED: 2/2 (100%)
  - ETH asset baseline: 1/1 (100%)
  - purge_period tuning: 2/4 (50%) — iter 9 DISCARD (BTC 6→12), iter 22 KEEP (BTC 12→24), iter 29 KEEP (ETH 24→12), iter 30 DISCARD via embargo proxy
  - embargo_period tuning: 0/2 (0%) — iter 9 BTC (6→12 DISCARD), iter 30 ETH (6→3 DISCARD); permanent blacklist for both directions
  - Alpha features (funding/regime/liquidation, BTC): 2/3 (67%) — iter 2 DISCARD (funding), iter 3 KEEP (regime), iter 4 KEEP (liquidation)
  - Alpha features (ETH): 0/2 (0%) — iter 24 DISCARD (regime removal), iter 27 DISCARD (funding add)
  - time_pcts adjustment: 1/5 (20%) — iter 14 KEEP [0.30,0.50,0.80]; iters 12, 21, 28 DISCARD (expansion); permanent 3-point set confirmed
  - HPO range narrowing: 0/5 (0%) — iters 10, 13, 15, 19, 20; permanent blacklist
  - Regime config window changes: 0/2 (0%) — iters 17 (BTC), 26 (ETH); permanent blacklist
  - Feature pruning (manual): 0/2 (0%) — iters 16 (BTC OI), 24 (ETH regime); permanent blacklist
  - Interaction features: 0/1 (0%) — iter 6; permanent blacklist
  - n_splits above 8: 0/1 (0%) — iter 11; blacklisted upward; downward untested
  - Overall: 14 KEEP/KEEP-VERIFIED out of 30 completed = 46.7%

- **ETH final status (8/10 iterations completed):** ETH best Brier 0.177773 (iter 29). Total ETH improvement across 8 iterations: 0.000470 (0.26%). This is structurally shallow compared to BTC (96.4% improvement). ETH improvement is likely bounded by tick-feature saturation — bar_position, return_5, vol_ratio, roc_5 dominate top-10 SHAP in all 8 ETH iterations; regime_vol_zscore has never entered ETH top-10. Two experiments remain (priorities #1 and #2 above). If both DISCARD, ETH Brier floor is confirmed at 0.177773.

- **Researcher compliance for iter 30: partial.** The previous directive's priority #1 was n_splits 8→6. Instead, researcher ran embargo_period 6→3 (autonomous mode, all strategy priorities "exhausted"). This represents a misread of the priority queue — n_splits 8→6 was listed as the highest-EV untested lever. The researcher may have been operating from an outdated priority list. The experiment itself (embargo_period reduction) was a valid low-risk choice. Its DISCARD result (0.178112 vs ETH best 0.177773) adds useful information: shorter embargo does not help ETH, consistent with BTC iter 9 pattern. n_splits 8→6 is now the mandatory first experiment for ETH iter 9/10.

- **ETH both-sides strategy dominates single-side across all 8 iterations.** ETH bs_pnl ~$14M, bs_sharpe 267-274 vs backtest_pnl ~$176, backtest_sharpe ~265. The $14M vs $176 ratio (~79,500x) is structurally consistent — ETH microstructure provides dense maker-fill opportunities that single-side misses. This is a robust finding independent of Brier improvement trajectory. ETH is a both-sides market-making asset.

- **BTC both-sides also dominates single-side.** BTC bs_pnl ~$584K, bs_sharpe 93.84 (iter 22 best) vs backtest_pnl $45.55, backtest_sharpe 109.25. The backtest_sharpe (single-side) actually exceeds bs_sharpe for BTC — 109 vs 94 — indicating BTC single-side has better risk-adjusted returns per trade, while both-sides generates more absolute PnL via volume. BTC is a mixed-strategy asset.

- **ETH bs_sharpe record progression:** 253.47 (iter 23) → 267.08 (iter 25) → 274.44 (iter 26, DISCARD) → 267.08 (iters 27-28) → 267.08 (iter 29) → 269.92 (iter 30, DISCARD). ETH bs_sharpe has been improving even on DISCARD iterations — the both-sides strategy is finding new optima even when single-side Brier does not improve. The iter 26 DISCARD (regime window 120→60) set the ETH bs_sharpe record at 274.44; this is informational but not actionable since bs_sharpe is not the optimization target.

- **BTC is confirmed in Brier plateau.** BTC best Brier 0.101759 (iter 22) has been unchanged for 8 iterations (iters 23-30 are all ETH). Available BTC levers on return: n_splits reduction (priority #4), feature selection tightening (priority #5), and objective brier_threshold adjustment (priority #6). All three are untested and low-risk.

- **embargo_period tuning: 0/2 KEEP, both directions tested.** BTC iter 9 tested 6→12 (DISCARD). ETH iter 30 tested 6→3 (DISCARD). Both directions fail. embargo_period=6 is optimal or near-optimal for both assets. Permanently blacklisted.

- **HPO trial starvation root cause confirmed.** Wall-clock timeout (not trial cap) is the binding constraint. Iters 10, 13 ran identical 14 trials with different trial caps (50 vs 40). The only confirmed fix is reducing computational load per trial: iter 14 (time_pcts 4→3 points) solved this for BTC (14→34 trials, 29.1% Brier improvement). For ETH, n_splits reduction is the analog intervention.

## Blacklist

- **Interaction features (all 8 pairs):** iter 6 DISCARD, Brier regression +41%. Permanent for all assets.
- **Funding features in BTC cached_features:** iter 2 DISCARD (0.143929 vs 0.143872). BTC-specific permanent.
- **Funding features in ETH cached_features:** iter 27 DISCARD (0.178154 vs ETH best 0.177789). ETH-specific permanent.
- **HPO range narrowing (all configurations):** iters 10, 13, 15, 19, 20 — 0/5 KEEP rate. Permanent for all assets.
- **time_pct 0.10 (early-bar sampling):** iter 21 DISCARD, Brier regression +63%. Permanent for all assets.
- **time_pcts expansion beyond 3 points:** iters 12, 21 (BTC) and 28 (ETH) all DISCARD. 3-point set [0.30,0.50,0.80] confirmed optimal for both assets.
- **time_pct 0.95 for ETH:** iter 28 DISCARD (Brier identical — no strict improvement). ETH-specific permanent.
- **embargo_period tuning (both directions):** iter 9 BTC 6→12 DISCARD; iter 30 ETH 6→3 DISCARD. embargo_period=6 confirmed optimal. Permanent for both assets.
- **n_splits above 8:** iter 11 DISCARD (HPO starvation). Blacklisted upward for all assets.
- **regime_params vol_window changes:** iter 17 BTC 120→240 DISCARD; iter 26 ETH 120→60 DISCARD. Window=120 confirmed. Permanent for both assets.
- **Static manual feature pruning:** iter 16 BTC OI DISCARD; iter 24 ETH regime DISCARD. LightGBM internal selection is superior. Do not manually remove features from cached_features without zero SHAP contribution across 3+ KEEP iterations.
- **Regime feature removal for ETH:** iter 24 DISCARD (0.178946 vs 0.178243). Regime features stay in ETH even absent from top-10 SHAP.
- **train_bars above 10000 for BTC:** learning curve saturation confirmed. Ceiling at 10000.
- **train_bars above 14000 for ETH:** iter 25 marginal gain at 14000; ceiling confirmed at 14000.
- **n_splits increase to 12 for BTC:** iter 11 DISCARD (HPO starvation, only 13 trials). Do not increase n_splits for any asset.

## HPO Range Recommendations

- `n_estimators`: maintain [100, 1500] — 0/5 KEEP rate on narrowing; wall-clock binds before range matters.
- `learning_rate`: maintain [0.005, 0.1] — wide range necessary given trial-count constraints.
- `max_depth`: maintain [2, 6] — no convergence data under non-starvation conditions.
- `num_leaves`: maintain [16, 128] — no convergence data.
- `min_child_samples`: maintain [100, 1000] — no convergence data.
- `reg_alpha`, `reg_lambda`: maintain [1e-8, 10.0] — no convergence data.
- `subsample`: maintain [0.6, 0.9] — no convergence data.
- `colsample_bytree`: maintain [0.4, 0.8] — no convergence data.
- Operational note: Wide ranges remain appropriate at current trial counts (24-34). TPE exploration across the full manifold is more valuable than exploitation in a narrow range. No range narrowing experiments warranted until trial count exceeds 40 per run.

## BTC Return Plan (after ETH iter 10/10, iteration ~32)

When ETH iter 10/10 completes (global iter ~32), execute mandatory config reset before first BTC experiment:

1. Set `walk_forward.train_bars` to 10000 (BTC ceiling confirmed iters 18+22).
2. Set `walk_forward.purge_period` to 12 (BTC-optimal confirmed iter 22).
3. Set `walk_forward.n_splits` to 8 initially; test 6 as priority #4.
4. Set `walk_forward.embargo_period` to 6 (optimal for both assets, confirmed iter 30).
5. Keep `time_pcts=[0.30,0.50,0.80]`, all 22 cached_features, all alpha feature groups.
6. Set `objective.drawdown_penalty_weight` back to 5.0 if ETH priority #2 changed it (BTC drawdown range is 0.13-0.46, not 0.017, so the doubled weight would incorrectly penalize BTC).

BTC research queue after reset:
- (a) n_splits 8→6 (priority #4 above) — informed by ETH n_splits result
- (b) min_target_corr 0.005→0.010 feature selection tightening (priority #5)
- (c) brier_threshold 0.20→0.15 objective gate tightening (priority #6)
- (d) if all above DISCARD: consider SOL or XRP asset expansion as next auditor-directed SWITCH

## Cross-Asset Signal Summary

| Asset | Best Brier | Best bs_sharpe | Iter Count | Regime in top-10 | Funding useful |
|-------|-----------|---------------|------------|------------------|----------------|
| BTC   | 0.101759  | 93.84         | 22         | Yes (iter 3+)    | No (iter 2)    |
| ETH   | 0.177773  | 274.44*       | 8          | No (all iters)   | No (iter 27)   |

*ETH bs_sharpe record 274.44 from iter 26 (DISCARD on Brier). Current ETH best Brier config gives bs_sharpe 267.08.

Key finding: ETH's structurally lower Brier floor (0.1778 vs BTC 0.1018) indicates ETH is a harder prediction target at 5m resolution, but its both-sides strategy generates 24x higher absolute PnL ($14M vs $584K) due to microstructure volatility and denser maker-fill opportunities. The prediction quality gap does not prevent profitability — it shifts the optimal strategy from single-side (BTC) to both-sides market-making (ETH).
