# Strategy Directive
Updated: 2026-03-20T09:15:00Z
After iteration: 38

## Priority Queue

### ESCALATION RESPONSE: PBO/CPCV Validation Gate (iters 39-41)

The auditor has issued a mandatory ESCALATE directive requiring PBO/CPCV validation for BTC and ETH before XRP expansion. This directive supersedes the SOL optimization queue. The researcher must execute validation runs in mode=verify with CPCV enabled before any new asset is added.

1. **[iter 39 — MANDATORY] BTC PBO/CPCV validation run.** Run the BTC best-config model (train_bars=10000, purge_period=24, n_splits=8, time_pcts=[0.30,0.50,0.80], 22 features) with CPCV enabled to measure PBO. Required: PBO < 0.40 and Deflated Sharpe > 0.0 to pass. Log results as KEEP if both thresholds pass, DISCARD if either fails. Record in description: (a) PBO value, (b) Deflated Sharpe value, (c) number of CPCV paths used, (d) whether the walk-forward OOS Brier is stable across paths (variance measure). This is a mode=verify run — do not change any knobs. If PBO >= 0.40, halt XRP expansion entirely and escalate to auditor for structural review.

2. **[iter 40 — MANDATORY] ETH PBO/CPCV validation run.** Same protocol as iter 39 applied to ETH best-config (train_bars=14000, purge_period=12, n_splits=8, drawdown_penalty_weight=10.0). ETH has only 9 optimization iterations vs BTC's 22, making combinatorial overfitting risk lower — but the mandatory gate still applies. Record same fields: PBO, Deflated Sharpe, CPCV path count, Brier stability variance. Both BTC and ETH PBO must be confirmed < 0.40 before XRP baseline is started.

3. **[iter 41] SOL PBO/CPCV validation run** (concurrent with BTC/ETH validation — execute after iter 40 if auditor clears BTC/ETH). SOL is at iter 2 with 2 optimization steps, making its overfitting risk minimal, but completing the validation sweep across all three active assets is operationally clean. Use SOL best-config (train_bars=14000, purge_period=24, n_splits=8). Note: if BTC or ETH fail PBO validation, do not run XRP and do not continue SOL optimization — escalate to auditor instead.

### SOL Optimization Queue (iters 42-47, conditional on validation pass)

These execute only after all three PBO/CPCV validation runs complete and pass. SOL is confirmed ETH-class (Brier 0.189379, tick features dominate, regime_vol_zscore absent from top-10 SHAP) — use ETH-pattern priority sequence.

4. **[iter 42] SOL purge_period 24→12.** ETH optimal was purge_period=12 (iter 29, KEEP). SOL's ETH-class profile (tick-dominant, regime-absent) suggests the ETH purge period will generalize. BTC optimal was purge_period=24. Testing purge_period=12 resolves whether SOL is ETH-like in walk-forward structure as well as feature importance. Expected outcome: KEEP based on ETH pattern. If DISCARD: SOL optimal purge_period=24, move directly to iter 43.

5. **[iter 43] SOL drawdown_penalty_weight 5.0→10.0.** ETH iter 32 produced a marginal KEEP (0.000001 Brier improvement). With SOL's higher volatility (wider intra-bar swings), the drawdown constraint is more likely to be binding, making a weight increase more impactful than it was for ETH. Low risk of regression. Run after purge_period is resolved to avoid confounding.

6. **[iter 44] SOL funding features in cached_features** (6 features: funding_rate, funding_rate_sma3, funding_rate_pctile, funding_rate_direction, funding_cumulative_24h, funding_hours_since). Funding was DISCARD for both BTC (iter 2) and ETH (iter 27). However, SOL perpetual funding rates are historically more volatile and exhibit more frequent sign changes than BTC/ETH — the hypothesis is that funding captures SOL-specific leveraged positioning dynamics not visible in tick data. This is a low-prior but non-negligible test. If funding features appear in top-10 SHAP after adding them: record as high-value evidence and carry forward. If absent from top-10 SHAP (as with BTC/ETH): DISCARD and add to permanent blacklist.

7. **[iter 45] SOL regime_params vol_window/lookback_window 120→60.** Only run this if SOL SHAP analysis from iter 37-38 ever showed regime features entering top-10 (current ack confirms regime_vol_zscore absent). This experiment is listed for completeness but is low priority given the ETH-class SHAP profile. If regime features remain absent, skip this entirely and move to iter 46.

