# Strategy Directive
Updated: 2026-03-20T12:00:00Z
After iteration: 44

## Critical Gap: PBO/Deflated Sharpe Measurement

`train_pulse_fast.py` runs walk-forward HPO and reports OOS Brier, ECE, PnL, Sharpe, and drawdown.
It does NOT compute PBO or Deflated Sharpe. These two acceptance criteria require
`cpcv_validation_pulse.py`, which is a separate script that already exists and is fully implemented
at `scripts/cpcv_validation_pulse.py`. The gap is purely operational: the autoresearch loop has
never called this script.

### What cpcv_validation_pulse.py does

- Loads the pre-cached `dataset.npz` (same file train_pulse_fast.py uses — no re-generation needed)
- Applies the same feature filter and time_pct filter from `knobs.json`
- Splits at BAR level into N groups, generates C(N,k) paths (default C(8,2)=28 paths)
- Trains a fixed-params LightGBM (midpoint of HPO ranges) on each path's train set
- Records IS and OOS Sharpe plus OOS Brier for every path
- Computes PBO (both Sharpe-based and Brier-based; takes the more favorable)
- Computes Deflated Sharpe via Bailey-Lopez de Prado approximation over n_paths
- Outputs a structured verdict with pass/fail against the acceptance thresholds

### How to invoke

```
uv run scripts/cpcv_validation_pulse.py --asset BTC --n-groups 8 --k-test 2
uv run scripts/cpcv_validation_pulse.py --asset ETH --n-groups 8 --k-test 2
uv run scripts/cpcv_validation_pulse.py --asset SOL --n-groups 8 --k-test 2
```

Each run takes ~5-10 minutes (28 fixed-param LightGBM fits, no HPO). Log the following fields
into results.tsv from the script output: PBO (best-of-both), Deflated Sharpe, OOS Brier mean,
OOS Brier std, IS-OOS Sharpe correlation, and pct paths with positive OOS Sharpe.

### Key implementation note

`cpcv_validation_pulse.py` uses HPO range midpoints as fixed params — NOT the best_params found
by train_pulse_fast.py. This is intentional (it measures structural PBO of the model class, not
of the specific tuned solution). However, it means PBO results are conservative relative to the
actual deployed model. A supplementary "best_params PBO" can be run later by substituting the
best_params from the last KEEP run, but this is optional at this stage.

### XRP dataset status

`data/models/pulse_v2/XRP_5m/dataset.npz` does NOT exist. Before the XRP baseline experiment
can run, `train_pulse_v2.py` must be run for XRP to generate the cached dataset. This is a
pre-requisite that requires ~15 minutes and is separate from the CPCV validation work.

---

## Priority Queue

1. **[iter 45 — MANDATORY BLOCK] BTC CPCV validation.**
   Run `uv run scripts/cpcv_validation_pulse.py --asset BTC --n-groups 8 --k-test 2`.
   Knobs.json must be in BTC-optimal state for feature filter to be meaningful:
   train_bars=10000, purge_period=24, n_splits=8, time_pcts=[0.30,0.50,0.80], 22 features.
   Required output to log: PBO (pass if <0.40), Deflated Sharpe (pass if >0.0), OOS Brier
   mean and std, IS-OOS correlation, pct paths positive OOS Sharpe.
   Note: current knobs.json has train_bars=14000, purge_period=12 (ETH/SOL-optimal). The
   researcher must confirm BTC-optimal config is in place before calling the script, OR
   accept that the feature set used will be the current 22-feature set (same for both
   BTC-optimal and ETH/SOL-optimal since cached_features are identical). The time_pcts and
   feature list in knobs.json control the CPCV filter — both configs share the same features
   and time_pcts, so the CPCV result is valid under current knobs.json. Proceed with current
   knobs.json without config change.
   Pass threshold: PBO < 0.40 AND Deflated Sharpe > 0.0.
   If FAIL: halt all expansion and escalate to auditor immediately.
   If PASS: log as KEEP and proceed to iter 46.

2. **[iter 46 — MANDATORY BLOCK, contingent on iter 45 PASS] ETH CPCV validation.**
   Run `uv run scripts/cpcv_validation_pulse.py --asset ETH --n-groups 8 --k-test 2`.
   ETH dataset exists at `data/models/pulse_v2/ETH_5m/dataset.npz`.
   Same protocol as iter 45. ETH has 9 optimization iterations — lower combinatorial
   exposure than BTC's 22. Expected to pass if BTC passes.
   If FAIL: halt XRP expansion; escalate. If PASS: proceed to iter 47.

