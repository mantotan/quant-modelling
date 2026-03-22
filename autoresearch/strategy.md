# Strategy Directive
Updated: 2026-03-23T11:00:00Z
After iteration: 165

## Program Status: Cross-Asset Campaign Complete — Evaluating New Levers

Iters 162-165 completed all 6 remaining items from strategy-after-161. The cross-asset re-run campaign
(iters 152-165) is the most productive campaign in the 165-iteration program history:
- 10 KEEPs + 2 DISCARDs in 14 iterations (71% KEEP rate)
- Every non-BTC model now has post-cross-asset baselines with BTC features in top-3 SHAP
- BTC models (5m/15m/1h) confirmed at structural floors with no cross-asset lever available

**New results this period (iters 162-165):**
- **SOL/1h KEEP-VERIFIED (iter 162)**: Brier=0.207484 (+5.41%), cross-asset top-3 confirmed
- **XRP/1h KEEP-VERIFIED (iter 163)**: Brier=0.206414 (+7.30%), cross-asset top-2 confirmed
- **BTC/15m DISCARD (iter 164)**: n_estimators=[150,350] — declared permanent floor 0.171809
- **XRP/5m KEEP (iter 165)**: Brier=0.209444 (+0.13% marginal), ceiling widen num_leaves=29 free within [16,48]

### Final Post-Cross-Asset Baselines (All 12 Models)

| Asset | 5m Best           | 15m Best          | 1h Best           |
|-------|-------------------|-------------------|-------------------|
| BTC   | 0.17605 (iter 104) FLOOR | 0.171809 (iter 123) FLOOR | 0.174676 (iter 136) |
| ETH   | 0.199722 (iter 156) | 0.193035 (iter 152) | 0.191504 (iter 160) |
| SOL   | 0.207246 (iter 158) | 0.200064 (iter 155) | 0.207484 (iter 162) |
| XRP   | 0.209444 (iter 165) | 0.205323 (iter 159) | 0.206414 (iter 163) |

All 9 non-BTC models are at post-cross-asset verified baselines.
BTC/5m and BTC/15m are at permanent structural floors (no cross-asset lever).
BTC/1h has had 3 near-misses (iters 136-138) but no attempts since iter 138.

### Cross-Asset Campaign: Lever Exhaustion Assessment

The cross-asset re-run campaign has been the single most productive lever in the program. With all 12
models updated, the question is: what high-value levers remain?

**Remaining unexplored or partially-explored levers:**

1. **Specialist split** (`specialist.enabled=true, boundary=0.4`): Never tested in 165 iterations.
   Rationale: The 5 time_pcts snapshots [0.1, 0.2, 0.4, 0.6, 0.8] may have fundamentally different
   predictive regimes. Early snapshots (0.1, 0.2) capture bar-opening momentum; late snapshots
   (0.6, 0.8) capture near-close momentum. Training a single model across all 5 conflates these
   signals. A specialist split at boundary=0.4 trains two sub-models (early: [0.1,0.2],
   late: [0.4,0.6,0.8]), potentially improving calibration for each regime.
   This is the highest-value untested structural change in the knobs.json.

2. **BTC/1h post-floor stochastic re-run**: BTC/1h had 3 near-misses at iter 136-138 but the
   best (0.174676, iter 136) used n_estimators=350 AT ceiling. The two subsequent runs used
   [100,250] with n_estimators=182 and 230 — both near-misses. A fresh run at [100,350] (the
   confirmed optimal range from iter 136) may escape the stochastic basin. Low expected value
   (<1% improvement likely) but costs only one fast experiment.

3. **num_leaves re-survey on BTC models**: BTC/1h iter 136 has n_estimators=350 AT ceiling —
   likely still starved. The confirmed starvation-free range is [100,250] from iters 137-138.
   BTC/1h num_leaves=76-83 across iters 137-138 (high, different from 1h tick-dominant assets).
   A run targeting num_leaves=[48,96]+n_estimators=[100,250] could check whether the 76-83 region
   is truly optimal or whether narrowing to that range unlocks a further improvement.

4. **Walk-forward config on post-cross-asset baselines**: n_splits=8, train_bars=10000 was set
   pre-cross-asset. The cross-asset features add 4 BTC features per snapshot; richer feature
   space may benefit from more training data (train_bars=12000-15000) or more splits (n_splits=10).
   This is a low-priority lever but has not been evaluated in the post-cross-asset era.

5. **SOL/1h num_leaves refinement**: iter 162 verify converged to num_leaves=27 at [16,64] ceiling.
   The fast run had num_leaves=48, verify=27 — a large discrepancy (fast/verify spread 2.81pct).
   The true optimum may be in the 27-35 range. A narrowed run [20,40]+[100,400] could tighten
   the search and potentially find a lower Brier. Expected value: 1-3%.

