# Strategy Directive
Updated: 2026-03-20T09:30:00Z
After iteration: 39

## Priority Queue

### ESCALATION STATUS: PBO/CPCV VALIDATION GATE — STILL UNEXECUTED

The auditor ESCALATE directive has been outstanding since before iter 38. The researcher has now run
three SOL optimization iterations (37, 38, 39) without executing a single validation run. Dispatch
state confirms last_auditor_at=0 — the auditor has never been invoked. This is the most critical
structural risk in the program.

**Decision on SOL parallel vs pause:** SOL optimization should NOW PAUSE. The rationale: SOL has
completed its most impactful experiments (baseline + train_bars + purge_period = 3/3 KEEPs), and
the remaining SOL queue (drawdown_penalty, funding test, objective switch) carries diminishing
marginal value — all are expected to produce sub-0.01% Brier improvements at most. Continuing
SOL optimization while PBO remains unmeasured for BTC (22 config experiments), ETH (9 experiments),
and SOL itself (3 experiments) is operationally backwards: we do not know if any of these models
will survive the overfitting gate. Execute validation first, then complete SOL.

1. **[iter 40 — MANDATORY BLOCK] BTC PBO/CPCV validation run.** Run the BTC best-config in
   mode=verify with CPCV enabled. Config: train_bars=10000, purge_period=24, n_splits=8,
   time_pcts=[0.30,0.50,0.80], 22 cached+regime features, same best_knobs.json. Required
   measurements: (a) PBO value, (b) Deflated Sharpe, (c) number of CPCV paths used,
   (d) OOS Brier variance across paths (stability measure). Pass thresholds: PBO < 0.40 AND
   Deflated Sharpe > 0.0. Log as KEEP if both pass, DISCARD if either fails. If BTC fails PBO:
   halt all asset expansion, halt SOL continuation, escalate immediately to auditor — this signals
   structural overfitting in the optimization program and requires architectural review. Do not
   skip this run. BTC has the highest combinatorial overfitting exposure (22 config experiments)
   in the entire program.

2. **[iter 41 — MANDATORY BLOCK, after iter 40 result is known] ETH PBO/CPCV validation run.**
   Same protocol applied to ETH best-config: train_bars=14000, purge_period=12, n_splits=8,
   drawdown_penalty_weight=10.0. ETH has 9 optimization iterations (lower combinatorial exposure
   than BTC). Required measurements same as iter 40. Pass thresholds same. Only execute if BTC
   passed — if BTC failed, do not run ETH, escalate to auditor instead with BTC failure evidence.

3. **[iter 42 — MANDATORY BLOCK, after iter 41 result is known] SOL PBO/CPCV validation run.**
   Config: train_bars=14000, purge_period=12, n_splits=8. SOL has 3 optimization iterations —
   lowest combinatorial overfitting exposure of the three assets. Expected to pass if BTC and ETH
   pass. Required measurements same. This completes the mandatory validation sweep for all active
   assets. Only execute if ETH passed.

### SOL Continuation Queue (iters 43-47, conditional on validation pass)

These execute only after iters 40-42 confirm PBO < 0.40 and Deflated Sharpe > 0.0 for all three
assets. SOL is confirmed ETH-class (Brier 0.189372, tick-dominant SHAP, regime_vol_zscore absent).
Follow ETH priority sequence. Current knobs.json has train_bars=14000, purge_period=12, n_splits=8
already set — SOL-optimal config is current.

4. **[iter 43] SOL drawdown_penalty_weight 5.0→10.0.** ETH iter 32 produced a marginal KEEP
   (Brier improvement 0.000001). SOL has higher intra-bar volatility than ETH, making the 30%
   drawdown constraint more likely to bind during adverse folds, so the increased penalty weight
   may have more impact than for ETH. Change only drawdown_penalty_weight in objective block;
   leave all other config unchanged. Expected: KEEP with marginal improvement. Run 30+ HPO trials.

5. **[iter 44] SOL objective.primary "brier"→"sharpe".** The SOL Brier trajectory has been
   declining but slowly: 0.193016 (iter 37) → 0.189379 (iter 38) → 0.189372 (iter 39). The last
   two iters produced a combined 0.007 Brier reduction — the floor is approaching. Switching
   objective to Sharpe-primary before the floor locks may open new landscape. Rationale: BTC and
   ETH both hit hard Brier floors with zero further improvement after lock-in. Testing Sharpe-
   primary now avoids the late-stage objective switch pattern seen in BTC (iters 33-36, 0/4 KEEP).
   If Sharpe-primary produces Brier regression (> 0.189372): DISCARD and accept current Brier
   floor as the SOL ceiling. If Sharpe-primary produces KEEP (lower Brier despite different
   objective): record as evidence that cross-metric objective generalization works for ETH-class
   assets.

