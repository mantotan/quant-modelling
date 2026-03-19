# Strategy Directive
Updated: 2026-03-20T08:30:00Z
After iteration: 36 (SOL iter 37 baseline in progress)

## Priority Queue

### SOL-Specific Priorities (iters 37-46)

1. **[SOL iter 37 — currently running] Accept SOL baseline result as KEEP if Brier < 0.25 and ECE < 0.05.** No knobs changes needed for this run — it uses BTC-optimal config (train_bars=10000, n_splits=8, purge_period=24, time_pcts=[0.30,0.50,0.80], 22 features). Expected SOL Brier range: 0.15-0.22 given higher volatility than BTC and similar bar count to ETH (432K). If Brier > 0.25 despite acceptance threshold, log as DISCARD and escalate to auditor — this would indicate the BTC feature set does not transfer to SOL and asset-specific engineering is required. Record the following in the description field: (a) actual Brier vs expectation, (b) whether regime_vol_zscore appears in top-10 SHAP (critical SOL differentiator test), (c) trial count achieved.

2. **[SOL iter 38] train_bars 10000→14000.** This is the single highest-confidence lever in the entire research program: train_bars extension has produced KEEP results on 100% of attempts (BTC iter 8: +27.5% Brier improvement; BTC iter 18: marginal improvement; ETH iter 25: improvement + bs_sharpe new record). ETH optimal was 14000 (same bar count class as SOL at 432K). SOL has 432K bars — n_splits=8 at train_bars=14000 requires 14000×8 + 2000×8 = 128K training bars, well within the 432K data budget (leaving 304K bars unused). If SOL Brier floor is at a similar level to ETH (0.17-0.18), this is the fastest path to improvement. If SOL baseline Brier is already below 0.15 (BTC-class), train_bars=12000 first for caution, then 14000. Verify immediately if improvement exceeds 2% relative.

3. **[SOL iter 39] purge_period optimization — test purge_period 24→12.** BTC optimal was purge_period=24 (KEEP, iter 22). ETH optimal was purge_period=12 (KEEP, iter 29). SOL microstructure is distinct from both: higher retail-driven momentum, more frequent regime transitions, and stronger mean-reversion after liquidation cascades. The shorter purge window (12 bars = 1h at 5m) may better match SOL's faster decorrelation vs BTC's slower cycle. Run this after train_bars extension to avoid confounding the two levers. If KEEP: SOL optimal purge_period=12. If DISCARD: SOL optimal purge_period=24 (BTC-like). This is the only confirmed asset-differentiating walk-forward parameter.

4. **[SOL iter 40] regime_params tuning — test vol_window/lookback_window 120→60.** BTC kept default 120 (iter 17 DISCARD at 240). ETH tried 120→60 (iter 26 DISCARD) but regime features never appeared in ETH top-10 SHAP. SOL may respond differently: if SOL baseline shows regime_vol_zscore in top-10 SHAP (as it did for BTC from iter 3 onward), then a shorter regime window (60 bars = 5h lookback) may capture SOL's faster volatility cycles. Only execute this if SOL baseline confirms regime_vol_zscore in top-10 SHAP. If regime features are absent from SOL top-10 SHAP (ETH pattern), skip this and move to priority #5 instead.

5. **[SOL iter 41] Objective switch: objective.primary "brier"→"sharpe" for SOL.** Both BTC and ETH reached hard Brier floors that no config change could pierce. The hypothesis is that Sharpe-primary optimization reshapes the Optuna landscape and escapes local minima. BTC Brier floor: 0.101759 (4 consecutive identical results, iters 33-36). ETH Brier floor: 0.177773 (1 marginal improvement in final iter). The SOL landscape is fresh — applying Sharpe-primary before hitting a Brier floor tests whether starting with Sharpe-primary avoids the floor-locking entirely. Mechanically: set `objective.primary` to "sharpe", keep `objective.brier_threshold` at 0.20 (acceptance gate as soft constraint), keep `objective.brier_penalty_weight` at 10.0. If Brier improves strictly, KEEP and apply Sharpe-primary to XRP baseline as well. If Brier is identical or regresses, DISCARD and revert to brier-primary — confirming objective switching has no impact for SOL either.

