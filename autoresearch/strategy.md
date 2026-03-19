# Strategy Directive
Updated: 2026-03-20T07:30:00Z
After iteration: 35

## Priority Queue

1. **Run CPCV/PBO validation on current BTC best model (knobs.json at BTC-optimal).** This is the mandatory gate before any further asset expansion or structural changes. The acceptance criteria require PBO < 0.40 and Deflated Sharpe > 0.0 before going live. Neither has been measured across the entire 35-iteration research cycle. BTC Brier 0.101759 satisfies the OOS Brier threshold (< 0.25), but a high PBO would indicate combinatorial overfitting across the 35 config trials and invalidate the result. Mechanically: run the existing backtest engine in CPCV mode on the BTC best config (train_bars=10000, purge_period=24, n_splits=8, time_pcts=[0.30,0.50,0.80], 22 features). Log PBO and Deflated Sharpe in the next results.tsv row. If PBO >= 0.40: the BTC model is overfit and the research direction must shift to structural remedies (higher regularization, reduced feature count via max_pairwise_corr tightening, or longer purge_period). If PBO < 0.40 and Deflated Sharpe > 0.0: BTC is validated and SOL expansion is greenlit. Do NOT proceed to SOL/XRP before this result is logged.

2. **Run CPCV/PBO validation on current ETH best model.** Identical rationale as priority #1 but for ETH config (train_bars=14000, purge_period=12, n_splits=8, time_pcts=[0.30,0.50,0.80], 22 features, drawdown_penalty_weight=10.0 per best_knobs.json). ETH Brier 0.177772 satisfies OOS Brier < 0.25. ETH's improvement trajectory was structurally shallow (0.26% gain across 9 iterations vs BTC's 96.4% improvement) — the shallow slope could indicate ETH is closer to its theoretical prediction floor rather than overfit, but PBO must confirm this. Log PBO and Deflated Sharpe. This can run concurrently with priority #1 if the compute infrastructure permits parallel validation runs.

3. **SOL asset baseline — first experiment on SOL (conditional on BTC PBO < 0.40).** If BTC PBO passes, switch asset to SOL and run a baseline training with the current BTC-optimal config as starting point: train_bars=10000, purge_period=24, n_splits=8, time_pcts=[0.30,0.50,0.80], all 22 cached_features (including 4 liquidation alpha features and 3 regime features). SOL has 432K bars available (2022-2026, same as XRP), providing adequate walk-forward coverage for n_splits=8 at train_bars=10000. SOL is the preferred first expansion asset over XRP because: (a) SOL microstructure (higher retail participation, memecoin correlation) may provide richer regime signal than XRP, (b) SOL volatility clustering is more BTC-like than XRP's payment-utility profile, meaning the BTC-trained feature set is more likely to transfer. Expected outcome: Brier in [0.12, 0.20] range. If Brier > 0.20 (acceptance threshold), this signals the current feature set does not generalize and flags a need for asset-specific feature engineering. If Brier < 0.20, KEEP and proceed to train_bars extension for SOL (mirroring BTC iter 8 which gave 27.5% improvement).

4. **XRP asset baseline (conditional on SOL baseline completing, regardless of SOL result).** After SOL baseline, run XRP baseline with identical config. XRP's lower intra-bar volatility and narrower tick structure may produce a different Brier floor than BTC/SOL. Logging XRP baseline independently of SOL result creates a cross-asset comparison matrix that informs whether asset-specific feature engineering is needed (e.g., payment flow features for XRP). If both SOL and XRP produce Brier > 0.20, the priority shifts back to structural changes on BTC/ETH rather than further asset expansion.