6. **[iter 45] SOL max_depth ceiling raise: hpo_search_space max_depth [2,6]→[2,8].** Evidence:
   best_params show max_depth=6 (at upper bound) in both iter 38 and iter 39 descriptions — 2/2
   consecutive SOL KEEPs with max_depth hitting the ceiling. The optimizer is ceiling-constrained.
   This is the first HPO range adjustment with confirmed convergence evidence. Change only
   max_depth upper bound from 6 to 8 in hpo_search_space. Expected: KEEP if true optimum is
   max_depth 7-8. If DISCARD: max_depth=6 is the true optimum, revert and add ceiling=6 to SOL
   blacklist. Do not apply to BTC/ETH as they are at confirmed floors.

7. **[iter 46] SOL funding features** (6 features: funding_rate, funding_rate_sma3,
   funding_rate_pctile, funding_rate_direction, funding_cumulative_24h, funding_hours_since).
   Add to cached_features (28 features total). Prior: 0/2 KEEP for BTC and ETH. However, SOL
   perpetual funding rates exhibit more frequent sign changes and larger magnitude deviations,
   creating a non-negligible hypothesis that funding captures SOL-specific leveraged positioning.
   Run after drawdown and objective experiments so their outcomes do not confound the feature
   signal. Acceptance criterion: funding features must appear in top-10 SHAP or produce strict
   Brier improvement. If absent from top-10 SHAP AND Brier identical: DISCARD and add SOL to
   funding permanent blacklist.

8. **[iter 47] Asset rotation: XRP baseline.** Only after iters 40-42 pass validation AND SOL
   has completed minimum 6 optimization iterations (iters 43-47). Starting config: BTC-optimal
   knobs.json (train_bars=10000, n_splits=8, purge_period=24, time_pcts=[0.30,0.50,0.80], 22
   features). Expected XRP Brier: 0.18-0.25 (payment-utility microstructure, lower speculative
   momentum than SOL/ETH). Primary diagnostic: does regime_vol_zscore appear in top-10 SHAP for
   XRP? If yes: XRP is BTC-class. If no: XRP is ETH/SOL-class.

## Observations

- **Researcher compliance: partial.** Previous directive prioritized BTC PBO/CPCV as iter 39
  (MANDATORY). The researcher instead ran SOL purge_period 24→12 as iter 39, continuing
  optimization. The SOL iter itself was correct and produced a valid KEEP (Brier 0.189372).
  However, the validation gate was not executed. The researcher correctly identified the
  purge_period skip logic in the ack note, which was good autonomous reasoning. The non-compliance
  on the validation gate is the key deviation.

- **KEEP rates by category (all 39 iterations):**
  - Baseline / pipeline corrections: 2/2 (100%)
  - Asset baselines (new asset first run): 3/3 (100%) — BTC iter 7, ETH iter 23, SOL iter 37
  - KEEP-VERIFIED runs: 2/2 (100%) — BTC iters 8, 14
  - train_bars extension: 4/4 (100%) — iters 8, 18, 25, 38; single most reliable lever, zero failures
  - purge_period tuning: 3/5 (60%) — BTC iter 22 KEEP (24), ETH iter 29 KEEP (12), SOL iter 39 KEEP (12)
  - drawdown_penalty_weight: 1/1 (100%) — ETH iter 32 (marginal)
  - Alpha features — regime/liquidation (BTC): 2/3 (67%)
  - Alpha features — funding (BTC + ETH): 0/3 (0%)
  - time_pcts adjustment: 1/5 (20%) — only [0.30,0.50,0.80] KEEP; all expansions DISCARD
  - HPO range narrowing: 0/5 (0%) — permanent blacklist, wall-clock binding
  - Regime config window changes: 0/2 (0%)
  - Feature pruning (manual): 0/2 (0%)
  - Interaction features: 0/1 (0%) — iter 6, +41% Brier regression
  - n_splits changes (any direction): 0/4 (0%) — n_splits=8 confirmed optimal
  - embargo_period tuning: 0/2 (0%)
  - Objective / gate experiments (BTC): 0/4 (0%) — hard floor locked
  - **Overall: 18 KEEP/KEEP-VERIFIED out of 39 = 46.2%**

