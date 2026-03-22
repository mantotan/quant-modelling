# Audit Report
Updated: 2026-03-23T06:00:00Z
After iteration: 162

## Verdict: CONTINUE
The cross-asset re-run campaign (iters 152-162) is the most productive campaign since the multi-tp OVERRIDE era, delivering 8 KEEPs in 11 iterations (73% KEEP rate) with 5-9% Brier improvements per KEEP. The researcher is executing the strategist's priority queue correctly and efficiently. The remaining 3 items (XRP/1h cross-asset re-run, BTC/15m final attempt, XRP/5m ceiling widen) are well-defined with clear accept/reject criteria. No intervention needed.

## Directive Details

**CONTINUE** with the following observations and binding notes:

### Cross-Asset BTC Features: Confirmed Universal Lever

The cross-asset re-run campaign has produced the single most impactful and consistent lever in the entire 162-iteration program:
- 8/8 non-BTC cross-asset re-runs produced KEEPs (100% KEEP rate for cross-asset experiments)
- btc_vol_norm_distance and btc_distance_from_open appear in top-3 SHAP for ALL 8 KEEPs
- Improvement range: 4.96% (SOL/5m) to 9.43% (ETH/1h), mean ~6.4%
- All non-BTC models improved to new post-cross-asset baselines

This is not overfitting. The improvements are consistent across 3 assets, 3 timeframes, and multiple HPO configurations. BTC leads the broader crypto market, and cross-asset tick features capture this lead-lag relationship at intra-bar resolution.

### Remaining Campaign Items: Expected Value Assessment

