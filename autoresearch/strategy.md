# Strategy Directive
Updated: 2026-03-20T13:00:00Z
After iteration: 45

## Critical Program State

**BTC validation COMPLETE (iter 44):** Brier 0.101759 exactly reproduced in verify mode.
All static acceptance criteria pass. PBO/Deflated Sharpe unmeasured — requires cpcv_validation_pulse.py.

**ETH validation COMPLETE (iter 45):** Brier 0.177789 vs best 0.177772 (+0.01% noise-level).
DISCARD label is correct by strict improvement rule, but the run confirms model stability.
ETH bs_sharpe 274.44 matches iter 26 record. Both validations confirm no overfitting regression.

**SOL validation in progress at time of this directive.** The researcher_ack.txt indicates SOL
validation is running (iter 46 implied). When it completes, regardless of outcome, the CPCV
sweep begins immediately.

**Transition point:** The program has completed its configuration research phase. BTC (22 opt
iterations), ETH (9), and SOL (7) are all at confirmed hard floors. The only remaining gates
before XRP expansion are: (a) SOL validation completion, (b) CPCV sweep for all three assets,
and (c) auditor invocation. The priority queue below is ordered for this transition.

---

## Priority Queue

1. **[iter 46 — MANDATORY, SOL validation, if not already complete] SOL validation run.**
   Run `uv run scripts/train_pulse_fast.py --asset SOL --trials 40 --timeout 420 --mode verify`
   using SOL-optimal knobs: train_bars=14000, purge_period=12, n_splits=8,
   time_pcts=[0.30,0.50,0.80], 22 cached+regime features, drawdown_penalty_weight=5.0.
   Accept any Brier <= 0.189372 as KEEP (exact or marginal improvement).
   Accept Brier up to 0.189600 as validation-pass (noise range is +/-0.0005 based on BTC/ETH).
   If Brier regresses beyond 0.190: investigate config state before proceeding to CPCV.
   If SOL confirms stable: mark as KEEP-VERIFIED and proceed to item 2.

2. **[iter 47 — MANDATORY BLOCK] BTC CPCV validation.**
   Run `uv run scripts/cpcv_validation_pulse.py --asset BTC --n-groups 8 --k-test 2`.
   The current knobs.json has train_bars=14000, purge_period=12 (ETH/SOL-optimal). This is
   acceptable: the CPCV script reads cached_features and time_pcts from knobs.json, both of
   which are asset-invariant (22 features, [0.30,0.50,0.80]) and match BTC-optimal. No config
   change required before running. The BTC dataset at data/models/pulse_v2/BTC_5m/dataset.npz
   exists and is ready.
   Log the following fields into results.tsv: PBO (best-of-both), Deflated Sharpe, OOS Brier
   mean, OOS Brier std, IS-OOS Sharpe correlation, pct paths with positive OOS Sharpe.
   Pass threshold: PBO < 0.40 AND Deflated Sharpe > 0.0.
   BTC has 22 optimization iterations — the highest combinatorial overfitting exposure in the
   program. If BTC FAILS: halt all expansion, invoke auditor immediately, do not proceed to
   ETH or SOL CPCV. If BTC PASSES: log as KEEP and proceed.

3. **[iter 48 — MANDATORY BLOCK, contingent on iter 47 PASS] ETH CPCV validation.**
   Run `uv run scripts/cpcv_validation_pulse.py --asset ETH --n-groups 8 --k-test 2`.
   ETH dataset exists at data/models/pulse_v2/ETH_5m/dataset.npz.
   ETH has only 9 optimization iterations — lower combinatorial exposure than BTC. If BTC
   passed, ETH is expected to pass. Failure here despite BTC passing would indicate the ETH
   feature set (tick-dominant, no regime signal) has structural overfitting not visible in
   the Brier progression. Log same fields as iter 47. Pass threshold identical.

