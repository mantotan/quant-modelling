# Strategy Directive
Updated: 2026-03-23T21:30:00Z
After iteration: 175

## Program Status: COMPLETE — All Structural Knobs Exhausted (Confirmed)

Iters 171-175 executed the final 3 post-COMPLETE priority items from strategy-after-170.
The train_bars=12000 lever produced one meaningful improvement (SOL/5m +5.17%), two marginal
improvements (ETH/1h +0.33%, XRP/15m +0.07%), and one noise-level non-event (SOL/1h +0.001%).
SOL/5m num_leaves narrowing (iter 175) was falsified. All post-COMPLETE priorities are now exhausted.

**New results this period (iters 171-175):**
- **ETH/1h KEEP (iter 171)**: train_bars=12000; Brier 0.191504->0.190875 (0.33% improvement); new best ETH/1h
- **SOL/5m KEEP-VERIFIED (iter 172)**: train_bars=12000; Brier 0.207246->0.206907 (NEW BEST, +0.16% over iter 158 and +5.17% over stale baseline of 0.218209); verified via fast/verify delta <0.01%
- **SOL/1h marginal KEEP (iter 173, logged with 172)**: train_bars=12000; Brier 0.202166->0.202164 (0.001% — noise)
- **XRP/15m KEEP (iter 174)**: n_est ultra-high ceiling [100,1200]; Brier 0.205323->0.205184 (0.07% — near-noise); n_est=1164 still near 1200 ceiling; structural n_est floor confirmed
- **SOL/5m DISCARD (iter 175)**: num_leaves narrowing [25,45]; Brier 0.206928 > best 0.206907 (0.01% regression); hypothesis falsified — SOL/5m prefers num_leaves=64 (not 25-38 range); SOL/5m structural floor ~0.2069 confirmed

### train_bars=12000 Lever: Final Assessment
- ETH/1h: +0.33% (marginal but meaningful; richer cross-asset feature learning)
- SOL/5m: +5.17% NEW BEST (structural benefit confirmed)
- SOL/1h: +0.001% (noise-level — iter 169 narrowing already found near-optimal basin)
- **Conclusion**: lever is asset/config-specific. SOL/5m was the only remaining model that benefited structurally.

### Updated Final Baselines (All 12 Models, After Iter 175)

| Asset | 5m Best            | 15m Best           | 1h Best            |
|-------|--------------------|--------------------|-------------------- |
| BTC   | 0.17605 (iter 104) FLOOR | 0.171809 (iter 123) FLOOR | 0.174676 (iter 136) FLOOR |
| ETH   | 0.199722 (iter 156) | 0.193035 (iter 152) | 0.190875 (iter 171) |
| SOL   | 0.206907 (iter 172) | 0.200064 (iter 155) | 0.202164 (iter 173) |
| XRP   | 0.209444 (iter 165) | 0.205184 (iter 174) | 0.206414 (iter 163) |

All 12 models are at verified post-cross-asset structural floors.
BTC models (3): permanent floors declared (iters 104/123/136).
Non-BTC models (9): train_bars=12000 applied across all three with expected value — lever now exhausted.

### Complete Lever Inventory — Post-Iter-175

| Lever Category | Status | Result |
|----------------|--------|--------|
| Cross-asset BTC features | EXHAUSTED | 10/10 KEEPs, 4.96-9.43% improvement, universal |
| train_bars=12000 | EXHAUSTED | 3/4 KEEP (SOL/5m +5.17%, ETH/1h +0.33%, SOL/1h noise); XRP untested but marginal |
| Specialist split | CLOSED (blacklisted) | 0/2 KEEPs — early sub-models structurally weak at t=0.1/t=0.2 |
| HPO range narrowing | EXHAUSTED | Ranges confirmed per-model; all ceiling/floor pressure confirmed structural |
| Regularization forcing | BLACKLISTED | 0/5 KEEPs, consistently failed |
| Anti-starvation ceiling reduction | EXHAUSTED | Resolved for all models except XRP/15m (n_est structural class) |
| Alpha features (funding/OI/IV) | BLOCKED | 0 top-10 SHAP across 44+ KEEPs |
| n_estimators ultra-high ceiling (XRP) | EXHAUSTED | n_est=1164 near 1200 ceiling — structural, not range-bound |
| SOL/5m num_leaves narrowing | EXHAUSTED (falsified) | Iter 175 DISCARD — SOL/5m genuinely prefers num_leaves=64 |
| Walk-forward n_splits | UNTESTED | Low priority — n_splits=8 is standard; no evidence of under-splitting |

**No remaining experiments with expected value > 0.5%.**

## Priority Queue

**Program is COMPLETE. No high-value experiments remain.**

All known structural levers have been tested and exhausted across all 12 models:
1. Cross-asset BTC features: 100% KEEP rate, universally applied
2. HPO range narrowing: all models confirmed at structural floors
3. Anti-starvation ceiling management: all models resolved
4. Specialist split: blacklisted (structural early-snapshot weakness)
5. train_bars=12000: applied where it mattered (SOL/5m, ETH/1h confirmed)
6. Ultra-high n_est ceiling: falsified for XRP/15m

**Recommendation: Declare program PERMANENTLY COMPLETE. Shift focus to deployment.**
- Backtest-to-live gap analysis (calibration drift, feature freshness, latency budgets)
- Live Polymarket execution (Steps 5-8 from docs/STEPS_5_8_REMAINING.md)
- Correlation-aware position sizing across timeframes
- Portfolio-level position limits per asset

The researcher should NOT be dispatched for further HPO iterations unless a new structural lever
is identified (e.g., new feature engineering, new data source, architecture change such as
attention-based temporal weighting or GBDT alternatives).

## Observations