6. **[SOL iter 42] drawdown_penalty_weight 5.0→10.0 for SOL.** This produced a marginal KEEP for ETH (iter 32: Brier 0.177773→0.177772, 0.000001 improvement). With SOL's higher volatility, the drawdown penalty may be more binding and produce a more material effect. Cost: negligible risk of regression. Run after iter 41 result is known — if Sharpe-primary was adopted, run this under Sharpe-primary config. If reverted, run under brier-primary.

7. **[SOL iter 43-45] Remaining SOL levers (in order):** (a) test funding features in cached_features for SOL — funding was DISCARD for BTC and ETH but SOL funding dynamics are distinct (perpetual funding rates are more volatile for SOL); (b) test time_pct 0.95 addition — ETH iter 28 showed no improvement but SOL near-close signal may carry more momentum; (c) min_target_corr 0.005→0.010 as a check — this was a no-op for BTC (iter 34) but verifies SOL feature quality. These are low-confidence experiments serving as search completeness rather than expected KEEPs.

8. **[SOL iter 46] Asset rotation: switch to XRP baseline.** After 10 SOL iterations (iters 37-46), rotate to XRP following the BTC→ETH→SOL→XRP rotation protocol. XRP config starting point: BTC-optimal knobs.json (train_bars=10000, n_splits=8, purge_period=24). XRP characteristics diverge most from BTC (payment utility vs. speculative asset, different tick structure, lower intra-bar volatility), so the XRP baseline Brier may be the most diagnostic test of feature set generalizability.

### Cross-Asset / Structural Priorities (post-SOL)

9. **[Post iter 46] CPCV/PBO validation on BTC and ETH best models.** This remains the most important unmeasured acceptance criterion. PBO must be < 0.40 for both assets before the program is considered validated. With 36 config experiments across 2 assets, the combinatorial overfitting risk is non-trivial. If the researcher has not run CPCV validation by iteration 50, the auditor should be prompted to issue a mandatory VALIDATION directive.

10. **[Post iter 50, conditional] Structural investigation: larger HPO trial budget via trial-per-split parallelism.** All HPO starvation evidence points to wall-clock as the binding constraint (0/5 KEEP on range narrowing; 14-30 trials when 40-50 are targeted). If the training script supports per-split parallelism (running Optuna trials concurrently across folds), doubling the trial budget without increasing wall-clock time would break the starvation pattern. This requires builder involvement to implement — not a researcher-executable knob change. Flag for auditor escalation if stagnation persists beyond iter 50.

## Observations

- **KEEP rates by category (all 36 iterations):**
  - Baseline / pipeline corrections: 2/2 (100%)
  - Asset baselines (new asset first run): 2/2 (100%) — BTC iter 7, ETH iter 23
  - KEEP-VERIFIED runs: 1/1 (100%) — BTC iter 8
  - train_bars extension: 3/3 (100%) — iters 8, 18, 25; single most reliable lever in the program
  - purge_period tuning: 2/4 (50%) — BTC iter 22 KEEP (12→24), ETH iter 29 KEEP (24→12)
  - drawdown_penalty_weight adjustment: 1/1 (100%) — ETH iter 32 KEEP (marginal, 0.000001 Brier)
  - Alpha features (BTC): 2/3 (67%) — regime KEEP iter 3, liquidation KEEP iter 4, funding DISCARD iter 2
  - Alpha features (ETH): 0/2 (0%) — regime removal DISCARD iter 24, funding add DISCARD iter 27
  - time_pcts adjustment: 1/5 (20%) — iter 14 KEEP [0.30,0.50,0.80]; all 4 expansion attempts DISCARD
  - HPO range narrowing: 0/5 (0%) — iters 10, 13, 15, 19, 20; wall-clock binding, not range
  - Regime config window changes: 0/2 (0%) — iters 17 (BTC), 26 (ETH)
  - Feature pruning (manual): 0/2 (0%) — iters 16 (BTC OI), 24 (ETH regime)
  - Interaction features: 0/1 (0%) — iter 6; +41% Brier regression
  - n_splits changes: 0/2 (0%) — iter 11 (8→12 DISCARD HPO starvation), iter 31 (ETH 8→6 DISCARD)
  - embargo_period tuning: 0/2 (0%) — iters 9 (BTC 6→12), 30 (ETH 6→3)
  - BTC objective/gate exhaustion experiments: 0/4 (0%) — iters 33, 34, 35, 36
  - **Overall: 16 KEEP/KEEP-VERIFIED out of 36 = 44.4%**