8. **[iter 46] SOL objective.primary "brier"→"sharpe".** BTC and ETH both hit hard Brier floors where no config change pierced the floor after it locked in. SOL Brier trajectory (0.193016→0.189379 across 2 iters) is still declining — the floor has not locked yet. However, testing Sharpe-primary before the floor locks may pre-empt the lock-in. Run this only if iters 42-45 fail to produce a strict Brier improvement — i.e., if SOL reaches 3 consecutive identical Brier readings, switch objective and check if it unlocks the landscape.

9. **[iter 47] Asset rotation: XRP baseline.** After all three PBO/CPCV validations pass and SOL has completed at minimum 6 optimization iterations (iters 42-47), rotate to XRP. XRP starting config: BTC-optimal knobs.json (train_bars=10000, n_splits=8, purge_period=24, time_pcts=[0.30,0.50,0.80]). XRP expected Brier range: 0.18-0.25 given payment-utility microstructure (less speculative momentum, lower intra-bar vol). Record whether regime_vol_zscore appears in top-10 SHAP for XRP — this is the primary asset profiling diagnostic.

## Observations

- **KEEP rates by category (all 38 iterations):**
  - Baseline / pipeline corrections: 2/2 (100%)
  - Asset baselines (new asset first run): 3/3 (100%) — BTC iter 7, ETH iter 23, SOL iter 37
  - KEEP-VERIFIED runs: 2/2 (100%) — BTC iter 8, iter 14
  - train_bars extension: 4/4 (100%) — iters 8, 18, 25, 38; the single most reliable lever in the program, zero failures
  - purge_period tuning: 2/4 (50%) — BTC iter 22 KEEP (24), ETH iter 29 KEEP (12)
  - drawdown_penalty_weight adjustment: 1/1 (100%) — ETH iter 32 (marginal)
  - Alpha features — regime/liquidation for BTC: 2/3 (67%)
  - Alpha features — ETH/funding for BTC+ETH: 0/3 (0%)
  - time_pcts adjustment: 1/5 (20%) — only [0.30,0.50,0.80] KEEP; all expansions DISCARD
  - HPO range narrowing: 0/5 (0%) — permanent blacklist, wall-clock is binding not range
  - Regime config window changes: 0/2 (0%) — BTC iter 17, ETH iter 26
  - Feature pruning (manual): 0/2 (0%) — iters 16, 24
  - Interaction features: 0/1 (0%) — iter 6, +41% Brier regression
  - n_splits changes (any direction): 0/4 (0%) — iters 11, 31, 33 and n_splits=8 confirmed optimal
  - embargo_period tuning: 0/2 (0%) — iters 9, 30
  - Objective / gate tightening (BTC): 0/4 (0%) — iters 33-36, floor locked
  - **Overall: 17 KEEP/KEEP-VERIFIED out of 38 = 44.7%**

- **SOL confirmed ETH-class profile.** SOL Brier 0.189379 falls in [0.15, 0.20] ETH-class range. Regime_vol_zscore absent from top-10 SHAP (confirmed by researcher ack). Tick features dominate: partial_bar_position, partial_range, trade_intensity. This mirrors ETH's SHAP profile exactly. Practical implication: SOL optimization should follow ETH's priority sequence (purge_period → drawdown_penalty → funding test), not BTC's. Expected SOL Brier floor: 0.175-0.185 based on ETH analog (ETH floor 0.177772 at 14000 train_bars).

- **SOL train_bars saturation curve:** iter 37 baseline (10000 bars) Brier 0.193016, iter 38 (14000 bars) Brier 0.189379 — 1.97% improvement. This is below the 2% threshold for mandatory verification, confirming the gain is marginal. Consistent with ETH pattern: ETH iter 25 (10000→14000) produced marginal improvement + bs_sharpe record. SOL bs_sharpe = 251.55 (iter 38), within range of ETH's 267.08 but below ETH peak. SOL may have fewer both-sides market-making opportunities due to lower intra-bar microstructure predictability.