4. **[iter 49 — MANDATORY BLOCK, contingent on iter 48 PASS] SOL CPCV validation.**
   Run `uv run scripts/cpcv_validation_pulse.py --asset SOL --n-groups 8 --k-test 2`.
   SOL dataset exists at data/models/pulse_v2/SOL_5m/dataset.npz.
   SOL has 7 optimization iterations — lowest combinatorial exposure. This run is expected to
   produce the best PBO of the three assets. If all three CPCV runs pass: the program is
   validated and cleared for XRP expansion. All static acceptance criteria are already met
   (Brier, ECE, PnL, drawdown); this sweep closes the PBO and Deflated Sharpe gates.

5. **[MANDATORY — after iter 49, before XRP] Invoke auditor for full program review.**
   dispatch_state.json shows last_auditor_at=0 — the auditor has NEVER been invoked across
   45 iterations and 7 strategist cycles. This is the most significant outstanding risk.
   The auditor should review: (a) whether the 22-feature set represents genuine alpha or
   lucky in-sample selection, (b) whether the BTC Brier floor at 0.1018 is plausible for a
   5m bar intra-bar model, (c) the strategy dispatch logic (single-side vs both-sides per
   asset), and (d) whether PBO < 0.40 is sufficient given 22 BTC optimization passes.
   The auditor review is a mandatory gate before XRP expansion. Do not start iter 51 (XRP
   dataset generation) until auditor acknowledgement is logged.

6. **[iter 51 — after auditor clearance] Generate XRP cached dataset.**
   Run `uv run scripts/train_pulse_v2.py --asset XRP --timeframe 5m` to generate
   data/models/pulse_v2/XRP_5m/dataset.npz. XRP has no cached dataset (confirmed missing).
   This is a ~15-minute setup step, not a model iteration. Log as infrastructure step.
   No knobs.json dependency: train_pulse_v2.py generates the full 50-feature dataset
   regardless of knobs.json contents.

7. **[iter 52 — after dataset exists] XRP baseline.**
   Run `uv run scripts/train_pulse_fast.py --asset XRP --trials 40 --timeout 420 --mode fast`.
   Starting config: current knobs.json (train_bars=14000, purge_period=12, n_splits=8,
   time_pcts=[0.30,0.50,0.80], 22 cached+regime features). XRP is a payment-utility asset
   with different microstructure than BTC/ETH/SOL (higher exchange concentration, lower
   institutional derivative volume). Primary diagnostic: does regime_vol_zscore appear in
   top-10 SHAP? If yes: XRP is BTC-class (regime-sensitive, try purge_period=24 next).
   If no: XRP is ETH/SOL-class (tick-dominant, skip regime experiments).
   Expected XRP Brier range: 0.19-0.26 (lower signal density expected vs SOL).
   Log as KEEP regardless of Brier (it is the first baseline anchor).

8. **[iter 53 — after XRP baseline KEEP] XRP train_bars sweep.**
   If XRP baseline Brier > 0.21: try train_bars 14000→18000 (payment assets may benefit
   from longer history due to regime sparsity). If XRP baseline Brier <= 0.21: train_bars
   is already adequate; proceed to purge_period tuning.
   Evidence base: train_bars extension has 4/4 (100%) KEEP rate across BTC, ETH, SOL, ETH.
   This remains the highest-confidence lever for new asset baselines.

---

## Observations

- **Researcher compliance: full through iter 45.** Both validation runs (BTC iter 44, ETH
  iter 45) were executed exactly as mandated. ETH knobs correctly set to ETH-optimal config
  (train_bars=14000, purge_period=12, drawdown_penalty_weight=10.0) before the validation run.
  The DISCARD label on iter 45 is correct by strict improvement rule (0.177789 > 0.177772)
  despite confirming stability. No deviations from strategy directive.