- **BTC confirmed at hard architectural floor.** Best Brier 0.101759 (iter 22) unchanged across 14 consecutive experiments (iters 23-36). Iterations 33-36 were all DISCARD with Brier exactly equal to best (0.101759), confirming the floor is locked — not merely a search stagnation but a model capacity limit at the current feature set. The last strict BTC improvement was iter 22 (purge_period 12→24, delta -0.000070). Config-level search is definitively exhausted.

- **ETH confirmed at architectural floor.** Best Brier 0.177772 (iter 32) with improvement slope of 0.000471 total (0.26%) across 9 iterations. ETH regime features never entered top-10 SHAP (vs BTC where regime_vol_zscore was a persistent top-10 signal from iter 3). Tick features (bar_position, return_5, vol_ratio) dominate ETH across all 9 iterations — ETH's intra-bar signal is structurally dominated by price-action microstructure rather than macro regime state.

- **Researcher compliance: full.** Researcher correctly identified BTC priority queue exhaustion after iters 33-36 and executed the asset rotation to SOL (iter 37 baseline) per protocol. The ack notes SOL expected Brier range 0.15-0.22, which aligns with this directive's expectation.

- **SOL asset profile differs from both BTC and ETH in ways that may produce distinct results:**
  - SOL has higher retail participation and stronger memecoin correlation than BTC, suggesting more volatile regime transitions — this may make regime features MORE useful than for ETH, where they were absent from top-10 SHAP
  - SOL intra-bar volatility is higher than BTC (wider price swings within 5m bars), which could either improve signal (clearer directional momentum) or worsen Brier (noisier outcomes)
  - SOL's 432K bar count matches ETH, suggesting train_bars=14000 as the natural extension target (same as ETH iter 25)
  - SOL perpetual funding rates are historically more volatile than BTC/ETH, making the funding feature group a higher-probability candidate for SOL than it was for either prior asset

- **Brier improvement trajectory: structurally driven, not parameter-driven.** The two major step-function improvements in the program came from architectural changes: iter 8 (train_bars 5000→8000, -27.5% Brier) and iter 14 (time_pcts 4→3 points, -29.1% Brier). All subsequent feature and HPO tuning combined yielded < 0.1% improvement. This pattern strongly predicts that SOL's largest gain will come from train_bars extension (priority #2), not from feature or objective tuning.

- **Both-sides strategy performance summary:**
  - BTC: bs_pnl $584K (bs_sharpe 93.84) vs single-side $45.55 (sharpe 109.25). Single-side has better risk-adjusted return; both-sides has 12,800x higher absolute PnL.
  - ETH: bs_pnl $14.07M (bs_sharpe 267.08) vs single-side $176.50 (sharpe 264.56). ETH both-sides dominates on all metrics — ETH is the primary market-making asset.
  - Note: ETH bs_sharpe record is 274.44 from DISCARD iter 26 config (regime window 60), not the current best-Brier config. The best-Brier config gives bs_sharpe 267.08. PnL optimization and Brier optimization are not perfectly aligned for ETH.
  - For SOL baseline, track whether bs_sharpe exceeds ETH's 267 — SOL's higher volatility could generate more market-making opportunities.