- **First convergence data for HPO best_params (from iter 38 description):** lr=0.023, max_depth=6, num_leaves=72, reg_alpha=0.016, reg_lambda=8e-6. Critical finding: max_depth=6 is at the ceiling of the search range [2,6]. If this pattern holds across 2+ more SOL KEEP iterations, raise the upper bound to max_depth=8. num_leaves=72 is mid-range [16,128]. reg_lambda=8e-6 is near the lower bound [1e-8, 10.0], suggesting no strong L2 regularization benefit at this data size.

- **Mandatory validation gate status: OPEN for all assets.** After 38 iterations and 3 assets, neither PBO nor Deflated Sharpe has been measured for any asset. Auditor ESCALATE is justified — the program has completed optimization without measuring the primary overfitting protection criteria. BTC has 22 config experiments alone; its PBO exposure is the highest in the program.

- **BTC remains at confirmed hard floor.** Best Brier 0.101759 (iter 22) unchanged across 16 experiments (iters 23-38). Zero strict improvements since purge_period=24 was set. All objective and gate experiments (iters 33-36) produced identical results, confirming model capacity ceiling not search stagnation.

- **ETH remains at confirmed hard floor.** Best Brier 0.177772 (iter 32). Improvement slope was 0.000471 total across 9 iterations (< 0.3%). Tick features dominate across all ETH runs.

- **Researcher compliance: full.** Researcher followed iter 36 strategy directive precisely — SOL baseline (iter 37) and train_bars extension (iter 38) were executed in order. Researcher ack correctly identifies purge_period 24→12 as the next SOL priority and notes regime_vol_zscore absent from SHAP. The only deviation is the validation gate not yet having been run — this is the auditor escalation driver, not a researcher error.

- **Both-sides strategy summary across all assets:**
  - BTC: bs_pnl $584K, bs_sharpe 93.84. Single-side sharpe 109.25 — single-side is risk-adjusted superior.
  - ETH: bs_pnl $14.07M, bs_sharpe 267.08. Single-side sharpe 264.56 — both-sides marginally superior and dramatically higher absolute PnL. ETH is the primary market-making asset.
  - SOL: bs_pnl $13.75M, bs_sharpe 251.55. Single-side sharpe 251.86 — nearly equal on risk-adjusted basis. SOL both-sides absolute PnL is $0.32M below ETH, confirming ETH dominates for market-making.
  - Pattern: ETH > SOL >> BTC for both-sides absolute PnL. Single-side risk-adjusted return is highest for BTC (sharpe 109.25), suggesting BTC is better as a directional bet and ETH/SOL as market-making assets.

- **HPO starvation is definitively not fixed.** At n_splits=8, the budget allows 24-40 trials depending on dataset size. SOL iter 38 hit 33/40 target trials — mild starvation. This is the structural ceiling until a parallelism change is made at the builder level.

## Blacklist

- **Interaction features (all 8 pairs):** iter 6 DISCARD, +41% Brier regression. Permanent for all assets.
- **Funding features in cached_features for BTC:** iter 2 DISCARD, absent from top-10 SHAP. Permanent for BTC.
- **Funding features in cached_features for ETH:** iter 27 DISCARD, absent from top-10 SHAP. Permanent for ETH.
- **HPO range narrowing (all configurations):** iters 10, 13, 15, 19, 20 — 0/5 KEEP. Wall-clock binding. Permanent blacklist for all assets.
- **time_pcts expansion beyond 3 points (any direction):** iters 12, 21, 28 — 0/3 KEEP. The set [0.30,0.50,0.80] is confirmed optimal for BTC and ETH. Do not add time points for SOL/XRP.
- **time_pct 0.10 (early-bar sampling):** iter 21, +63% Brier regression. Permanent for all assets.
- **embargo_period tuning (both directions from 6):** iters 9, 30 — 0/2 KEEP. embargo_period=6 is confirmed. Permanent.
- **n_splits above 8:** iter 11, HPO starvation. Permanent upward blacklist.
- **n_splits below 8 (to 6):** iters 31, 33 — 0/2 KEEP. n_splits=8 is confirmed optimal. Permanent downward blacklist.
- **regime_params window changes for BTC (120→240):** iter 17 DISCARD. Permanent for BTC.
- **regime_params window changes for ETH (120→60):** iter 26 DISCARD. Permanent for ETH (regime features absent regardless of window).
- **Manual feature pruning from cached_features:** iters 16, 24 — 0/2 KEEP. LightGBM internal selection outperforms manual pruning. Permanent.
- **train_bars above 10000 for BTC:** saturation confirmed at 10000. Ceiling at 10000 for BTC.
- **train_bars above 14000 for ETH:** marginal plateau confirmed. Ceiling at 14000 for ETH.
- **BTC objective gate experiments (any form):** iters 33-36, 0/4 KEEP, floor locked. Permanent for BTC.
- **XRP expansion before PBO/CPCV validation of BTC and ETH:** auditor ESCALATE directive. Do not start XRP baseline until iters 39-40 confirm PBO < 0.40 for both BTC and ETH.