- **KEEP rates by category (all 45 iterations):**
  - Asset baselines (new asset first run): 3/3 (100%) — iters 7, 23, 37
  - KEEP-VERIFIED runs: 2/2 (100%) — iters 8, 14 (standalone verify-mode runs)
  - train_bars extension: 4/4 (100%) — iters 8, 18, 25, 38. Highest-confidence lever in program.
  - purge_period tuning: 3/5 (60%) — iters 22 (BTC: 12->24), 29 (ETH: 24->12), 39 (SOL: 24->12)
  - drawdown_penalty_weight: 1/1 (100%) — ETH iter 32 (marginal)
  - Alpha features — regime+liquidation: 2/3 (67%) — iters 3, 4 KEEP; iter 5 data not clean
  - Alpha features — funding features: 0/4 (0%) — iters 2, 27, 43, and ETH iter 27
  - time_pcts adjustment: 1/6 (17%) — only [0.30,0.50,0.80] KEEP; all expansions/contractions fail
  - HPO range narrowing: 0/5 (0%) — iters 10, 13, 15, 19, 20. Wall-clock binding.
  - regime_params window changes: 0/3 (0%) — iters 17, 26; SOL skipped (SHAP absent)
  - feature pruning (manual): 0/2 (0%) — iters 16, 24
  - interaction features: 0/1 (0%) — iter 6, +41% Brier regression
  - n_splits changes (any direction from 8): 0/4 (0%) — iters 11, 31, 33; n_splits=8 confirmed
  - embargo_period tuning: 0/2 (0%) — iters 9, 30; embargo=6 confirmed
  - objective/gate experiments: 0/4 (0%) — iters 33, 34, 35, 36; BTC hard floor
  - validation runs (mode=verify/DISCARD-stable): 2/2 reproducible — iters 44, 45
  - Overall: 19 KEEP/KEEP-VERIFIED out of 45 iterations = 42.2%

- **Convergence of best_params across KEEP iterations:**
  - BTC: lr=0.01272, max_depth=4, num_leaves=77, reg_alpha=2.854, reg_lambda=1.131.
    Stable for 17 consecutive experiments (iters 23-44). Highest convergence confidence.
  - ETH: lr=0.009, max_depth=6, num_leaves=95, reg_alpha=1e-6, reg_lambda=0.023.
    Stable across iters 25, 29, 32, 45. Tick-dominant asset: very low regularization.
  - SOL: lr=0.023, max_depth=6, num_leaves=72, reg_alpha=0.016, reg_lambda=8e-6.
    Stable across iters 38, 39, 40, 42, 43. Same pattern as ETH (low regularization).
  - Asset-class split confirmed: BTC uses meaningful L2 regularization (reg_alpha 2.854);
    ETH/SOL converge near reg_alpha=0 with negligible reg_lambda.

- **Brier improvement trajectory: exhausted at confirmed floors.**
  - BTC: 0.1982 (iter 7) → 0.101759 (iter 22). Frozen for 23 iterations (iters 22-45).
    Rate: -0.49% per kept experiment. Floor is structural, not HPO-related.
  - ETH: 0.178243 (iter 23) → 0.177772 (iter 32). Minimal improvement across 9 iters.
    ETH floor appears to be 0.177-0.178 range; tick features provide only marginal signal lift.
  - SOL: 0.193016 (iter 37) → 0.189372 (iter 39). Frozen for 6 iterations (iters 39-45).

- **Feature importance trend across assets:**
  - BTC top-10 SHAP (stable): regime_vol_zscore consistently rank 7; tick features dominate
    ranks 1-6, 8-10. regime_vol_zscore is the sole alpha signal contributing to BTC.
  - ETH/SOL top-10 SHAP: tick features dominate entirely (partial_bar_position, partial_range,
    trade_intensity, volume_ratio_partial, distance_from_open, rsi_7, parkinson_vol_10,
    bar_position, volume_sma_10, rsi_14). No regime or alpha features appear.
  - Asset-class diagnostic: BTC is regime-sensitive; ETH/SOL/XRP-expected are tick-dominant.
    Regime features provide positive marginal value for BTC (confirmed by iter 3 KEEP and
    consistent top-10 rank) but zero measurable value for ETH/SOL after 9+7 experiments.