- **HPO trial count status:** Current config achieves 24-34 trials per run at n_splits=8 with 8-minute wall-clock budget. This is the binding operational constraint. No range-narrowing experiment has ever produced a KEEP — the wall-clock limit is more constraining than the search space width.

- **best_knobs.json is in ETH config (train_bars=14000, purge_period=12, drawdown_penalty_weight=10.0).** Current knobs.json is BTC-optimal (train_bars=10000, purge_period=24, drawdown_penalty_weight=5.0). For SOL baseline (iter 37), knobs.json BTC-optimal is the correct starting point — do NOT use best_knobs.json. The researcher ack confirms this was followed correctly.

## Blacklist

- **Interaction features (all 8 pairs):** iter 6 DISCARD, Brier +41% regression. Permanent for all assets. Do not re-enable regardless of asset.
- **Funding features in cached_features for BTC:** iter 2 DISCARD. Not in top-10 SHAP for BTC. Permanent for BTC only. Test allowed for SOL (different funding dynamics) after baseline is established.
- **Funding features in cached_features for ETH:** iter 27 DISCARD. Not in top-10 SHAP for ETH. Permanent for ETH. Test allowed for SOL/XRP.
- **HPO range narrowing (all configurations):** iters 10, 13, 15, 19, 20 — 0/5 KEEP rate. Wall-clock is the binding constraint. Permanent blacklist for all assets. The only warranted range change is a ceiling raise if Optuna's best_params cluster near the upper bound.
- **time_pcts expansion beyond 3 points (any direction):** iters 12 (BTC, 4→6), 21 (BTC, add 0.10), 28 (ETH, add 0.95) — all DISCARD. The 3-point set [0.30,0.50,0.80] is confirmed optimal for BTC and ETH. Do not add time points for SOL/XRP without evidence that additional points improve Brier.
- **time_pct 0.10 (early-bar sampling):** iter 21 DISCARD, Brier +63% regression. Permanent for all assets.
- **embargo_period tuning (both directions from 6):** iter 9 BTC 6→12 DISCARD; iter 30 ETH 6→3 DISCARD. embargo_period=6 is confirmed. Permanent for all assets.
- **n_splits above 8:** iter 11 DISCARD (HPO starvation at n_splits=12). Permanent upward blacklist.
- **n_splits below 8 (to 6):** iter 33 BTC DISCARD, iter 31 ETH DISCARD (0/2 KEEP rate). n_splits=8 is confirmed optimal. Permanent downward blacklist.
- **regime_params window changes for BTC (120→240):** iter 17 DISCARD. Permanent for BTC. Test for SOL only if regime_vol_zscore appears in top-10 SHAP.
- **regime_params window changes for ETH (120→60):** iter 26 DISCARD. Permanent for ETH (regime features not in top-10 SHAP regardless of window).
- **Manual feature pruning from cached_features:** iter 16 BTC OI DISCARD; iter 24 ETH regime DISCARD. LightGBM internal selection outperforms manual pruning. Never remove features without 3+ consecutive KEEP iterations showing zero SHAP contribution.
- **train_bars above 10000 for BTC:** saturation confirmed. Ceiling at 10000 for BTC.
- **train_bars above 14000 for ETH:** marginal gain plateau confirmed. Ceiling at 14000 for ETH.
- **BTC objective gate tightening as standalone experiment:** iters 34 (min_target_corr), 35 (brier_threshold 0.20→0.15), 36 (brier_threshold 0.10) — all DISCARD or no-change. Model at architectural floor; gate tightening does not reshape Optuna landscape. Do not re-attempt for BTC.
- **n_splits 8→6 for any asset:** 0/2 KEEP rate, both assets tested. Permanent.