- **SOL is now 3/3 KEEP.** All three SOL experiments have been KEEPs (baseline, train_bars, purge_
  period). This is consistent with the early phase of the program (BTC opened 3/4 KEEP before the
  optimization landscape hardened). SOL Brier trajectory: 0.193016 → 0.189379 → 0.189372.
  The last delta (0.007 Brier reduction in iter 39) signals approaching floor. Expected SOL floor:
  0.187-0.189 based on ETH analog trajectory.

- **SOL best_params max_depth ceiling alert — confirmed across 2 consecutive KEEPs.** Both iter
  38 and iter 39 report best_params: lr=0.023, max_depth=6, num_leaves=72, reg_alpha=0.016,
  reg_lambda=8e-6. max_depth=6 at the upper bound of [2,6] in 2/2 SOL KEEPs crosses the threshold
  for action. This is the strongest HPO convergence signal in the program to date.

- **BTC remains at confirmed hard floor.** Best Brier 0.101759 (iter 22), unchanged across
  17 experiments (iters 23-39). BTC is exhausted.

- **ETH remains at confirmed hard floor.** Best Brier 0.177772 (iter 32). ETH is exhausted.

- **Validation gate remains entirely open.** After 39 iterations across 3 assets, PBO and
  Deflated Sharpe have not been measured once. BTC has 22 config experiments — the highest
  combinatorial overfitting exposure in the program. The OOS Brier, ECE, PnL, and drawdown metrics
  all pass the acceptance thresholds by static measurement, but overfitting bias cannot be quantified
  without PBO. This is the single largest risk to the program's validity.

- **Both-sides strategy summary (updated through iter 39):**
  - BTC: bs_pnl $584K, bs_sharpe 93.84. Single-side sharpe 109.25. Single-side risk-adjusted superior.
  - ETH: bs_pnl $14.07M, bs_sharpe 267.08. Single-side sharpe 264.56. Both-sides marginally superior
    on risk-adjusted basis, dramatically higher absolute PnL. ETH is the primary market-making asset.
  - SOL: bs_pnl $13.75M, bs_sharpe 251.55. Single-side sharpe 251.86. Nearly equal risk-adjusted.
    SOL both-sides absolute PnL $0.32M below ETH.
  - Pattern: ETH > SOL >> BTC for both-sides absolute PnL. BTC best for directional single-side.
    ETH/SOL optimal for both-sides market-making. This pattern is stable across all iterations.

- **HPO starvation status.** At n_splits=8 with train_bars=14000 (SOL current config), HPO budget
  allows 33-34 trials (SOL iter 38: 33 trials, iter 39: 34 trials). Target is 40. Structural
  starvation is mild (85% of target). This is the ceiling until a builder-level parallelism change
  is made. No config knob can resolve this without reducing train_bars or n_splits — both are
  blacklisted for regression.

## Blacklist

- **Interaction features (all 8 pairs):** iter 6 DISCARD, +41% Brier regression. Permanent all assets.
- **Funding features in cached_features for BTC:** iter 2 DISCARD, absent from top-10 SHAP. Permanent.
- **Funding features in cached_features for ETH:** iter 27 DISCARD, absent from top-10 SHAP. Permanent.
- **HPO range narrowing (all configurations):** iters 10, 13, 15, 19, 20 — 0/5 KEEP. Wall-clock binding.
  Permanent blacklist all assets.
- **time_pcts expansion beyond 3 points (any direction):** iters 12, 21, 28 — 0/3 KEEP. [0.30,0.50,0.80]
  confirmed optimal for BTC and ETH. Do not add time points for SOL or XRP.