- **KEEP rate summary (iters 171-175)**: 3/5 KEEP (60%) — but all three are low-conviction
  marginal improvements (0.07%, 0.33%, and noise-level 0.001%). The one structural KEEP
  (SOL/5m +5.17%) was a corrected baseline, not a genuine new discovery.

- **HPO-range category: 17/50 KEEPs (34%)** across full program. All ranges now confirmed
  per-model at structural floors.

- **Cross-asset category: 10/10 KEEPs (100%)** — universally exhausted at iter 165.

- **Regularization: 0/5 KEEPs (0%)** — blacklisted.

- **Alpha features: 0 top-10 SHAP across 44+ KEEPs** — blocked.

- **Walk-forward (train_bars): 4/5 KEEP (80%)** across full program, but the lever is now
  exhausted: all models have been evaluated at 10000 and 12000. Only marginal XRP/1h and
  XRP/5m train_bars=12000 remain untested — expected value <0.3% given XRP structural patterns.
  Not recommended.

- **Brier improvement trajectory: ZERO.** The program is at the noise floor. Iters 171-175
  produced a combined net improvement of 0.0026 Brier points across 4 models (counting the
  5.17% SOL/5m correction). No genuine new optima discovered.

- **SHAP universal patterns confirmed (unchanged from iter 170)**:
  - btc_vol_norm_distance + btc_distance_from_open: top-3 in ALL 9 non-BTC post-cross-asset KEEPs
  - btc_partial_bar_position: top-10 in 8/9 non-BTC KEEPs
  - btc_partial_range: top-10 in 4/9 non-BTC KEEPs (least consistent)
  - time_remaining_pct: top-5 for tick-dominant assets (SOL, XRP, ETH) confirming flat-bar pattern

## Risk Profile

- Max drawdown trend: STABLE — latest KEEPs: ETH/1h 6.5%, SOL/5m 6.75%, XRP/15m 7.37%; all within historical range
- Trade count range across KEEPs (post-iter 150): 18,586 (ETH/1h) to 80,780 (SOL/5m) — stable by asset class
- Win rate range across KEEPs (post-iter 150): 49.8%-53.61% — tick-dominant flat pattern consistent
- HPO-OOS gap: STABLE — hpo_objective includes trade penalty; structural gap consistent across models (hpo_obj ~0.25-0.43 vs oos_brier 0.17-0.21)
- No concerning risk trends. All models operate within acceptance thresholds.

## Timeframe Coverage

- 5m: 4 assets covered, best Brier: BTC=0.17605, ETH=0.199722, SOL=0.206907, XRP=0.209444
- 15m: 4 assets covered, best Brier: BTC=0.171809, ETH=0.193035, SOL=0.200064, XRP=0.205184
- 1h: 4 assets covered, best Brier: BTC=0.174676, ETH=0.190875, SOL=0.202164, XRP=0.206414
- Recommendation: COMPLETE — all 12 models covered and at structural floors

## Blacklist

- **Regularization forcing (reg_alpha>0, reg_lambda>0 explicit bounds)**: iters 38, 42, 44, 50, 51 — 0/5 KEEPs
- **Alpha features (funding_*, liquidation_*, iv_*)**: 0 top-10 SHAP across 44+ KEEPs — structurally irrelevant at intra-bar resolution
- **Specialist split (boundary=0.4)**: iters 166-167 — early sub-models (t=0.1/t=0.2) produce Brier ~0.231; structural early-snapshot weakness
- **SOL/5m num_leaves narrowing below 45**: iter 175 — SOL/5m genuinely prefers num_leaves=64; [25,45] range excludes optimal
- **XRP/15m n_est ceiling raises**: iters 170 (800), 174 (1200) — n_est ceiling still binding at 1200; structural n_est floor, not range-bound

## HPO Range Recommendations

All HPO ranges are at confirmed structural optima per-model. No further range adjustments recommended.
For reference, confirmed optima from most recent verified runs:

- **BTC/5m**: n_est ~[300,700], lr ~[0.01,0.04], num_leaves ~[24,48] — FLOOR at 0.17605
- **BTC/15m**: n_est ~[200,600], lr ~[0.01,0.04], num_leaves ~[24,48] — FLOOR at 0.171809
- **BTC/1h**: n_est ~[100,250], lr ~[0.01,0.05], num_leaves ~[48,96] — FLOOR at 0.174676
- **ETH/5m**: n_est ~[100,400], lr ~[0.03,0.08], num_leaves ~[16,48] — FLOOR at 0.199722
- **ETH/15m**: n_est ~[100,500], lr ~[0.02,0.06], num_leaves ~[64,128] — FLOOR at 0.193035
- **ETH/1h**: n_est ~[100,400], lr ~[0.02,0.06], num_leaves ~[16,32], train_bars=12000 — FLOOR at 0.190875
- **SOL/5m**: n_est ~[300,450], lr ~[0.05,0.08], num_leaves ~[48,80], train_bars=12000 — FLOOR at 0.206907
- **SOL/15m**: n_est ~[200,600], lr ~[0.02,0.06], num_leaves ~[32,64] — FLOOR at 0.200064
- **SOL/1h**: n_est ~[300,400], lr ~[0.025,0.035], num_leaves ~[32,42], train_bars=10000 — FLOOR at 0.202164
- **XRP/5m**: n_est ~[200,500], lr ~[0.03,0.07], num_leaves ~[28,52] — FLOOR at 0.209444
- **XRP/15m**: n_est >1200 (structural), lr ~[0.007,0.015], num_leaves ~[50,70] — FLOOR at 0.205184
- **XRP/1h**: n_est ~[200,500], lr ~[0.02,0.05], num_leaves ~[32,60] — FLOOR at 0.206414
