# Strategy Directive
Updated: 2026-03-20T02:00:00Z
After iteration: 23

## Priority Queue

1. **ETH: test train_bars 10000→14000.** The ETH baseline (iter 23, Brier 0.178243) is 75% higher than the BTC optimum (0.101759) after 22 iterations of tuning. On BTC, the single most impactful structural change was train_bars 5000→8000 (+27.5% Brier gain, iter 8). ETH has a larger asset-specific pattern cycle (more institutional flow, lower retail noise) and likely needs more historical context to capture recurring funding/liquidation regimes. The precedent is exact: BTC at iter 7 had Brier 0.1982 as its "new baseline"; ETH at iter 23 has Brier 0.178243. BTC's first improvement move was extending train_bars. Keep all other knobs identical (time_pcts=[0.30,0.50,0.80], n_splits=8, purge_period=24, embargo_period=6, wide HPO bounds). Expected gain: Brier reduction 0.010-0.025 (estimated 6-14% improvement based on BTC trajectory). If fewer than 25 HPO trials complete, abort and flag as budget-constrained.

2. **ETH: test time_pcts [0.30, 0.50, 0.80] — confirm 3-point optimum transfers.** Before running this explicitly, note that iter 23 already used the 3-point set (identical knobs from BTC). This priority is implicitly satisfied. However, the researcher should verify that the ETH last_run.log confirms exactly 3 time_pcts in play and that the train sample count (185K in iter 23 log) matches expectations. If iter 23 used the wrong time_pcts by accident, re-run the baseline. If confirmed correct, skip to priority #3.

3. **ETH: test regime features — check whether regime_vol_zscore appears in top-10 for ETH.** On BTC, regime_vol_zscore was the only confirmed persistent alpha signal (top-10 across iters 3, 4, 8, 14, 18). Iter 23 researcher_ack explicitly notes "regime_vol_zscore not in top-10 for ETH, tick features dominate." This means ETH has a qualitatively different feature importance profile. Test: increase vol_window and lookback_window from 120→60 (halving) to see if shorter regime windows better capture ETH's higher-frequency volatility transitions. ETH trades at higher velocity than BTC; 120-bar (10-hour) regime windows may be too slow for ETH's dynamics. If regime_vol_zscore enters top-10: mark regime tuning as ETH-productive. If it doesn't: consider disabling regime features for ETH to reduce noise (after confirming Brier impact). This is a direct alpha-contribution test. Do NOT change other knobs.

4. **ETH: add funding features to cached_features (6 features).** On BTC, funding features in cached_features were a DISCARD (iter 2, Brier 0.143929 vs 0.143872 baseline). However, ETH has a structurally different funding dynamics profile: ETH funding rates are more volatile, more responsive to spot/perp divergence, and carry more information at 5m resolution due to higher DeFi activity and staking-related flow. The iter 23 baseline Brier gap (0.178 vs 0.102 on BTC) suggests substantial unexploited structure. Funding features may contribute to ETH in a way they do not for BTC. Gate: run only after priority #1 (train_bars) establishes a more mature ETH baseline. If DISCARD, add to ETH-specific blacklist. If KEEP: ETH and BTC have asymmetric alpha features — document this and use asset-specific configs going forward.

5. **ETH: test purge_period 24 (current BTC-proven setting).** The current ETH config inherited from BTC already has purge_period=24 (set in iter 22). Confirm this is correct in the ETH config. If the ETH baseline at iter 23 was actually run with purge_period=12 (the pre-iter-22 value), then iter 23's Brier 0.178243 understates true ETH performance and re-running with purge_period=24 may provide a small improvement. The researcher_ack for iter 23 does not mention this explicitly. Verify which purge_period value was active during iter 23 before running new ETH experiments.

## Observations

- **KEEP rates by category (all 23 iterations):** Baseline/pipeline correction 2/2 (100%); verification 1/1 (100%); train_bars extension 2/2 (100%); walk-forward purge/embargo 2/4 (50%, iters 9 and 11 DISCARD, iters 22 KEEP and n_splits 12 not yet retested); alpha feature groups 2/3 (67% on BTC, not counting ETH); ETH asset baseline 1/1 (100%); time_pcts adjustment 1/3 (33%, iter 14 KEEP, iters 12 and 21 DISCARD); HPO range narrowing 0/5 (0%, definitive); regime config 0/1 (0%); interaction features 0/1 (0%); feature pruning 0/1 (0%). Overall: 11 KEEP + 1 KEEP-VERIFIED out of 23 attempts = 52%.

- **HPO starvation root cause definitively confirmed as wall-clock timeout (iter 20).** Iters 19 and 20 both ran exactly 29-30 trials regardless of cap (50 vs 55). The binding constraint is training time per trial, not the trial count ceiling. Narrowed HPO ranges do NOT help because per-trial cost is fixed by dataset size and model complexity — the search space reduction does not affect trial duration. This kills the HPO-narrowing strategy permanently. The only lever to get more trials is reducing dataset size (time_pcts fewer points, shorter train_bars — both are blacklisted), or accepting fewer trials. At 30 trials, the wide search space is adequate: iter 8 and iter 14 both achieved best Brier improvements with 34 and 34 trials respectively at wide bounds.

- **Priority #2 (time_pct 0.10) definitively failed (iter 21).** Brier 0.166316 vs best 0.101829, a 63% regression. Early-bar signal (first 10% = ~30 seconds of a 5m bar) is not informative for intra-bar direction prediction. The 3-point set [0.30, 0.50, 0.80] is confirmed optimal. No further time_pcts experiments are warranted for BTC or ETH unless a novel theoretical rationale exists.

