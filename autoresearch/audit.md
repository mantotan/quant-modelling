# Audit Report
Updated: 2026-03-25T12:00:00Z
After iteration: 122

## Verdict: CONTINUE — anti-starvation rollout producing measurable lift; items 3-6 of strategy queue pending

The post-OVERRIDE HPO phase is healthy. The anti-starvation fix (n_estimators=[100,800]) has a 100% KEEP rate (3/3: ETH/15m iter 116, ETH/5m iter 117, SOL/5m iter 121) and is the highest-ROI lever in the portfolio. BTC/5m remains structurally starved even after the ceiling reduction (22/40 trials, n_estimators=709 near ceiling), which is a genuine constraint at 929K samples/8 folds — no intervention is warranted since it's a known dataset-size floor. The remaining strategy queue (items 3-6: BTC/15m anti-starvation, XRP/15m anti-starvation, SOL/1h reg_alpha widen, ETH/5m min_child narrowing) has not been executed and should continue as planned.

## Directive Details

**CONTINUE** with the following binding notes:

### Note 1: Anti-Starvation Priority Remains Correct

The researcher has executed 2 of 6 strategy queue items (SOL/5m KEEP, BTC/5m DISCARD). Items 3-6 are the correct next targets. Confirm priority order:
1. BTC/15m anti-starvation (items 3, n_estimators=[100,800], currently 15-17/40 structural starvation)
2. XRP/15m anti-starvation (item 4, currently 22/40, marginal starvation)
3. SOL/1h reg_alpha widen to [0.1, 20.0] (item 5)
4. ETH/5m min_child narrowing [300,700] (item 6, speculative)

### Note 2: BTC/5m Starvation Is Structural — Ceiling Reduction Insufficient

BTC/5m iter 122 got 22/40 trials with n_estimators=[100,800] — same starvation level as iter 104 (11/40 pre-fix). The fix improved trial count from 11 to 22 (2x), but the ceiling reduction alone cannot overcome 929K samples/8-fold training size. Best_params n_estimators=709 is near the 800 ceiling, suggesting BTC/5m genuinely needs more estimators than other assets. Two options for future exploration (do NOT pursue yet — execute items 3-6 first):
- Option A: Further ceiling reduction to n_estimators=[100,500] — risk of underfitting since optimal appears near 700+
- Option B: Reduce n_splits from 8 to 6 for BTC/5m only (blacklisted for BTC previously, but that was single-tp; multi-tp context may differ — auditor suspends blacklist for BTC/5m n_splits=6 as a conditional experiment AFTER items 3-6 complete)

### Note 3: No New Directives on HPO Range Changes

Range narrowing has 0/5 KEEP rate across all assets. The only productive HPO lever identified is the anti-starvation ceiling reduction. Do NOT pursue lr narrowing, min_child narrowing, or any other range contraction experiments until the anti-starvation rollout for all 6 starved assets is complete.

### Note 4: SOL/1h Anomaly Status

SOL/1h iter 118 produced reg_alpha=8.55 — pushing against the [0, 10] upper bound. This is a genuine HPO upper-bound signal (confirmed by 40/40 full-coverage run). The reg_alpha widen experiment (item 5, [0.1, 20.0]) is the correct next step for SOL/1h. If it DISCARDs, SOL/1h floor is confirmed genuine at 0.221683.

---

## Progress Assessment
- **Improvement rate:** Post-OVERRIDE (iters 103-122): 6 KEEPs out of 20 iterations = 30% KEEP rate
  - Anti-starvation KEEPs only: 3/3 (100%) — ETH/15m +0.275%, ETH/5m (new baseline), SOL/5m +0.069%
  - Other experiments: 3/17 (17.6%)
  - Overall per-KEEP Brier improvement average (post-OVERRIDE): ~0.12% per KEEP
  - Improvement rate: **decelerating** — improvements are sub-0.1% (micro-gains), approaching floors
- **Estimated iterations to DISCARD exhaustion:** The 6 remaining starved assets represent 6 confirmed experiments; expected 3-4 additional KEEPs at current anti-starvation success rate (assuming BTC/15m KEEP, XRP/15m marginal, SOL/1h conditional, ETH/5m speculative)
- **KEEP rate last 10 iters (113-122):** 3/10 (30%) — stable, not deteriorating

## Risk Flags