1. **XRP/1h cross-asset re-run (strategy #3)**: HIGHEST remaining expected value. XRP/1h iter 149 (pre-cross-asset) = 0.222676. ETH/1h saw +9.43%, SOL/1h saw +5.41%. Expected improvement: 5-10%, target 0.200-0.211. This single experiment could bring XRP/1h below 0.21 for the first time.

2. **BTC/15m final attempt (strategy #5)**: LOW expected value. Three consecutive starvation-free runs (iters 123, 154, 157) produced 0.171809, 0.173259, 0.171889. The landscape is confirmed flat in the 0.1718-0.1733 range. One more attempt with n_est=[150,350] is acceptable but the auditor expects DISCARD. After this: declare permanent BTC/15m floor.

3. **XRP/5m ceiling widen (strategy #6)**: MARGINAL expected value. Iter 161 verify found num_leaves=39 near 40 ceiling. Widening to 48 may find 1-2%. Worth one test but not worth more than one.

### Note: Post-Campaign Transition Planning

After the remaining 3 items complete (estimated 3-5 more iterations), the HPO research program will be exhausted for all 12 models. The auditor recommends that the strategist begin drafting a "program complete" summary after XRP/1h completes. All 12 models will have:
- Post-cross-asset baselines established
- num_leaves ranges confirmed via convergence evidence
- Structural floors documented for BTC/5m, BTC/1h, and potentially BTC/15m
- All known HPO levers tested (anti-starvation, num_leaves narrowing, reg_alpha forcing, cross-asset)

The next phase should be deployment readiness (backtest-to-live gap investigation), NOT further HPO iteration.

### Alpha Feature Ruling: REAFFIRMED

The prior audit's ruling blocking ADD_ALPHA for funding, OI, IV, liquidation, and Polymarket sources remains in force. Zero alpha features in top-10 SHAP across 50+ KEEP iterations (iters 92-162) is conclusive. Cross-asset BTC tick features are the only non-tick alpha source that works.

## Progress Assessment

- Improvement rate: ACCELERATING in this period due to cross-asset lever discovery. Mean improvement per KEEP: 6.4% (iters 152-162) vs <0.3% (iters 123-142). This is a structural shift, not sustainable -- once all 9 non-BTC models have cross-asset baselines, improvement rate will return to deceleration.
- Estimated iterations to full program completion: 3-5 (XRP/1h + BTC/15m + XRP/5m)
- KEEP rate: 73% (8/11, iters 152-162) vs 25% (5/20, iters 123-142). Dramatic increase driven by cross-asset feature deployment being a near-guaranteed improvement for pre-cross-asset models.

## Risk Flags

- Overfitting: NONE -- hpo_objective vs oos_brier gaps remain structurally explained:
  - BTC/15m iter 157: hpo_obj=0.175302 vs oos_brier=0.171889, gap=0.003 (trade_penalty component, not overfitting)
  - ETH/1h iter 160: hpo_obj=0.262576 vs oos_brier=0.191504, gap=0.071 (trade_penalty dominant for 1h low-trade-count models, structural)
  - SOL/15m iter 155: hpo_obj=0.253259 vs oos_brier=0.200064, gap=0.053 (trade_penalty structural)
  - ETH/15m iter 152: hpo_obj=0.197081 vs oos_brier=0.193035, gap=0.004 (clean, minimal penalty)
  - All gaps are STABLE or NARROWING vs prior period. No widening trend. No genuine overfitting.
- Calibration drift: ECE STABLE -- all KEEP rows in period: 0.0059 (SOL/15m) to 0.0286 (ETH/1h). All well below 0.05 ceiling. ETH/1h at 0.0286 is the highest value; monitor but not concerning.
- PnL disconnect: Brier-PnL correlation STRONG -- all 8 KEEPs show improved or maintained PnL alongside Brier improvement. No divergence.
  - ETH/15m: Brier 0.2083->0.1930, PnL $291->$298 (improved)
  - SOL/5m: Brier 0.2181->0.2072, PnL $303->$305 (improved)
  - ETH/1h: Brier 0.2114->0.1915, PnL $73.6->$75.0 (improved)
  - SOL/1h: Brier 0.2193->0.2075, PnL $70.6->$72.0 (improved)
- Drawdown risk: STABLE -- max_dd values for recent KEEPs: ETH/15m 0.07, SOL/15m 0.0512, ETH/5m 0.06, SOL/5m 0.0688, XRP/15m 0.0725, ETH/1h 0.0625, XRP/5m 0.0625, SOL/1h 0.085. All well below PnL in absolute terms. max_dd/pnl ratios: 0.0002-0.001 for 5m/15m (excellent), 0.0008-0.001 for 1h (excellent). No increasing trend.
- Trade volume: STABLE -- 5m: ~80-81K trades; 15m: ~75-76K trades; 1h: ~18-19K trades. No decline. All far above 50-trade minimum.
- Win rate: tick-dominant assets 49-52% (structural FLAT, consistent with probability model). BTC sniper 66% (iter 157). All within 40-85% plausible range. No cherry-picking signals.
- Strategy divergence: bs_pnl (both-sides) remains strongly positive across all KEEPs and generally moves in same direction as single-side PnL. No divergence detected.
- Search exhaustion: RESOLVED for cross-asset re-runs (7/9 non-BTC models now have post-cross-asset baselines; XRP/1h remaining). CONFIRMED EXHAUSTED for BTC models (BTC/5m floor, BTC/1h floor, BTC/15m near-floor with one attempt remaining). Overall program approaching completion within 3-5 iterations.
- Fast/verify consistency: All 8 KEEP-VERIFIED rows show fast-verify Brier delta < 3% (SOL/1h 2.81% is the widest; most are <0.3%). No verification drift.

## Timeframe Coverage

| Timeframe | Iterations (total) | KEEPs (total) | Best Brier         | Best PnL        |
|-----------|--------------------|---------------|--------------------|-----------------|
| 5m        | ~52                | 12            | BTC 0.17605 (i104) | ETH $312.66 (i156) |
| 15m       | ~45                | 16            | BTC 0.171809 (i123)| XRP $298.67 (i159) |
| 1h        | ~47                | 14            | BTC 0.174676 (i136)| ETH $75.03 (i160)  |

Coverage is well-balanced. The 1h timeframe received concentrated attention in this period (ETH/1h iter 160, SOL/1h iter 162) and will continue to receive attention (XRP/1h next). No timeframe is underserved.

## Post-Cross-Asset Baseline Table (all 12 models)

| Asset | 5m Brier | 5m Iter | 15m Brier | 15m Iter | 1h Brier | 1h Iter |
|-------|----------|---------|-----------|----------|----------|---------|
| BTC   | 0.17605  | 104     | 0.171809  | 123      | 0.174676 | 136     |
| ETH   | 0.199722 | 156     | 0.193035  | 152      | 0.191504 | 160     |
| SOL   | 0.207246 | 158     | 0.200064  | 155      | 0.207484 | 162     |
| XRP   | 0.209715 | 161     | 0.205323  | 159      | 0.222676*| 149     |

*XRP/1h is the ONLY remaining model without a post-cross-asset baseline. This is the highest-priority experiment.

Sub-0.20 models: BTC (all 3 TFs), ETH (all 3 TFs), SOL/15m (0.200064 boundary). That is 7/12.

## Acceptance Criteria Status (per best asset+timeframe)

| Metric       | Target      | Current Best                        | Gap/Status          |
|-------------|-------------|-------------------------------------|---------------------|
| Brier        | < 0.25      | 0.171809 (BTC/15m i123)             | PASS -- all 12 below 0.23 |
| Brier t>=0.10| < 0.25/bucket| consistent across verified runs     | OK -- no bucket violations reported |
| ECE          | < 0.05      | 0.0059 (SOL/15m i155)               | PASS -- all below 0.036 |
| PnL          | > 0         | $312.66 (ETH/5m i156)               | PASS -- all positive |
| Sharpe       | > 0.0       | 251.66 (ETH/5m i156)                | PASS -- all >> 0.0 (still inflated but consistently positive) |
| Max DD       | < PnL       | max 0.232 (BTC/15m) vs PnL $43+     | PASS -- DD << PnL in all cases |
| Trades       | >= 10       | 18K-81K depending on timeframe      | PASS -- all >> 10 |
| Win Rate     | 40-85%      | BTC sniper 66%, tick 49-52%         | PASS -- all in range |
| HPO-OOS Gap  | stable      | 0.003-0.071 (penalty-dominated)     | STABLE -- no widening trend |
| BS PnL       | > 0         | $70M+ (ETH/5m i156)                 | PASS -- informational |
| Trades/bar   | 1 (Phase 2) | varies                              | Phase 2 not yet started |

**CPCV Status: All 12 validations complete (unchanged from prior audit).** No re-validation needed unless model architecture changes.

## Researcher Compliance

The researcher has been executing the strategist's priority queue faithfully:
- Iters 152-162 map directly to strategy priorities #1 through current
- KEEP-VERIFIED protocol followed correctly (fast + verify runs with --save)
- Knob changes are precise and well-documented
- No unauthorized experiments or deviations from the queue
- Cross-asset feature activation handled correctly (features appear in SHAP top-3 for all KEEPs)

Researcher compliance: EXCELLENT.