6. **XRP/15m n_estimators ceiling**: iter 159 verify found n_estimators=595 near 600 ceiling
   (structural starvation confirmed). The model quality is likely constrained by the ceiling.
   A test at [100,800] or [100,1000] may unlock further improvement despite the starvation
   cost. This is high-risk (starvation will reduce trial count) but XRP/15m has historically
   responded to higher ceilings.

## Priority Queue

1. **Specialist split: ETH/1h with specialist.enabled=true, boundary=0.4**
   Rationale: ETH/1h is the best-performing 1h model (0.191504) and has the most consistent
   tick-dominant pattern with BTC cross-asset features dominant. Testing specialist split on
   the best baseline first gives maximum signal quality. The specialist knob creates 2 sub-models
   (early: time_pcts=[0.1,0.2], late: time_pcts=[0.4,0.6,0.8]) — this has never been tested
   in 165 iterations and is the only remaining structural knob.
   Specific change: `specialist.enabled=true`, `specialist.boundary=0.4`,
   `specialist.early_time_pcts=[0.1,0.2]`, `specialist.late_time_pcts=[0.4,0.6,0.8]`
   Keep num_leaves=[16,32] and n_estimators=[100,400] from iter 160 (known optimal range).
   Accept if: Brier(specialist) < 0.191504.

2. **Specialist split: SOL/15m with specialist.enabled=true**
   Rationale: SOL/15m (0.200064) represents the tick-dominant asset class with clean
   cross-asset features. If specialist split works on ETH/1h, test on SOL/15m to confirm
   generalizability. Use num_leaves=[32,72]+n_estimators=[100,400] from iter 155.
   Accept if: Brier(specialist) < 0.200064.

3. **BTC/1h stochastic re-run num_leaves=[48,96]+n_estimators=[100,250]**
   Rationale: BTC/1h best (iter 136) found num_leaves=76-83 across iters 137-138 but those
   were both stochastic near-misses. The starvation-free range [100,250] is confirmed. Narrowing
   num_leaves search to [48,96] (centering on 76-83 observed optimum) with the starvation-free
   n_estimators range may escape the 0.1746-0.1750 basin.
   Accept if: Brier < 0.174676.

4. **SOL/1h num_leaves narrowing [20,40]+n_estimators=[100,400]**
   Rationale: Iter 162 fast=48, verify=27 — large fast/verify discrepancy suggests the fast run
   was sub-optimal. The verify optimum (27) is in the lower half of [16,64]. Narrowing to [20,40]
   focuses search on the confirmed optimum range and may reduce stochastic variance.
   Accept if: Brier < 0.207484.

5. **XRP/15m n_estimators ceiling widen [100,800]+num_leaves=[32,80]**
   Rationale: iter 159 verify had n_estimators=595 near 600 ceiling — the model is ceiling-bound.
   Raising to 800 allows HPO to escape the ceiling and potentially find a lower Brier. Starvation
   will be present (historical XRP/15m structural) but the improvement potential is real.
   Accept if: Brier < 0.205323.

6. **Specialist split: XRP/5m as representative of starvation class**
   Run after items 1-2 provide evidence on whether specialist split generalizes.
   Use num_leaves=[16,48]+n_estimators=[100,400] from iter 165.

## Observations

- **Cross-asset category: 9/9 KEEPs (100%) across iters 152-165** — the single highest-value
  lever in the program history. All non-BTC assets show btc_vol_norm_distance and
  btc_distance_from_open in top-2 SHAP universally. Cross-asset lever is now exhausted
  (all 9 non-BTC models updated; BTC has no cross-asset lever available).

- **HPO-range category: 16/47 KEEPs (34%)** across the full program. The typical pattern is
  multiple DISCARDs before finding the correct starvation-free range, then a KEEP. After the
  cross-asset campaign, most ranges are dialed in. Further HPO narrowing on post-cross-asset
  baselines may have marginal gains only.

- **Regularization forcing: 0/5 KEEPs** — reg_alpha forcing strategy consistently failed
  (iters 139, 143, 144, 145, 146). Blacklisted.

- **Anti-starvation (ceiling reduction): 1/4 KEEPs** — succeeded in specific cases where
  the ceiling was wasted (not the universal fix). Now mostly resolved; all models have
  confirmed optimal ranges.

- **Specialist: 0/0 tests** — the only fully untested structural knob. Priority #1.

- **Brier improvement trajectory**: Decelerating. Pre-cross-asset: 0.01-2% improvements.
  Cross-asset campaign: 4.96-9.43% improvements. Post-cross-asset: 0.13% marginal (iter 165).
  The program has successfully exploited the largest available lever. Remaining gains will
  be smaller (0.5-3% range) unless specialist split reveals a structural benefit.