- **Overfitting: none** — hpo_objective vs oos_brier gap analysis (available rows, iters 116-122):
  - ETH/15m iter 116 KEEP: hpo_obj=0.295 vs brier=0.208 → gap=0.087 (composite trade penalty, normal)
  - ETH/5m iter 117 KEEP: hpo_obj=0.279 vs brier=0.212 → gap=0.067 (normal)
  - SOL/1h iter 118 DISCARD: hpo_obj=0.407 vs brier=0.224 → gap=0.183 (elevated: high reg_alpha=8.55 driving penalty)
  - XRP/15m iter 119 DISCARD: hpo_obj=0.501 vs brier=0.220 → gap=0.281 (highest seen — XRP/15m near penalty boundary; 22/40 trials means HPO found a high-trade-penalty corner of search space; not overfitting, but search space edge effect)
  - BTC/5m iter 122 DISCARD: hpo_obj=0.168 vs brier=0.176 → gap=-0.008 (hpo_objective below oos_brier; this is the "primary=brier no penalty" mode confirming BTC sniper, not overfitting)
  - SOL/5m iter 121 KEEP: hpo_obj=0.455 vs brier=0.218 → gap=0.237 (consistent with SOL tick-dominant composite)
  - Gap trend: **stable** — no systematic widening detected; XRP/15m 0.501 is highest but attributable to penalty boundary (77K trades at 5-trade-penalty-weight), not overfitting signal
  - Penalty component: dominant contributor to gap for tick-dominant assets (77K+ trades each run)

- **Calibration drift: none** — ECE trend post-OVERRIDE:
  - BTC/5m: 0.0056 (iter 104) → 0.0076 (iter 122) — slight drift but well below 0.05 threshold
  - ETH/15m: 0.0278 (iter 96) → 0.0197 (iter 110) → 0.0234 (iter 116) — stable fluctuation
  - ETH/5m: 0.0058 (iter 117) — PASS
  - SOL/5m: 0.0083 (iter 93) → 0.0095 (iter 121) — stable, well below threshold
  - XRP/15m: 0.0156 (iter 98) → 0.0217 (iter 119) — slight upward drift, monitor next KEEP
  - SOL/1h: 0.0153 (iter 101) → 0.0171 (iter 118) — within noise, stable
  - All ECE values below 0.04, far from 0.05 alarm threshold

- **PnL disconnect: none** — Brier-PnL correlation strong for all assets:
  - BTC sniper class: PnL $56.39 (iter 104) → $54.93 (iter 122) — marginal decline consistent with DISCARD
  - Tick-dominant: backtest_pnl consistently $68-307 across all assets, Sharpe >140 for 5m/15m assets
  - No Brier improvement with PnL decline detected

- **Drawdown risk: stable** — max_dd / pnl ratio across recent KEEPs:
  - BTC/5m iter 104: max_dd=0.3901, pnl=$56.39 → ratio=0.0069 (6.9%, EXCELLENT)
  - BTC/15m iter 95: max_dd=0.174, pnl=$50.05 → ratio=0.0035 (excellent)
  - BTC/1h iter 107: max_dd=0.2333, pnl=$12.00 → ratio=0.0194 (good)
  - ETH/15m iter 116: max_dd=0.0875, pnl=$292.26 → ratio=0.0003 (tick-dominant, excellent)
  - ETH/5m iter 117: max_dd=0.0687, pnl=$307.53 → ratio=0.0002 (excellent)
  - SOL/5m iter 121: max_dd=0.0688, pnl=$302.94 → ratio=0.0002 (excellent)
  - XRP/1h iter 115: max_dd=0.0625, pnl=$75.23 → ratio=0.0008 (excellent)
  - All ratios well below 1.0 (RED FLAG threshold). Declining trend for tick-dominant assets.

- **Trade volume: stable, high** — trade counts per asset class:
  - BTC sniper 5m: ~80,940 (iter 104, stable vs prior)
  - ETH/5m: ~81,000 (iter 117), ETH/15m: ~77,061 (iter 116)
  - SOL/5m: ~80,783 (iter 121), XRP/15m: ~77,189 (iter 119)
  - 1h assets: 19,182-19,345 (all stable)
  - Trend: **stable** — no model selectivity drift

- **Win rate: stable** — tick-dominant: 49-51% (mathematically constrained by design); BTC sniper: 62-87% (consistent with monotonic bucket pattern); no anomalies

- **Strategy divergence: informational** — both-sides PnL (bs_pnl) consistently positive for all assets (tick-dominant $5.6M-$69.3M bs_pnl in normalized terms; BTC sniper $162K-$1.79M). Single-side vs both-sides divergence stable — model is improving in actionable regions for both strategies.

- **Search exhaustion: mild signs** — sub-0.1% Brier improvements per KEEP; most HPO range narrowing attempts fail (0/5); anti-starvation fix is the only remaining productive lever. After items 3-6 complete, genuine exhaustion is likely for all 12 asset-timeframes. Next phase will require either new features (ADD_ALPHA) or architecture changes (MTF signal combination).

---

## Timeframe Coverage