5. **Structural change: objective.primary switch from "brier" to "sharpe" for BTC (conditional on BTC validation passing).** BTC has been optimizing Brier for 22+ iterations with no movement below 0.1015 in 13 consecutive attempts. The model may be in a Brier-specific local optimum that Sharpe-primary optimization would escape. Evidence: BTC backtest_sharpe improved from 73.27 (iter 1) to 109.25 (iter 22) alongside Brier improvements, then stalled. Switching primary to "sharpe" with Brier as a secondary penalty constraint (brier_threshold=0.15, brier_penalty_weight=10.0 to prevent regression) reshapes the Optuna landscape without changing the model architecture. Mechanically: set `objective.primary` to "sharpe", keep `objective.brier_threshold` at 0.15, keep `objective.brier_penalty_weight` at 10.0. If this yields Brier < 0.101759 (strict improvement), KEEP. If Brier regresses beyond 0.103, DISCARD and revert to brier-primary. This is lower priority than validation (priorities 1-2) and SOL/XRP expansion (priorities 3-4) because config-level optimization on BTC is confirmed exhausted — but it represents the last untested objective reformulation for BTC.

6. **Structural change: reg_alpha/reg_lambda ceiling raise for BTC (conditional on sharpe-primary result).** The current HPO search space allows reg_alpha and reg_lambda up to 10.0. After 30+ HPO runs, we have no convergence data on where regularization optimum sits within [1e-8, 10.0]. If Optuna is consistently selecting near the upper bound (reg_alpha/reg_lambda > 5.0), this is evidence the model benefits from stronger regularization and the upper bound is binding. Raise the ceiling to [1e-8, 50.0] for both params and run one BTC experiment. This is a low-risk structural test because the model architecture is unchanged — it only widens the regularization manifold for HPO to explore. Only execute if the researcher has access to logged best_params from recent KEEP iterations showing reg_alpha or reg_lambda > 5.0.

## Observations

- **KEEP rates by category (all 35 iterations):**
  - Baseline / pipeline corrections: 2/2 (100%)
  - train_bars extension: 3/3 (100%) — iters 8, 18, 25; train_bars is the single most reliable lever
  - KEEP-VERIFIED: 1/1 (100%) — iter 8 (100-trial verification confirmed)
  - Asset baselines: 2/2 (100%) — iter 7 (BTC), iter 23 (ETH)
  - purge_period tuning: 2/4 (50%) — iter 22 KEEP (BTC 12→24), iter 29 KEEP (ETH 24→12)
  - drawdown_penalty_weight adjustment: 1/1 (100%) — iter 32 KEEP (ETH 5.0→10.0, marginal)
  - Alpha features (BTC): 2/3 (67%) — regime KEEP (iter 3), liquidation KEEP (iter 4), funding DISCARD (iter 2)
  - Alpha features (ETH): 0/2 (0%) — regime removal DISCARD (iter 24), funding add DISCARD (iter 27)
  - time_pcts adjustment: 1/5 (20%) — iter 14 KEEP [0.30,0.50,0.80]; all expansion attempts DISCARD
  - HPO range narrowing: 0/5 (0%) — iters 10, 13, 15, 19, 20; wall-clock binding not range
  - Regime config window changes: 0/2 (0%) — iters 17, 26
  - Feature pruning (manual): 0/2 (0%) — iters 16, 24
  - Interaction features: 0/1 (0%) — iter 6
  - n_splits changes: 0/2 (0%) — iter 11 (8→12 DISCARD), iter 31 (ETH 8→6 DISCARD)
  - embargo_period changes: 0/2 (0%) — iters 9, 30 (both directions)
  - Objective/gate changes (total): 1/4 (25%) — iter 32 KEEP (drawdown weight), iters 33-35 DISCARD/no-change
  - **Overall: 16 KEEP/KEEP-VERIFIED out of 35 = 45.7%**

- **BTC confirmed at hard Brier plateau.** Best Brier 0.101759 (iter 22) unchanged across 13 consecutive experiment attempts (iters 23-35). The last strict improvement was iter 22 (purge_period 12→24). All 6 strategy priorities executed post-ETH (iters 33-35 + prior) yielded DISCARD or no-change. Config-level search is definitively exhausted for BTC.

- **ETH Brier floor confirmed at 0.177772 (iter 29).** Total ETH improvement across 9 iterations: 0.000471 (0.26% relative). ETH is structurally harder to predict at 5m resolution than BTC — tick features (bar_position, return_5, vol_ratio) dominate all 9 ETH iterations; regime_vol_zscore never enters ETH top-10 SHAP despite being BTC's most valuable alpha signal (top-10 from iter 3 onwards).