## HPO Range Recommendations

- `max_depth`: **ALERT — raise ceiling from 6 to 8.** Evidence: SOL iter 38 best_params show max_depth=6, which is at the current upper bound. If the optimizer is selecting the ceiling value, the true optimum may lie above 6. This is the first convergence data point, so a single observation is insufficient to act — collect max_depth from 2 more SOL KEEP iterations. If max_depth=6 appears in 3/3 SOL KEEPs, raise upper bound to 8 for SOL. Do not raise for BTC/ETH as they are at confirmed floors.
- `learning_rate`: no change. SOL iter 38 lr=0.023 is within [0.005, 0.1] with no ceiling pressure. Maintain [0.005, 0.1].
- `num_leaves`: no change. SOL iter 38 num_leaves=72 is mid-range [16, 128]. No ceiling pressure.
- `reg_alpha`: no change. SOL iter 38 reg_alpha=0.016 — near lower region but not at the floor. Maintain [1e-8, 10.0].
- `reg_lambda`: **monitor.** SOL iter 38 reg_lambda=8e-6 is near the lower bound [1e-8, 10.0]. This suggests near-zero L2 regularization is optimal. If 3+ SOL KEEPs confirm reg_lambda < 1e-4, narrow the lower region to [1e-8, 0.01] to reduce search waste in the high-lambda region.
- `n_estimators`: maintain [100, 1500]. No convergence data.
- `min_child_samples`: maintain [100, 1000]. Lower bound of 100 is a hard floor.
- `subsample`: maintain [0.6, 0.9].
- `colsample_bytree`: maintain [0.4, 0.8].
- **Researcher action item:** report best_params (learning_rate, max_depth, num_leaves, reg_alpha, reg_lambda) in description field for all future KEEP rows. Iter 38 provides the first data point. Two more SOL KEEP observations are needed before any range adjustment is warranted.

## Cross-Asset Status Summary

| Asset | Best Brier | Best bs_sharpe | Opt Iters | Config Status              | PBO Status   |
|-------|-----------|---------------|-----------|----------------------------|--------------|
| BTC   | 0.101759  | 93.84         | 22 (7-36) | Exhausted — hard floor     | NOT MEASURED |
| ETH   | 0.177772  | 267.08        | 9 (23-32) | Exhausted — hard floor     | NOT MEASURED |
| SOL   | 0.189379  | 251.55        | 2 (37-38) | Active — ETH-class profile | NOT MEASURED |
| XRP   | —         | —             | 0         | BLOCKED — PBO gate open    | N/A          |

## Validation Gate (ESCALATED — mandatory before XRP)

| Metric          | Required  | BTC Status          | ETH Status          | SOL Status          |
|-----------------|-----------|---------------------|---------------------|---------------------|
| OOS Brier       | < 0.25    | 0.101759 PASS       | 0.177772 PASS       | 0.189379 PASS       |
| OOS ECE         | < 0.05    | 0.0088 PASS         | 0.0252 PASS         | 0.0135 PASS         |
| Net PnL         | > 0       | $45.55 PASS         | $176.50 PASS        | $172.13 PASS        |
| Max drawdown    | < 30%     | 13.61% PASS         | 1.75% PASS          | 1.62% PASS          |
| PBO             | < 0.40    | NOT MEASURED        | NOT MEASURED        | NOT MEASURED        |
| Deflated Sharpe | > 0.0     | NOT MEASURED        | NOT MEASURED        | NOT MEASURED        |

The four measured metrics pass for all three active assets. PBO and Deflated Sharpe are unmeasured after 38 iterations and represent the critical outstanding validation risk. BTC has 22 config experiments — the highest combinatorial overfitting exposure in the program. The auditor ESCALATE directive is appropriate and must be executed before any further asset expansion.