- **time_pct 0.10 (early-bar sampling):** iter 21, +63% Brier regression. Permanent all assets.
- **embargo_period tuning (both directions from 6):** iters 9, 30 — 0/2 KEEP. embargo_period=6 confirmed.
- **n_splits above 8:** iter 11 DISCARD, HPO starvation worsens.
- **n_splits below 8 (to 6):** iters 31, 33 — 0/2 KEEP. n_splits=8 is optimal. Permanent.
- **regime_params window changes for BTC (120→240):** iter 17 DISCARD. Permanent for BTC.
- **regime_params window changes for ETH (120→60):** iter 26 DISCARD. Permanent for ETH.
- **Manual feature pruning from cached_features:** iters 16, 24 — 0/2 KEEP. Permanent.
- **train_bars above 10000 for BTC:** saturation confirmed at 10000. BTC ceiling.
- **train_bars above 14000 for ETH:** marginal plateau confirmed. ETH ceiling.
- **BTC objective gate experiments (any form):** iters 33-36 — 0/4 KEEP, floor locked. Permanent BTC.
- **regime_params window changes for SOL:** skip experiment (regime_vol_zscore absent from top-10 SHAP,
  same as ETH pattern — iter 26 evidence generalizes). Do not test window changes for SOL.
- **XRP expansion before PBO/CPCV validation of BTC, ETH, SOL:** auditor ESCALATE directive outstanding.
  Do not start XRP baseline until iters 40-42 confirm PBO < 0.40 for all three assets.

## HPO Range Recommendations

- `max_depth`: **RAISE CEILING from 6 to 8 for SOL (iter 45).** Evidence: max_depth=6 at upper bound
  in 2/2 consecutive SOL KEEPs (iters 38, 39 — both report max_depth=6 in best_params). Two-
  observation threshold met. Action: in iter 45, change hpo_search_space max_depth from [2,6] to
  [2,8]. Scope: SOL only. Do not change for BTC or ETH (both at confirmed floors where this
  parameter is already optimized).
- `learning_rate`: no change. SOL lr=0.023 is mid-range within [0.005, 0.1]. No ceiling pressure.
- `num_leaves`: no change. SOL num_leaves=72 is mid-range [16, 128].
- `reg_alpha`: no change. SOL reg_alpha=0.016 is in lower region but not at floor.
- `reg_lambda`: monitor only. SOL reg_lambda=8e-6 appears in 2/2 KEEPs near the lower bound
  [1e-8, 10.0]. If one more SOL KEEP confirms reg_lambda < 1e-4, narrow upper region to [1e-8, 0.01]
  to reduce search waste. Do not act yet.
- `n_estimators`, `subsample`, `colsample_bytree`, `min_child_samples`: maintain current ranges.
- **Researcher action item (standing):** report best_params (lr, max_depth, num_leaves, reg_alpha,
  reg_lambda) in description field for all future KEEP rows. Iters 38 and 39 provide the first two
  data points and have already triggered a max_depth ceiling action.

## Cross-Asset Status Summary

| Asset | Best Brier | Best bs_sharpe | Opt Iters   | Config Status              | PBO Status   |
|-------|-----------|----------------|-------------|----------------------------|--------------|
| BTC   | 0.101759  | 93.84          | 22 (7-36)   | Exhausted — hard floor     | NOT MEASURED |
| ETH   | 0.177772  | 267.08         | 9 (23-32)   | Exhausted — hard floor     | NOT MEASURED |
| SOL   | 0.189372  | 251.55         | 3 (37-39)   | Active — ETH-class, paused | NOT MEASURED |
| XRP   | —         | —              | 0           | BLOCKED — PBO gate open    | N/A          |

## Validation Gate (ESCALATED — mandatory before SOL continuation or XRP)

| Metric          | Required  | BTC Status          | ETH Status          | SOL Status          |
|-----------------|-----------|---------------------|---------------------|---------------------|
| OOS Brier       | < 0.25    | 0.101759 PASS       | 0.177772 PASS       | 0.189372 PASS       |
| OOS ECE         | < 0.05    | 0.0088 PASS         | 0.0252 PASS         | 0.0135 PASS         |
| Net PnL         | > 0       | $45.55 PASS         | $176.50 PASS        | $172.13 PASS        |
| Max drawdown    | < 30%     | 13.61% PASS         | 1.75% PASS          | 1.62% PASS          |
| PBO             | < 0.40    | NOT MEASURED        | NOT MEASURED        | NOT MEASURED        |
| Deflated Sharpe | > 0.0     | NOT MEASURED        | NOT MEASURED        | NOT MEASURED        |

The four static metrics pass for all three active assets. PBO and Deflated Sharpe are the critical
unmeasured risks. Until these are measured, the program cannot confirm that its Brier improvements
represent genuine generalization rather than combinatorial overfitting across the HPO search.
Execute iters 40-42 (BTC, ETH, SOL validation runs) before any further optimization or expansion.