- **Researcher compliance: full (iters 31-35).** All 5 post-iter-30 experiments executed in exact priority queue order. The ack confirms BTC priority queue is exhausted and correctly identifies SOL/XRP expansion as next step. The researcher is ahead of this directive on asset selection intent — validation must precede expansion per this directive.

- **Critical gap: PBO and Deflated Sharpe have never been measured.** Acceptance criteria (PBO < 0.40, Deflated Sharpe > 0.0) are unverified. With 35 config experiments across 2 assets and ~16 KEEP iterations, the risk of combinatorial overfitting is non-trivial. This is the highest-priority action before any further research.

- **Brier improvement trajectory: decelerating sharply.** Progression per BTC KEEP: iter 7 (new pipeline, 0.1982) → iter 8 (+27.5%, 0.14372) → iter 14 (+29.1%, 0.10184) → iters 18, 22 (marginal, <0.01%). The large gains came from architectural corrections (train_bars, time_pcts), not feature or HPO tuning. The remaining improvement reservoir on the current architecture is near zero.

- **Both-sides strategy dominates for both assets.** ETH bs_pnl ~$14.07M (bs_sharpe 267) vs single-side $176 (sharpe 264). BTC bs_pnl ~$584K (bs_sharpe 93.84) vs single-side $45.55 (sharpe 109). ETH both-sides generates ~79,500x more absolute PnL. BTC single-side has superior risk-adjusted return (sharpe 109 vs 94) but lower absolute PnL. ETH is a market-making asset; BTC single-side sniper may have distinct deployment value.

- **n_splits=6 confirmed suboptimal for both assets.** BTC iter 33 (n_splits=6): Brier 0.101954 > best 0.101759. ETH iter 31 (n_splits=6): Brier 0.17835 > best 0.177773. Despite the HPO trial-count improvement (+18-46% more trials), reduced fold count degrades model quality. n_splits=8 is confirmed optimal for all assets. Blacklisted permanently downward.

- **best_knobs.json is in ETH config (train_bars=14000, purge_period=12).** Current knobs.json is BTC-optimal (train_bars=10000, purge_period=24). The researcher must apply asset-specific config before each new asset's baseline experiment. For SOL/XRP baseline: start from BTC-optimal knobs.json (train_bars=10000, purge_period=24) as the default starting point, not best_knobs.json.

## Blacklist

- **Interaction features (all 8 pairs):** iter 6 DISCARD, Brier regression +41%. Permanent for all assets. Do not re-enable.
- **Funding features in cached_features:** iter 2 (BTC) DISCARD, iter 27 (ETH) DISCARD. 0/2 KEEP rate across both assets. Permanent for BTC and ETH. Test for SOL/XRP only after baseline is established.
- **HPO range narrowing (all configurations):** iters 10, 13, 15, 19, 20 — 0/5 KEEP rate. Wall-clock is the binding constraint, not search range width. Permanent for all assets.
- **time_pcts expansion beyond 3 points:** iters 12, 21 (BTC) and 28 (ETH) all DISCARD. 3-point set [0.30,0.50,0.80] confirmed optimal for both BTC and ETH. Test for SOL/XRP only after baseline.
- **time_pct 0.10 (early-bar sampling):** iter 21 DISCARD, Brier regression +63%. Permanent for all assets.
- **embargo_period tuning (both directions):** iter 9 BTC 6→12 DISCARD; iter 30 ETH 6→3 DISCARD. embargo_period=6 is confirmed optimal. Permanent for both assets.
- **n_splits above 8:** iter 11 DISCARD (HPO starvation). Permanent upward blacklist for all assets.
- **n_splits below 8 (to 6):** iter 33 BTC DISCARD, iter 31 ETH DISCARD. 0/2 KEEP rate. n_splits=8 is confirmed optimal. Permanent downward blacklist for all assets.
- **regime_params vol_window/lookback_window changes:** iter 17 BTC 120→240 DISCARD; iter 26 ETH 120→60 DISCARD. Window=120 confirmed for both assets. Permanent.
- **Static manual feature pruning from cached_features:** iter 16 BTC OI DISCARD; iter 24 ETH regime DISCARD. LightGBM internal selection outperforms manual pruning. Do not remove features unless zero SHAP contribution confirmed across 3+ consecutive KEEP iterations.
- **train_bars above 10000 for BTC:** learning curve saturation confirmed at 10000. Ceiling at 10000.
- **train_bars above 14000 for ETH:** marginal gain plateau confirmed at 14000. Ceiling at 14000.
- **brier_threshold tightening (0.20→0.15) as standalone experiment for BTC:** iter 35 DISCARD (no change). Model already below the new gate; penalty non-binding. Do not re-attempt as a standalone lever.
- **min_target_corr tightening (0.005→0.010) for BTC:** iter 34 DISCARD (identical Brier). All current features already exceed the threshold or are protected. Do not re-attempt for BTC.

