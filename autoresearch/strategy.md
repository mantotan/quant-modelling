# Strategy Directive
Updated: 2026-03-20T03:00:00Z
After iteration: 24

## Priority Queue

1. **ETH: train_bars 10000→14000.** This was priority #1 in the previous directive and was skipped — the researcher ran regime feature removal (iter 24) instead. Priority #1 remains the single highest-confidence move for ETH. Evidence: on BTC, extending train_bars 5000→8000 produced a 27.5% Brier improvement (iter 8, 0.1982→0.143724), the largest single gain in the entire BTC experiment sequence. ETH's current Brier (0.178243) is 75% above BTC's optimum (0.101759), indicating the same class of underfitting. More training history allows the model to learn longer-cycle funding/liquidation regime patterns. Keep all other knobs identical: time_pcts=[0.30,0.50,0.80], n_splits=8, purge_period=24, embargo_period=6, wide HPO bounds. Gate: if fewer than 25 HPO trials complete, flag as budget-constrained. Expected gain: Brier reduction 0.010-0.025 (6-14%).

2. **ETH: test regime_params vol_window/lookback_window 120→60.** Iter 24 showed that regime features must stay in ETH (removing them caused Brier 0.178946 vs best 0.178243). However, the feature importance question remains: regime_vol_zscore is not in top-10 for ETH despite contributing marginal signal. The hypothesis is that ETH's higher-velocity regime transitions require a shorter window (60 bars = 5 hours at 5m) vs BTC's 120-bar (10-hour) optimum. This is a tuning experiment, not a removal experiment — iter 24 answered removal, this answers calibration. Do NOT change any other params. If regime_vol_zscore enters top-10: mark as ETH-productive and consider further narrowing. If Brier is flat or worse: accept that 120 is also ETH-optimal and move on. This experiment is distinct from and not blocked by iter 24's result.