- **SHAP universal patterns confirmed**:
  - btc_vol_norm_distance + btc_distance_from_open appear in top-3 for ALL 9 non-BTC KEEPs
  - btc_partial_bar_position appears in top-10 for 8/9 non-BTC KEEPs
  - btc_partial_range appears less consistently (3-4/9 KEEPs)
  - Recommendation: btc_partial_range could be removed if it does not appear in specialist
    sub-model top-10 (frees one feature slot)

## Risk Profile

- **Max drawdown trend**: Stable. 5m assets: $305-$309. 1h assets: $72-$76. 15m assets: $293-$299.
  Ratios are healthy (max_dd/pnl well under 1.0 across all KEEPs).
- **Trade count range across KEEPs**: 5m ~80,780-81,000; 15m ~75,400-77,061; 1h ~18,586-18,998.
  Stable — no sudden drops or spikes. Trade count is consistent within each timeframe class.
- **Win rate range across KEEPs**: tick-dominant: 49.5%-53.6%; BTC sniper: 60-67%.
  Win rate stable — calibration is holding across cross-asset updates.
- **HPO-OOS gap**: Recent KEEPs show hpo_objective within 0.01-0.03 of oos_brier. Stable.
  No widening trend — cross-asset features did not introduce overfitting.
- **BS-PnL vs single-side**: Not systematically tracked in recent iterations (columns absent
  in several rows). Both strategies remain enabled in knobs.json.

## Timeframe Coverage

- 5m: ~66 iterations, 28 KEEPs, best Brier BTC=0.17605 / ETH=0.199722 / SOL=0.207246 / XRP=0.209444
- 15m: ~43 iterations, 20 KEEPs, best Brier BTC=0.171809 / ETH=0.193035 / SOL=0.200064 / XRP=0.205323
- 1h: ~39 iterations, 20 KEEPs, best Brier BTC=0.174676 / ETH=0.191504 / SOL=0.207484 / XRP=0.206414
- Recommendation: All timeframes have been covered. Priority #1 is specialist split on 1h
  models (where intra-bar dynamics may differ most between early/late snapshots).

## Blacklist

- **reg_alpha forcing [0.1,5.0]**: 0/5 KEEPs (iters 139, 143, 144, 145, 146). Permanently
  blacklisted — this approach fails across all assets and timeframes.
- **interaction_features**: Never produced a top-20 SHAP feature across 165 iterations.
  Permanently disabled (interaction_features.enabled=false already in knobs.json).
- **alpha_features (funding, OI, IV, polymarket)**: 0 appearances in top-10 SHAP across
  44+ KEEPs (auditor Ruling 3 formal block). These are in cached_features for training but
  contribute no signal. Keep in pipeline for data completeness but do not enable specifically.
- **BTC/5m further improvement**: Permanent structural floor 0.17605 (iter 104).
  n_estimators=103 near lower bound confirmed HPO landscape non-smooth. No further attempts.
- **BTC/15m further improvement**: Permanent floor 0.171809 (iter 123). Three consecutive
  starvation-free near-misses (iters 154, 157, 164). No further attempts.
- **n_estimators=[100,1500]**: Confirmed wasteful — all assets optimize well below 600.
  Upper bound ceiling should never exceed 600 for any future experiment.

## HPO Range Recommendations

- **num_leaves**: Asset-specific confirmed ranges:
  - BTC: 40-83 (5m/15m optimum ~43-46; 1h optimum ~76-83)
  - ETH: 20-103 (1h optimum ~22; 15m optimum ~103; 5m optimum ~69)
  - SOL: 27-51 (all timeframes in 27-51 range, tight convergence)
  - XRP: 25-50 (5m optimum ~29-39; 15m optimum ~50; 1h optimum ~39-42)
- **n_estimators**: Asset-specific confirmed ranges:
  - BTC: [100,350] for 5m/15m/1h (optimum 103-235 range depending on run)
  - ETH: [100,500] for 5m/15m; [100,400] for 1h (optimum 307-389)
  - SOL: [100,400] for all timeframes (optimum 224-354)
  - XRP: [100,600] for 15m (ceiling-bound); [100,400] for 5m/1h (optimum 230-386)
- **learning_rate**: [0.005, 0.1] is the correct range. Asset patterns:
  - BTC: lr ~0.017-0.061 (varies by run)
  - ETH: lr ~0.016-0.024 (tick-dominant low lr)
  - SOL: lr ~0.016-0.094 (wider spread)
  - XRP: lr ~0.049-0.098 (higher lr preference)