## HPO Range Recommendations

- `n_estimators`: maintain [100, 1500]. Wall-clock constrains trial count before range width matters.
- `learning_rate`: maintain [0.005, 0.1]. No convergence clustering data under non-starvation conditions.
- `max_depth`: maintain [2, 6]. No clustering data. Note: lower bound of 2 is appropriate for Pulse's short intra-bar sequences.
- `num_leaves`: maintain [16, 128]. No clustering data.
- `min_child_samples`: maintain [100, 1000]. Lower bound of 100 is a hard floor (8 correlated samples per bar per PROGRAM.md; do not lower).
- `reg_alpha`, `reg_lambda`: maintain [1e-8, 10.0]. If researcher observes best_params consistently showing reg_alpha or reg_lambda > 8.0 across 3+ KEEP iterations, raise upper bound to 50.0 — this is the only evidence-gated ceiling raise warranted.
- `subsample`: maintain [0.6, 0.9].
- `colsample_bytree`: maintain [0.4, 0.8].
- **Researcher action item:** begin reporting best_params values (at minimum learning_rate, max_depth, reg_alpha, reg_lambda) in the description field of results.tsv for all KEEP rows. This data is required to make evidence-based HPO range recommendations. Currently zero convergence data is available from 16 KEEP iterations.

## Cross-Asset Status Summary

| Asset | Best Brier | Best bs_sharpe | Iter Count | Config Status     | PBO Validated |
|-------|-----------|---------------|------------|-------------------|---------------|
| BTC   | 0.101759  | 93.84         | 22 (iters 7-36) | Exhausted — hard floor | No |
| ETH   | 0.177772  | 267.08        | 9 (iters 23-32) | Exhausted — hard floor | No |
| SOL   | (baseline in progress — iter 37) | — | 0 complete | In progress | No |
| XRP   | —         | —             | 0          | Not started       | No |

## SOL Microstructure Hypothesis

SOL's likely experiment outcomes differ from BTC and ETH for the following structural reasons, which should inform how the researcher interprets baseline results:

- **If SOL Brier < 0.15 (BTC-class performance):** SOL intra-bar momentum is highly predictable; the feature set transfers well. Regime features likely in top-10 SHAP. Proceed aggressively with train_bars extension and purge_period tuning.
- **If SOL Brier in [0.15, 0.20] (ETH-class performance):** Feature set transfers adequately. Check whether regime_vol_zscore appears in top-10 SHAP — if yes, SOL is BTC-like structurally (use BTC priority sequence); if no, SOL is ETH-like (tick features dominate, fewer levers available).
- **If SOL Brier > 0.20 (above acceptance threshold):** The current feature set does not generalize to SOL. Escalate to auditor for ADD_ALPHA directive — SOL-specific features (e.g., memecoin correlation index, SOL ecosystem funding flows, validator stake changes) may be required. Do not proceed to XRP until auditor directive is received.

## Validation Gate (unchanged — still unmeasured)

| Metric         | Required | BTC Status          | ETH Status          |
|----------------|----------|---------------------|---------------------|
| OOS Brier      | < 0.25   | 0.101759 PASS       | 0.177772 PASS       |
| OOS ECE        | < 0.05   | 0.0088 PASS         | 0.0252 PASS         |
| Net PnL        | > 0      | $45.55/bar PASS     | $176.50/bar PASS    |
| Max drawdown   | < 30%    | 13.61% PASS         | 1.75% PASS          |
| PBO            | < 0.40   | NOT MEASURED        | NOT MEASURED        |
| Deflated Sharpe| > 0.0    | NOT MEASURED        | NOT MEASURED        |

PBO and Deflated Sharpe remain unmeasured after 36 iterations. If the research program reaches iteration 50 without measuring these, the auditor should issue a mandatory validation gate before any further asset expansion.