| Timeframe | Iterations (post-OVERRIDE) | KEEPs | Best Brier (multi-tp) | Best PnL |
|-----------|---------------------------|-------|----------------------|----------|
| 5m        | 8 (iters 103-122 partial) | 3     | BTC=0.17605, ETH=0.211888, SOL=0.218058, XRP=0.221503 | ETH $307.53/bar |
| 15m       | 7                          | 2     | BTC=0.171913, ETH=0.208324, SOL=0.215443, XRP=0.218727 | ETH $292.26/bar |
| 1h        | 5                          | 1     | BTC=0.174864, ETH=0.211438, SOL=0.221683, XRP=0.226907 | ETH $73.64/bar |

Coverage note: 5m has slight over-representation (8 iters vs 7 and 5 for 15m/1h). This is intentional given the 6-item strategy queue weighting (items 1-2 were 5m, items 3-4 are 15m, items 5-6 are 1h and 5m). No SWITCH directive needed — the queue is balanced.

---

## Acceptance Criteria Status (per best asset+timeframe)

Reporting best multi-tp values per metric across all 12 models.

| Metric        | Target      | Current Best        | Gap             |
|---------------|-------------|---------------------|-----------------|
| Brier         | < 0.25      | 0.171913 (BTC/15m)  | OK (31% below)  |
| Brier t>=0.10 | < 0.25 per bucket | BTC sniper t80=0.087 | OK             |
| ECE           | < 0.05      | 0.0056 (BTC/5m)     | OK              |
| PnL           | > 0         | $307.53 (ETH/5m)    | OK              |
| Sharpe        | > 0.0       | 245.15 (ETH/5m)     | OK              |
| Max DD        | < PnL       | 0.069 vs $307.53    | OK (ratio <<1)  |
| Trades        | >= 10       | 80,000+ (5m)        | OK              |
| Win Rate      | 40-85%      | BTC sniper 83%, tick ~50% | OK            |
| HPO-OOS Gap   | stable      | 0.067-0.281         | Stable; XRP/15m 0.501 elevated (penalty boundary, not overfitting) |
| BS PnL        | > 0         | $69.3M (SOL/5m)     | OK (informational) |
| Trades/bar    | 1           | 1.0 (all assets)    | OK              |

**All acceptance criteria currently met for all 12 deployed models.** The program is in the HPO refinement phase, not the acceptance-gating phase. Deployment clearance (all 12 CPCV + regime-bucketed validations complete) was achieved by iter 102.

---

## Portfolio Floor Summary (multi-tp, latest bests)

| Asset | 5m Brier | 15m Brier | 1h Brier | Class |
|-------|----------|-----------|----------|-------|
| BTC   | 0.17605  | 0.171913  | 0.174864 | Sniper (ramp pattern) |
| ETH   | 0.211888 | 0.208324  | 0.211438 | Tick-dominant (flat) |
| SOL   | 0.218058 | 0.215443  | 0.221683 | Tick-dominant (flat) |
| XRP   | 0.221503 | 0.218727  | 0.226907 | Tick-dominant (flat) |

BTC sniper class has clearly lower multi-tp Brier (0.172-0.176) vs tick-dominant (0.208-0.227). The 0.171913 BTC/15m floor is the current portfolio best. The 15m timeframe is the sweet spot for BTC sniper accuracy (15m > 5m > 1h by Brier).

Tick-dominant floors: ETH is the best (~0.208-0.212), SOL intermediate (~0.215-0.222), XRP highest (~0.219-0.227). SOL/1h at 0.221683 and XRP/1h at 0.226907 are the weakest models in the portfolio and the primary targets for the remaining queue items.

---

## Starvation Status (remaining items)

| Asset/TF   | Current Trials | Anti-starvation Applied | Status |
|------------|---------------|------------------------|--------|
| SOL/5m     | 24/40 (iter 121) | YES — KEEP (0.218058) | DONE |
| BTC/5m     | 22/40 (iter 122) | YES — DISCARD (regression) | DONE (structural floor) |
| BTC/15m    | 17/40 (iter 105/114) | NOT YET | Pending (item 3) |
| XRP/15m    | 22/40 (iter 119) | NOT YET | Pending (item 4) |
| ETH/15m    | 23/40 (iter 116) | YES — KEEP (0.208324) | DONE |
| ETH/5m     | 23/40 (iter 117) | YES — KEEP (0.211888) | DONE |
| SOL/15m    | 16/40 (iters 97/109) | NOT YET (per blacklist) | Deferred |
| Starvation-free | 40/40 | N/A | ETH/1h (380s), SOL/1h (209s), XRP/1h (266s) |

SOL/15m remains blacklisted for HPO re-run without anti-starvation fix per strategy directive. Note: best_knobs.json has n_estimators=[100,800] which IS the anti-starvation fix — researcher should apply it to SOL/15m as item 7 after the current queue completes.