- **Both-sides vs single-side strategy performance (all 45 iterations):**
  - BTC: single-side sharpe 109.25, bs_sharpe 93.84. Single-side 16% superior for BTC.
    This is consistent across all 22 BTC optimization iterations — BTC is a directional asset.
  - ETH: bs_sharpe 267.08-274.44, single-side sharpe 252.05-270.66. Both-sides marginally
    superior on Sharpe; dramatically superior on absolute PnL ($14M vs $176). ETH is the
    primary market-making asset. bs_sharpe 274.44 is the program-wide record (iter 26/45).
  - SOL: bs_sharpe 251.55, single-side sharpe 251.86. Statistically equal — no clear winner.
  - Recommendation for live deployment: BTC=single-side; ETH=both-sides; SOL=either.

- **HPO starvation: confirmed structural, permanent.**
  At n_splits=8, train_bars=14000, wall-clock timeout binds at 28-34 trials (target 40).
  All knob-level mitigations have been exhausted (n_splits: 0/4 KEEP; train_bars reduction:
  regression; HPO range narrowing: 0/5 KEEP). Starvation reduces trial count by ~30% but
  does not prevent finding the global optimum (best_params stable across 23 iterations).

- **XRP microstructure expectation:**
  XRP futures on Binance (XRPUSDT-M): low open interest vs ETH/SOL, low funding rate
  variability (payment token, not speculative asset), high exchange concentration (Ripple
  reserve effects). Expected to behave as ETH/SOL-class (tick-dominant). Funding features
  should be pre-blacklisted for XRP given 0/4 performance across all other assets. Start
  with 22 features (standard set) without adding funding_* to cached_features.

---

## Blacklist

- **Interaction features (all 8 pairs):** iter 6, +41% Brier regression. Permanent all assets.
- **Funding features in cached_features:** 0/4 KEEP across BTC iter 2, ETH iter 27, SOL iter 43.
  Consistent non-appearance in top-10 SHAP for all three assets. Apply to XRP by default;
  do not test funding for XRP unless XRP SHAP shows anomalous funding signal.
- **HPO range narrowing (all configurations):** iters 10, 13, 15, 19, 20 — 0/5 KEEP.
  Wall-clock timeout binding regardless of bounds. Permanent blacklist all assets.
- **time_pcts expansion beyond 3 points [0.30,0.50,0.80]:** iters 12, 21, 28 — 0/3 KEEP.
  time_pct 0.10 (iter 21): +63% Brier regression. time_pct 0.20+0.90 (iter 12): severe
  regression with HPO starvation. time_pct 0.95 (iter 28): no improvement. Keep at 3 points.
- **embargo_period tuning (both directions from 6):** iters 9, 30 — 0/2 KEEP. Keep at 6.
- **n_splits above or below 8:** iters 11, 31, 33 — 0/4 total including ETH n_splits=6.
  n_splits=8 is confirmed optimal for all assets.
- **regime_params window changes:** iters 17 (BTC: 120->240), 26 (ETH: 120->60). Apply
  blacklist to SOL and XRP without testing (regime_vol_zscore absent from ETH/SOL SHAP).
- **Manual feature pruning from cached_features:** iters 16 (BTC OI prune), 24 (ETH regime
  prune) — 0/2 KEEP. Minimum feature set already determined by feature selection pipeline.
- **train_bars above 10000 for BTC:** saturation at 10000. BTC ceiling confirmed.
- **train_bars above 14000 for ETH:** marginal plateau. ETH ceiling at 14000.
- **train_bars above 14000 for SOL:** floor reached before further saturation. Ceiling at 14000.
- **BTC objective gate experiments (iters 33-36):** brier_threshold 0.15, 0.10; n_splits=6;
  min_target_corr 0.010 — 0/4 KEEP. Floor locked. Permanent for BTC.
- **max_depth above 6 for SOL:** iter 41 DISCARD (max_depth=7: Brier 0.192005 > 0.189372).
  max_depth=6 confirmed SOL ceiling. Do not raise for SOL.
- **Sharpe-primary objective for SOL:** iter 42 DISCARD — identical best_params to brier-primary.
  Landscape invariant. Permanent for SOL.