## HPO Range Recommendations

- `n_estimators`: maintain [100, 1500]. 0/5 KEEP rate on narrowing. Wall-clock constrains trial count before range matters; widening the range further has no benefit at 30-34 trials per run.
- `learning_rate`: maintain [0.005, 0.1]. Wide range necessary given trial-count constraints. No convergence clustering data available.
- `max_depth`: maintain [2, 6]. No convergence data collected under non-starvation conditions (>=30 trials).
- `num_leaves`: maintain [16, 128]. No convergence data.
- `min_child_samples`: maintain [100, 1000]. No convergence data.
- `reg_alpha`, `reg_lambda`: maintain [1e-8, 10.0]. If best_params logs from KEEP iterations show these clustering near 10.0 (upper bound), raise ceiling to 50.0 as per priority #6 above.
- `subsample`: maintain [0.6, 0.9]. No convergence data.
- `colsample_bytree`: maintain [0.4, 0.8]. No convergence data.
- Operational note: Range narrowing is permanently blacklisted (0/5 KEEP rate). The only warranted range change is a ceiling raise if Optuna is hitting the upper bound on regularization params. This requires inspecting best_params from logged KEEP iterations — the researcher should report these values in the description field going forward.

## Validation Gate

Before any SOL/XRP experiments, the following validation metrics must be logged in results.tsv:

| Metric | Required | BTC Status | ETH Status |
|--------|----------|-----------|-----------|
| OOS Brier | < 0.25 | 0.101759 PASS | 0.177772 PASS |
| OOS ECE | < 0.05 | 0.0088 PASS | 0.0252 PASS |
| Net PnL | > 0 | $45.55/bar PASS | $176.50/bar PASS |
| Max drawdown | < 30% | 0.1361 PASS | 0.0175 PASS |
| PBO | < 0.40 | NOT MEASURED | NOT MEASURED |
| Deflated Sharpe | > 0.0 | NOT MEASURED | NOT MEASURED |

PBO and Deflated Sharpe are the two unverified acceptance criteria. Both must be computed before the research program is considered validated.

## Cross-Asset Status Summary

| Asset | Best Brier | Best bs_sharpe | Iter Count | Config Status | PBO Validated |
|-------|-----------|---------------|------------|--------------|---------------|
| BTC   | 0.101759  | 93.84         | 22         | Exhausted    | No            |
| ETH   | 0.177772  | 274.44*       | 9          | Exhausted    | No            |
| SOL   | —         | —             | 0          | Not started  | No            |
| XRP   | —         | —             | 0          | Not started  | No            |

*ETH bs_sharpe record 274.44 from iter 26 DISCARD config. Current ETH best Brier config gives bs_sharpe 267.08.

Key structural finding: the largest Brier improvements in this research program came from architectural fixes (train_bars extension, time_pcts reduction to 3 points), not from feature or HPO tuning. With architecture confirmed, the next phase is validation then generalization — not further config search on known-plateau assets.