3. **ETH: add funding features to cached_features (6 features: funding_rate, funding_rate_sma3, funding_rate_pctile, funding_rate_direction, funding_cumulative_24h, funding_hours_since).** On BTC, funding features were a DISCARD (iter 2). ETH has structurally different funding dynamics: higher funding rate volatility, more frequent sign changes, and stronger correlation with DeFi/staking flows at 5m resolution. With a lower ETH baseline Brier (0.178 vs BTC's 0.144 at equivalent stage), there is more room for alpha capture. Gate: run only after priority #1 establishes a new ETH baseline; funding tests should compare against the post-train_bars Brier, not the iter-23 baseline. If DISCARD: add to ETH-specific blacklist. If KEEP: ETH and BTC have asymmetric alpha — document and use asset-specific configs.

4. **ETH: test train_bars 14000→18000 (if priority #1 KEEPs with clean gain).** BTC's train_bars ceiling was 10000 (iter 18, 0.000008 marginal gain). ETH may have a higher ceiling given its different volatility regime distribution and higher institutional turnover. Only run this if priority #1 produces a Brier improvement >= 0.005. If priority #1 gain is sub-0.003: ceiling is already reached and this priority is skipped. Do not run this before priority #1 result is known.

5. **ETH: add time_pct 0.95 (late-bar snapshot, 1 additional point).** The current 3-point set [0.30, 0.50, 0.80] omits the very late bar. For ETH, where microstructure (tick features) dominates importance, the final 5% of a bar (last ~15 seconds) may carry strong directional momentum signal — buyers/sellers exhausting into bar close. Adding a single point at 0.95 is low-risk: it does not dramatically increase sample count (estimated +10% vs current 185K train samples) and should not trigger HPO starvation (iter 14 showed 34 trials with 3 points; 1 additional point should still fit in budget). Gate: run only after priorities #1-3 are resolved. Monitor trial count — abort if <25 trials complete.

## Observations

- **KEEP rates by category (all 24 iterations):**
  - Baseline/pipeline correction: 2/2 (100%)
  - train_bars extension: 2/2 (100%)
  - KEEP-VERIFIED: 1/1 (100%)
  - ETH asset baseline: 1/1 (100%)
  - purge_period tuning: 1/2 (50%) — iter 9 DISCARD, iter 22 KEEP
  - Alpha features BTC (funding/regime/liquidation): 2/3 (67%) — iter 2 DISCARD (funding), iters 3 and 4 KEEP
  - time_pcts adjustment: 1/4 (25%) — iter 14 KEEP [0.30,0.50,0.80], iters 12, 21 DISCARD (expansion), iter not yet run for 0.95
  - HPO range narrowing: 0/5 (0%) — iters 10, 13, 15, 19, 20
  - Regime config changes (window/removal): 0/3 (0%) — iters 17, 24 DISCARD, and iter 6 interaction DISCARD
  - Feature pruning (manual): 0/2 (0%) — iters 16, 24
  - Interaction features: 0/1 (0%) — iter 6
  - embargo_period: 0/1 (0%) — iter 9
  - n_splits above 8: 0/1 (0%) — iter 11
  - Overall: 12 KEEP/KEEP-VERIFIED out of 24 = 50%

- **Iter 24 compliance deviation noted.** Previous directive priority #1 was train_bars 10000→14000. Researcher ran priority #3 (regime feature removal) first. The deviation is understandable — regime feature behavior was actively unresolved after iter 23's SHAP report — but iter 24 is now a DISCARD and train_bars remains the highest-confidence untested move for ETH. Priority #1 is reinstated at top position.

- **Regime features: keep in ETH, but tuning not yet tested.** Iter 24 confirms regime features contribute marginal signal for ETH (removing them degraded Brier by 0.0007). However, whether tuning the window size (120→60) can make regime_vol_zscore enter top-10 is still open. Removal is now blacklisted for ETH; window tuning remains active.

- **ETH both-sides strategy remains extraordinary.** Iter 23 bs_sharpe 253.47, iter 24 bs_sharpe 251.62 (even on a DISCARD model). This confirms the ETH both-sides PnL is structurally driven by ETH's higher volatility and tick-feature dominance, not dependent on incremental Brier improvement. The both-sides profit mechanism for ETH (spread capture + volume) is robust across Brier levels.

- **ETH Brier has not yet benefited from train_bars extension.** BTC went from 0.1982 → 0.1438 → 0.1018 through train_bars + time_pcts optimization. ETH is still at 0.178243 (baseline). The 0.076-point gap to BTC optimum (0.101759) is almost entirely untouched structural improvement — this represents the primary research opportunity.

- **HPO starvation confirmed permanent.** 30-34 trials per run is the stable budget at current dataset size. Wide HPO bounds [100,1500] n_estimators, [0.005,0.1] lr produce equivalent results to narrowed bounds with this trial count. No further HPO range experiments are warranted.

- **Brier trajectory: BTC plateau, ETH early-stage.** BTC has been flat within 0.0001 Brier for 6 iterations. ETH is in the equivalent position BTC was at iter 7 (Brier 0.1982, "new baseline"). The expected ETH improvement trajectory mirrors BTC but with potentially higher ceilings given ETH's different feature importance profile.

- **OOS accuracy divergence: BTC 0.8598 vs ETH 0.7363.** This 12-point gap reflects the baseline-vs-optimized stage difference, not a structural ETH weakness. ETH accuracy should approach BTC levels as train_bars and feature selection improve. The bs_pnl magnitude difference ($14M ETH vs $583K BTC) is partly explained by higher ETH tick-level volatility creating wider market-sim payoffs.

## Blacklist

- **Interaction features (all 8 pairs):** iter 6 DISCARD, Brier 0.2028 (+41% regression from 0.1437). Permanent for all assets.
- **Funding features in BTC cached_features:** iter 2 DISCARD (0.143929 vs 0.143872). BTC-specific. Not blacklisted for ETH.
- **HPO range narrowing (all configurations):** iters 10, 13, 15, 19, 20 — 0/5 KEEP rate. Root cause: wall-clock timeout binds at ~30 trials regardless of search space width. Permanent for all assets.
- **time_pct 0.10 (early-bar sampling):** iter 21 DISCARD, Brier 0.166316 (+63% regression). Permanent for BTC and ETH.
- **time_pcts expansion beyond 3 points (BTC):** iters 12 and 21 both DISCARD (HPO starvation + signal degradation). 3-point set [0.30,0.50,0.80] is confirmed optimal for BTC. ETH single-point expansion to 0.95 is not yet blacklisted and is active as priority #5.
- **embargo_period increase 6→12:** iter 9 DISCARD — noise-level difference (0.143727 vs 0.143724). No benefit.
- **n_splits above 8 without budget confirmation:** iter 11 DISCARD (13 trials at n_splits=12). Gate: confirm >35 trial completions. Irrelevant while ETH is focus.
- **train_bars above 10000 on BTC:** iter 18 learning curve saturation (0.000008 Brier gain). BTC ceiling confirmed.
- **train_bars below 8000 on BTC:** iter 8 hard floor (27.5% degradation at 5000 bars). Do not revert.
- **Static manual feature pruning:** iters 16 (OI features, BTC) and 24 (regime features, ETH) both DISCARD. LightGBM's internal feature selection handles pruning more efficiently than manual removal. Do not remove features from cached_features unless SHAP confirms zero contribution over multiple KEEP iterations.
- **regime_params vol_window above 120 on BTC:** iter 17 DISCARD (identical Brier at 240 bars). BTC optimal is 120. Not yet tested for ETH at 60-bar reduction.
- **Regime feature removal for ETH:** iter 24 DISCARD (0.178946 vs 0.178243). Confirmed: regime features stay in ETH cached_features even when not in top-10 SHAP.

## HPO Range Recommendations

- `n_estimators`: maintain [100, 1500] — narrowing 0/5 KEEP rate; wall-clock binds before range matters.
- `learning_rate`: maintain [0.005, 0.1] — no valid convergence data under non-starvation conditions.
- `max_depth`: maintain [2, 6] — no convergence data.
- `num_leaves`: maintain [16, 128] — no convergence data.
- `min_child_samples`: maintain [100, 1000] — no convergence data.
- `reg_alpha`, `reg_lambda`: maintain [1e-8, 10.0] — no convergence data.
- `subsample`: maintain [0.6, 0.9] — no convergence data.
- `colsample_bytree`: maintain [0.4, 0.8] — no convergence data.
- **Operational note:** 28-34 trials is the natural per-run budget. Wide bounds are appropriate for this trial count — they ensure the sampler explores the full manifold via the Optuna TPE prior rather than over-exploiting a narrow region. Accept this budget as fixed; do not attempt further range experiments.