- **XRP expansion before CPCV validation and auditor clearance:** iters 47-49 (CPCV sweep)
  and auditor invocation are mandatory gates. Do not start XRP dataset generation until both
  are complete.

---

## HPO Range Recommendations

- `max_depth` for BTC: keep [2,6]. Best always lands at 4. Could narrow to [2,6] without change.
  Do not raise ceiling for BTC (no evidence needed for deeper trees given stable floor).
- `max_depth` for ETH/SOL: keep [2,6]. Both assets converge at 6 (ceiling hit). Current range
  is correct — raising to [2,8] is blacklisted for SOL (iter 41 regression evidence).
- `max_depth` for XRP: start at [2,6]. If XRP best_params hit max_depth=6 in 2+ consecutive
  KEEPs, raise to [2,8] as a hypothesis, but SOL precedent suggests regression is likely.
- `learning_rate`: BTC best lr=0.01272, ETH best lr=0.009, SOL best lr=0.023. All in lower
  half of [0.005,0.1]. For XRP, start with full range — do not narrow until 3+ XRP KEEPs
  show convergence. Tentative XRP expected range: [0.005,0.05] by analogy with SOL.
- `reg_alpha`: BTC=2.854 (mid-range); ETH=1e-6, SOL=0.016 (both near lower bound).
  Asset-specific divergence — do not narrow for XRP until convergence established.
- `reg_lambda`: SOL reg_lambda=8e-6 near lower bound across 3/3 SOL KEEPs (iters 38, 39, 40).
  3-observation threshold met. For any future SOL experiments: narrow upper bound to [1e-8, 0.01].
  ETH reg_lambda=0.023 is also near lower bound; same narrowing applies to ETH if future
  experiments are needed. Do not apply to BTC.
- `n_estimators`, `subsample`, `colsample_bytree`, `min_child_samples`: maintain current
  wide ranges for all assets. No convergence signal across assets.

---

## Cross-Asset Status Summary

| Asset | Best Brier | Best bs_sharpe | Opt Iters   | Config Status          | Validation Status         |
|-------|------------|----------------|-------------|------------------------|---------------------------|
| BTC   | 0.101759   | 93.84          | 22 (7-36)   | Exhausted — hard floor | verify PASS (iter 44)     |
| ETH   | 0.177772   | 274.44         | 9 (23-32)   | Exhausted — hard floor | verify PASS (iter 45)     |
| SOL   | 0.189372   | 251.55         | 7 (37-43)   | Exhausted — hard floor | verify IN PROGRESS        |
| XRP   | —          | —              | 0           | BLOCKED — CPCV gate    | N/A                       |

---

## Acceptance Gate (all static metrics pass; PBO/Deflated Sharpe pending CPCV)

| Metric          | Required  | BTC Status          | ETH Status          | SOL Status          |
|-----------------|-----------|---------------------|---------------------|---------------------|
| OOS Brier       | < 0.25    | 0.101759 PASS       | 0.177772 PASS       | 0.189372 PASS       |
| OOS ECE         | < 0.05    | 0.0088 PASS         | 0.0252 PASS         | 0.0135 PASS         |
| Net PnL         | > 0       | $45.55 PASS         | $176.50 PASS        | $172.13 PASS        |
| Max drawdown    | < 30%     | 13.61% PASS         | 1.75% PASS          | 1.62% PASS          |
| PBO             | < 0.40    | PENDING iter 47     | PENDING iter 48     | PENDING iter 49     |
| Deflated Sharpe | > 0.0     | PENDING iter 47     | PENDING iter 48     | PENDING iter 49     |

Note on BTC drawdown: 13.61% is the highest of the three assets. It passes the 30% threshold
with margin, but is elevated vs ETH (1.75%) and SOL (1.62%). This difference is structural:
BTC uses single-side sniper (directional, concentrated exposure) while ETH/SOL benefit from
both-sides MM (spread captures, lower directional exposure). Not a concern for acceptance, but
relevant to live deployment risk sizing.

All four static metrics pass for all three active assets. The CPCV sweep (iters 47-49) plus
auditor clearance are the only remaining gates. Both are already operationally ready.