- **ETH both-sides strategy is extraordinary.** Iter 23 bs_sharpe 253.47, bs_pnl $14,029,542. This is a ~2.7x multiple over the previous bs_sharpe record of 93.84 (BTC iter 22). ETH win_rate is only 0.5319 (barely above coin-flip) meaning the both-sides market-making strategy profits from spread capture and volume, not directional accuracy — a fundamentally different profit mechanism than BTC (win_rate 0.8697). ETH should be the primary optimization target going forward.

- **Brier trajectory for BTC has plateaued.** Last 6 BTC iterations: 0.101837 (iter 18), 0.102175 (iter 19, DISCARD), 0.102175 (iter 20, DISCARD), 0.166316 (iter 21, DISCARD), 0.101759 (iter 22, KEEP — marginal). BTC net Brier improvement over the plateau period (iters 18-22) is 0.000078. The learning curve is flat. ETH has a 0.076-point Brier gap relative to BTC's optimum — structural improvements are much more accessible on ETH.

- **ETH tick features dominate (iter 23 researcher_ack).** Unlike BTC where regime_vol_zscore is the key alpha signal, ETH's top-10 is dominated by tick-level features. This suggests ETH's intra-bar dynamics are driven by microstructure rather than macro regime state — consistent with ETH's higher DeFi/AMM activity creating more regular tick-level patterns.

- **OOS accuracy gap between BTC and ETH.** BTC OOS accuracy 0.8598 (iter 22), ETH OOS accuracy 0.7363 (iter 23). The 12-point gap is expected for a baseline vs optimized model. Given that ETH win_rate (0.5319) is far below accuracy (0.7363), the model is predicting direction accurately but the both-sides strategy is capturing spread regardless of direction — these are decoupled metrics for ETH.

- **bs_pnl magnitude ordering (latest values):** ETH $14.0M (iter 23) >> BTC $583K (iter 22). The 24x difference is partly explained by higher ETH volatility (more extreme intra-bar moves = wider market-sim payoffs), more trades (45,116 vs 43,721), and possibly a more favorable regime distribution in the test window. Treat absolute ETH PnL as potentially overfitted to the specific test period — Sharpe is the more robust metric.

- **Researcher compliance (iters 19-23):** Full compliance. Iter 19 = priority #1 (narrowed HPO, 55 trials). Iter 20 = reasonable re-attempt to confirm starvation mechanism before abandoning the priority. Iter 21 = priority #2 (time_pct 0.10). Iter 22 = priority #3 (purge_period 24). Iter 23 = auditor SWITCH ETH directive (correct override of remaining BTC priorities). The sequence demonstrates sound experimental discipline.

## Blacklist

- **Interaction features (all 8 pairs):** iter 6 DISCARD, Brier 0.1437→0.2028 (+41% regression). Permanent. Do not enable `interaction_features.enabled` under any condition for any asset.
- **Funding features in BTC cached_features:** iter 2 DISCARD (0.143929 vs 0.143872 baseline). BTC-specific. 8h funding cadence provides no 5m intra-bar signal for BTC. Not yet tested for ETH — ETH funding is not blacklisted.
- **HPO range narrowing (all configurations):** iters 10, 13, 15, 19, 20 — 0/5 KEEP rate. Root cause confirmed as wall-clock timeout (iter 20). Narrowed ranges with any trial cap do not improve outcomes. Permanent blacklist.
- **time_pct 0.10 (early-bar sampling):** iter 21 DISCARD, Brier 0.166316 (+63% regression). Not informative at 5m resolution. Permanent blacklist for both BTC and ETH.
- **time_pcts expansion beyond 3 points:** iters 12 and 21 both DISCARD (HPO starvation + signal degradation). The 3-point set [0.30, 0.50, 0.80] is confirmed optimal. Do not expand.
- **embargo_period increase 6→12:** iter 9 DISCARD — noise-level difference (0.143727 vs 0.143724). No benefit at this resolution.
- **n_splits above 8 (without budget confirmation):** iter 11 DISCARD (13 HPO trials at n_splits=12). Gate remains: confirm >35 trial completions before attempting. Currently irrelevant while ETH is the focus.
- **train_bars above 10000 on BTC:** iter 18 confirmed learning curve saturation (0.000008 Brier gain). BTC-specific ceiling.
- **train_bars below 8000 on BTC:** iter 8 hard floor (-27.5% Brier at 5000 bars). Do not revert for BTC.
- **Static manual feature pruning:** iter 16 DISCARD (Brier 0.101896 vs 0.101837). oi_price_divergence and oi_momentum are net contributors for BTC.
- **regime_params vol_window/lookback_window above 120 on BTC:** iter 17 DISCARD (Brier identical at 240 bars). 120-bar window is optimal at 5m for BTC. NOT yet tested for ETH — reducing to 60 is an active priority (#3).

## HPO Range Recommendations

- `n_estimators`: wide bounds [100, 1500] — confirmed that narrowing produces no gain (HPO starvation). Wide bounds are fine.
- `learning_rate`: keep [0.005, 0.1] — narrowing to [0.005, 0.04] was never confirmed beneficial due to starvation.
- `max_depth`: keep [2, 6] — no clean convergence data under non-starvation conditions.
- `num_leaves`: keep [16, 128] — same reasoning as max_depth.
- `min_child_samples`: keep [100, 1000] — same reasoning.
- `reg_alpha` and `reg_lambda`: keep [1e-8, 10.0] — no convergence data.
- `subsample`: keep [0.6, 0.9] — no convergence data.
- `colsample_bytree`: keep [0.4, 0.8] — no convergence data.
- **Critical note:** The HPO starvation analysis (iters 19-20) proves that 30 trials at wide bounds is mechanically equivalent to 30 trials at narrow bounds — the wall-clock constraint dominates. Do not attempt further HPO range experiments. Accept 28-32 trials as the natural budget and rely on wide bounds to cover the search space broadly.