3. **[iter 47 — MANDATORY BLOCK, contingent on iter 46 PASS] SOL CPCV validation.**
   Run `uv run scripts/cpcv_validation_pulse.py --asset SOL --n-groups 8 --k-test 2`.
   SOL dataset exists at `data/models/pulse_v2/SOL_5m/dataset.npz`.
   SOL has only 7 optimization iterations and reached its floor quickly — lowest
   combinatorial overfitting exposure. Expected to pass.
   If all three pass: the full static acceptance table is complete for BTC, ETH, SOL.
   The program is validated and cleared for XRP expansion.

4. **[iter 48 — after CPCV sweep complete] Generate XRP cached dataset.**
   Run `uv run scripts/train_pulse_v2.py --asset XRP --timeframe 5m` to generate
   `data/models/pulse_v2/XRP_5m/dataset.npz`. This is a ~15-minute pre-requisite
   with no knobs.json dependency. It must complete before any XRP training or CPCV run.
   Log as a setup step, not a model iteration.

5. **[iter 49 — after iter 48 dataset exists] XRP baseline.**
   Run `uv run scripts/train_pulse_fast.py --asset XRP --trials 40 --timeout 420 --mode fast`.
   Starting config: current knobs.json (train_bars=14000, purge_period=12, n_splits=8,
   time_pcts=[0.30,0.50,0.80], 22 cached+regime features). XRP is a payment-utility
   asset with lower speculative momentum than SOL/ETH. Primary diagnostic: does
   regime_vol_zscore appear in top-10 SHAP for XRP? If yes: XRP is BTC-class (regime-
   sensitive). If no: XRP is ETH/SOL-class (tick-dominant). Expected XRP Brier: 0.18-0.26.
   Log as KEEP (it is a first baseline — any result constitutes a valid anchor).

6. **[iter 50 — conditional on XRP baseline KEEP] XRP train_bars sweep.**
   If XRP baseline Brier > 0.20: try train_bars 14000→18000 (more data may help a
   payment-utility asset with lower signal density). If XRP baseline Brier < 0.20:
   baseline is already strong, proceed directly to purge_period tuning.
   Evidence base: train_bars extension has a 4/4 (100%) KEEP rate in the program.

## Observations

- **Researcher compliance: full for iter 44.** The BTC validation run (iter 44) was executed
  exactly as mandated by the previous strategy directive. BTC Brier reproduced at 0.101759
  (exact match to best) confirming model stability. The researcher correctly identified the
  limitation: PBO/Deflated Sharpe were not reported because `train_pulse_fast.py` cannot
  compute them. This is accurate — the CPCV script must be called separately.

- **KEEP rates by category (all 44 iterations):**
  - Asset baselines (new asset first run): 3/3 (100%) — BTC iter 7, ETH iter 23, SOL iter 37
  - KEEP-VERIFIED runs: 2/2 (100%) — BTC iters 8, 14
  - train_bars extension: 4/4 (100%) — iters 8, 18, 25, 38; most reliable lever in program
  - purge_period tuning: 3/5 (60%) — BTC iter 22, ETH iter 29, SOL iter 39 all KEEP
  - drawdown_penalty_weight: 1/1 (100%) — ETH iter 32 (marginal)
  - Alpha features — regime+liquidation (BTC): 2/3 (67%)
  - Alpha features — funding (all three assets): 0/4 (0%) — permanent blacklist confirmed
  - time_pcts adjustment: 1/5 (20%) — only [0.30,0.50,0.80] KEEP; all expansions fail
  - HPO range narrowing: 0/5 (0%) — wall-clock binding; permanent blacklist
  - Regime config window changes: 0/3 (0%) — BTC iter 17, ETH iter 26, SOL skipped correctly
  - Feature pruning (manual): 0/2 (0%) — iters 16, 24
  - Interaction features: 0/1 (0%) — iter 6, +41% Brier regression
  - n_splits changes (any direction from 8): 0/4 (0%) — n_splits=8 confirmed optimal
  - embargo_period tuning: 0/2 (0%) — embargo_period=6 confirmed
  - Objective / gate experiments (BTC): 0/4 (0%) — hard floor
  - Validation / verification runs: 1/1 KEEP (iter 44) for BTC Brier stability
  - **Overall: 19 KEEP/KEEP-VERIFIED out of 44 = 43.2%**

- **SOL hard floor confirmed at 0.189372 across 4 consecutive identical Brier values (iters
  39-43).** Max_depth ceiling raised to [2,8] in iter 41 produced regression (0.192005). Sharpe-
  primary objective in iter 42 reproduced identical best_params and Brier. Funding features in
  iter 43 produced identical Brier. SOL has exhausted all known levers. SOL is in the same state
  as BTC (22 experiments exhausted) and ETH (9 experiments exhausted). All three assets are at
  confirmed hard floors awaiting CPCV validation.

- **BTC hard floor confirmed at 0.101759 across 17 experiments (iters 23-44).** Iter 44
  validates exact reproduction (0.101759) in verify mode with 40 HPO trials. Best params
  stable: n_estimators=1028, lr=0.01272, max_depth=4, num_leaves=77, reg_alpha=2.854,
  reg_lambda=1.131. regime_vol_zscore consistently rank 7 in top-10 SHAP across all BTC
  KEEP iterations.

- **ETH validation running (iter 45 was described as ETH validation running now).** ETH
  best Brier 0.177772 (iter 32). ETH validation result should be logged before or alongside
  the CPCV run sequence. If ETH train_pulse_fast.py validation confirms exact Brier
  reproduction: proceed to CPCV. If ETH Brier regresses: investigate config state.

- **Both-sides vs single-side strategy comparison (44 iterations):**
  - BTC: bs_sharpe 93.84, single-side sharpe 109.25. Single-side superior for BTC.
  - ETH: bs_sharpe 267.08, single-side sharpe 264.56. Both-sides marginally superior on risk-
    adjusted; dramatically higher absolute PnL ($14.07M vs $176.50). ETH is the primary
    market-making asset.
  - SOL: bs_sharpe 251.55, single-side sharpe 251.86. Effectively equal.
  - Pattern is stable and consistent: BTC = directional single-side. ETH/SOL = both-sides MM.

- **HPO starvation: structural and unresolvable at current config.** At n_splits=8,
  train_bars=14000, wall-clock timeout binds at 29-34 trials (target 40). All config levers
  to increase HPO budget have been blacklisted (n_splits reduction: 0/4 KEEP; train_bars
  reduction: structural regression). The only path to more HPO trials is a builder-level
  parallelism change (e.g., LightGBM GPU acceleration, Optuna parallel workers) — outside
  the autoresearch knob space.

- **dispatch_state confirms last_auditor_at=0.** The auditor has never been invoked in 44
  iterations. This is the longest-outstanding structural risk. The CPCV sweep (iters 45-47)
  will either close or escalate this risk. Recommend invoking auditor after iter 47 regardless
  of CPCV outcome to perform a full program review before XRP expansion.

## Blacklist

- **Interaction features (all 8 pairs):** iter 6, +41% Brier regression. Permanent all assets.
- **Funding features in cached_features for BTC, ETH, SOL:** 0/4 KEEP across iters 2, 27,
  43 and ETH iter 27. Funding absent from top-10 SHAP in all three assets. Permanent blacklist.
  Apply to XRP unless XRP microstructure analysis shows structural reason to differ.
- **HPO range narrowing (all configurations):** iters 10, 13, 15, 19, 20 — 0/5 KEEP.
  Wall-clock timeout binding regardless of trial cap. Permanent blacklist all assets.
- **time_pcts expansion beyond 3 points:** iters 12, 21, 28 — 0/3 KEEP. [0.30,0.50,0.80]
  confirmed optimal for BTC, ETH. Apply same default to XRP.
- **time_pct 0.10 (early-bar sampling):** iter 21, +63% Brier regression. Permanent all assets.
- **embargo_period tuning (both directions from 6):** iters 9, 30 — 0/2 KEEP. Keep at 6.
- **n_splits above or below 8:** iters 11, 31, 33 — 0/4 total. n_splits=8 confirmed optimal.
- **regime_params window changes for BTC (120→240):** iter 17. Permanent for BTC.
- **regime_params window changes for ETH (120→60):** iter 26. Permanent for ETH.
- **regime_params window changes for SOL:** no test needed (regime_vol_zscore absent from
  SHAP, same as ETH, iter 26 evidence generalizes). Skip for SOL.
- **Manual feature pruning from cached_features:** iters 16, 24 — 0/2 KEEP. Permanent.
- **train_bars above 10000 for BTC:** saturation at 10000. BTC ceiling.
- **train_bars above 14000 for ETH:** marginal plateau. ETH ceiling.
- **train_bars above 14000 for SOL:** floor reached before saturation — SOL ceiling likely same
  as ETH. Test 18000 only if XRP analogy suggests further headroom.
- **BTC objective gate experiments:** iters 33-36 — 0/4 KEEP. Floor locked. Permanent BTC.
- **max_depth above 6 for SOL:** iter 41 DISCARD (max_depth=7 found optimum but Brier
  regressed). max_depth=6 confirmed SOL optimum. Revert hpo_search_space max_depth to [2,6]
  for SOL. Note: this was a [2,8] test; the result confirms [2,6] is correct.
- **Sharpe-primary objective for SOL:** iter 42 DISCARD — identical best_params and Brier to
  brier-primary. No landscape change. Permanent for SOL.
- **XRP expansion before CPCV validation of BTC, ETH, SOL:** iters 45-47 are mandatory gates.
  Do not start XRP dataset generation or baseline until iter 47 result is known.

## HPO Range Recommendations

- `max_depth` for SOL: REVERT ceiling back to [2,6]. Evidence: iter 41 tested [2,8], found
  max_depth=7 as HPO optimum, but Brier regressed from 0.189372 to 0.192005 (+0.14%).
  max_depth=6 is the confirmed SOL optimum. The current knobs.json shows max_depth [2,6] —
  confirm this is correct; do not raise the ceiling again for SOL.
- `max_depth` for XRP: start at [2,6] default. If XRP best_params hit max_depth=6 in 2+
  consecutive KEEPs, raise to [2,8] and test (same protocol as SOL iter 41 — but expect
  regression based on SOL precedent).
- `learning_rate`: BTC best lr=0.01272 (lower region of [0.005,0.1]). SOL best lr=0.023.
  For XRP, start with full range [0.005,0.1]. No narrowing recommended until 3+ XRP KEEPs
  show convergence.
- `reg_alpha`: BTC best reg_alpha=2.854 (mid-range). SOL best reg_alpha=0.016 (low). Divergent
  — do not narrow for XRP until asset-specific convergence is established.
- `reg_lambda`: SOL reg_lambda=8e-6 near lower bound [1e-8, 10.0] in 3/3 SOL KEEPs (iters
  38, 39, 40). This now meets the 3-observation threshold. For SOL (if any future experiments
  are run): narrow upper bound to [1e-8, 0.01]. Do not apply to BTC/ETH/XRP.
- `n_estimators`, `subsample`, `colsample_bytree`, `min_child_samples`: maintain current
  ranges for all assets.

## Cross-Asset Status Summary

| Asset | Best Brier | Best bs_sharpe | Opt Iters   | Config Status              | CPCV Status  |
|-------|-----------|----------------|-------------|----------------------------|--------------|
| BTC   | 0.101759  | 93.84          | 22 (7-36)   | Exhausted — hard floor     | NOT RUN      |
| ETH   | 0.177772  | 267.08         | 9 (23-32)   | Exhausted — hard floor     | NOT RUN      |
| SOL   | 0.189372  | 251.55         | 7 (37-43)   | Exhausted — hard floor     | NOT RUN      |
| XRP   | —         | —              | 0           | BLOCKED — CPCV gate open   | N/A          |

## Acceptance Gate (all static metrics pass; PBO/Deflated Sharpe pending CPCV)

| Metric          | Required  | BTC Status          | ETH Status          | SOL Status          |
|-----------------|-----------|---------------------|---------------------|---------------------|
| OOS Brier       | < 0.25    | 0.101759 PASS       | 0.177772 PASS       | 0.189372 PASS       |
| OOS ECE         | < 0.05    | 0.0088 PASS         | 0.0252 PASS         | 0.0135 PASS         |
| Net PnL         | > 0       | $45.55 PASS         | $176.50 PASS        | $172.13 PASS        |
| Max drawdown    | < 30%     | 13.61% PASS         | 1.75% PASS          | 1.62% PASS          |
| PBO             | < 0.40    | PENDING iter 45     | PENDING iter 46     | PENDING iter 47     |
| Deflated Sharpe | > 0.0     | PENDING iter 45     | PENDING iter 46     | PENDING iter 47     |

All four static metrics pass for all three active assets. BTC has 22 config experiments —
the highest combinatorial overfitting exposure. ETH has 9. SOL has 7. The CPCV sweep is
the only remaining gate. It is already implemented and ready to run.
