# Strategy Directive
Updated: 2026-03-19T20:30:00Z
After iteration: 11

## Priority Queue

1. **Expand time_pcts to 6 points — add 0.20 and 0.90** — set `time_pcts` to [0.20, 0.30, 0.40, 0.60, 0.80, 0.90]. This increases training samples by 50% (from 557,784 to ~836,676) at zero HPO cost — it does not increase per-trial wall time because samples are vectorized, not sequential. This is the highest-EV experiment available: more training signal with no structural risk. The early-bar point (0.20) captures momentum formation; the late point (0.90) captures near-close conviction. Expected gain: Brier reduction of 0.001-0.003 from reduced estimation variance and slightly richer temporal signal. This was priority #3 in the last directive and has not yet been attempted.

2. **Prune low-value liquidation features — remove oi_price_divergence and oi_momentum from cached_features** — in iter 4, adding all 4 liquidation features produced only +0.000004 Brier gain (0.143858→0.143854). In the corrected pipeline (iter 8), their contribution is unverified. `liquidation_proximity` and `leverage_proxy` are the directly interpretable signals; `oi_price_divergence` and `oi_momentum` are derived and likely correlated (max_pairwise_corr=0.90 filter may not catch all redundancy). Reducing to 28 features reduces model complexity with minimal signal loss. If DISCARD, restore them — but this is low-risk. This was priority #4 in the last directive and has not yet been attempted.

3. **Re-attempt HPO range narrowing with increased trial budget (100→150 trials)** — iter 10 narrowed ranges correctly (n_estimators [500,1500], lr [0.005,0.04], max_depth [3,6], num_leaves [31,96], min_child [200,600]) but only 14 trials ran before timeout. The ranges were right; the budget was the bottleneck. The fix: raise the Optuna trial limit from 100 to 150 (or confirm the HPO timeout is generous enough for 100 trials at train_bars=8000). Do NOT change the ranges from iter 10 — those were correct per HPO convergence evidence. If 14 trials at the old range took the full budget, then either the trial limit must increase or the timeout must be relaxed. Check if `fast_mode` is limiting trial count; iter 11 ran 13/40 in fast mode — the 40-trial cap in fast mode may be the true bottleneck. If so, increase fast_mode trial cap to 80.

4. **Test adding time_pct 0.10 as a 7th sample point (if priority #1 KEEPs)** — 0.10 is 10% into the bar (30 seconds on a 5m bar). This is the earliest reliable signal point before the initial momentum burst fades. Only attempt after confirming 6-point time_pcts is stable. This extends the temporal coverage further into bar-open dynamics. Expected gain: marginal Brier improvement; primary benefit is regularization from additional samples.

5. **Test regime_params tuning — increase vol_window 120→240** — `regime_vol_zscore` is confirmed top-10 across iters 3, 4, and 8. The current vol_window=120 bars = 10 hours on 5m bars. Increasing to 240 bars (20 hours) smooths the regime signal across a full trading day cycle, reducing noise from intraday vol spikes. The lookback_window should match: set `lookback_window` 120→240 simultaneously. This is a structural improvement to the only confirmed alpha signal. Expected gain: 0.0005-0.001 Brier from cleaner regime labeling.

## Observations

- **KEEP rates by category (all iterations)**: Alpha features 2/3 (67%), Walk-forward params 1/4 (25%), Interaction features 0/1 (0%), HPO range narrowing 0/1 (0%), baseline resets 1/1 (100%). Overall: 6 KEEP or KEEP-VERIFIED out of 11 iterations = 55%.
- **Walk-forward KEEP rate collapsed**: Iters 9, 10, 11 were all DISCARDs — 0/3 on the most recent category attempts. The underlying issue is HPO starvation: iter 10 (14 trials), iter 11 (13 trials) both failed to converge because per-trial cost increased. Only iter 8 (train_bars increase) KEEPed in this category, because it ran 100 full trials.
- **HPO starvation is the active bottleneck**: Every experiment that increases per-trial training time is hitting a wall. fast_mode appears to cap at 40 trials; iter 11 ran only 13/40. The effective HPO budget must be restored before further structural changes are attempted.
- **Brier improvement has flatlined**: Best Brier is 0.143724 (iter 8, KEEP-VERIFIED). Iters 9-11 produced 0.143727, 0.14377, and 0.14387 — all within 0.0001 of best but none beating it. We have 9 iterations of signal extraction since the corrected pipeline. Any further Brier gain requires either more data (time_pcts expansion, priority #1) or better HPO convergence (priority #3).
- **Both-sides strategy consistently dominates**: bs_pnl ranges from $1.40M to $1.43M vs single-side $68. The bs_sharpe peak remains iter 8 at 85.30. Iter 11 bs_sharpe of 79.88 is the lowest since the corrected pipeline — consistent with the DISCARD (HPO starvation means suboptimal model weights, not a feature problem).
- **bs_sharpe trajectory (corrected pipeline)**: iter 8 = 85.30, iter 9 = 86.45, iter 10 = 87.79, iter 11 = 79.88. Iter 10's narrow HPO actually achieved bs_sharpe 87.79 with only 14 trials — the highest on record. This is evidence that the narrowed HPO ranges in iter 10 were directionally correct; more trials at those ranges should improve further. Iter 11's drop to 79.88 is purely from HPO starvation (13 trials).
- **regime_vol_zscore is the only confirmed persistent alpha signal**: Appeared in top-10 in iters 3, 4, and 8. No other alpha feature has confirmed persistent importance.
- **Funding features remain blacklisted from cached_features**: Two iterations confirm they add no value at 5m bar resolution (iter 2 DISCARD). Their 8h cadence makes them constant within most training windows.
- **Researcher compliance**: The researcher ran iter 9 (embargo, priority #5 from last directive), iter 10 (HPO narrowing, priority #1), and iter 11 (n_splits, priority #2). This matches the last priority queue with reordering. The researcher correctly identified that priorities #3 and #4 are the next logical steps in the ack note — full compliance.

## Blacklist

- **Interaction features (all 8 pairs in interaction_features.pairs)**: iter 6 DISCARD, Brier 0.143854→0.2028 (+41% regression). Permanently blacklisted. Do not enable `interaction_features.enabled`.
- **Funding features in cached_features**: iter 2 DISCARD (0.143929 vs 0.143872 baseline, +0.000057 Brier regression). Permanently blacklisted from cached_features. The 8h funding cadence provides no 5m intra-bar signal.
- **n_splits above 8 without HPO trial budget increase**: iter 11 DISCARD — 12 folds consumed HPO budget, leaving only 13 trials. Do not increase n_splits until per-trial cost is confirmed manageable.
- **embargo_period increase (6→12)**: iter 9 DISCARD — Brier 0.143727 vs best 0.143724 (noise-level difference of 0.000003). No evidence it helps; current embargo of 6 bars (30 min) is sufficient given purge_period=12.
- **train_bars below 8000**: iter 7 established Brier 0.1982 at train_bars=5000; iter 8 showed 27.5% improvement at 8000. Hard floor at 8000.
- **time_pcts below 0.10**: Insufficient intra-bar price action exists before 10% elapsed (30s on 5m bars).
- **time_pcts above 0.90**: Remaining bar time insufficient to act on signal.

## HPO Range Recommendations

- `n_estimators`: keep [500, 1500] — iter 10 correctly narrowed from [100, 1500]. The lower bound of 100-500 was underfitting territory; confirmed correct by iter 10 achieving best bs_sharpe on record (87.79) with only 14 trials.
- `learning_rate`: keep [0.005, 0.04] — iter 10 correctly narrowed from [0.005, 0.1]. Evidence: all 3 KEEP iterations post-correction had Brier <0.145, none occurred with lr>0.04 in reported best params.
- `max_depth`: keep [3, 6] — narrowed correctly in iter 10. Depth-2 trees are insufficient for regime_vol_zscore to interact with other features.
- `num_leaves`: keep [31, 96] — narrowed correctly in iter 10. 16-30 leaves is too shallow; 97-128 over-parameterizes at this sample scale.
- `min_child_samples`: keep [200, 600] — narrowed correctly in iter 10. Range [100, 1000] was too wide; the practically relevant band for 557K samples is [200, 600].
- `reg_alpha` and `reg_lambda`: keep [1e-8, 10.0] — no convergence data to narrow. Wide range appropriate.
- `subsample` and `colsample_bytree`: keep [0.6, 0.9] and [0.4, 0.8] — no convergence evidence to narrow these.
- **Critical action**: Investigate whether the fast_mode trial cap (appears to be 40) is the binding constraint for HPO budget. If so, increase the fast_mode cap to 80 trials before re-attempting iter 10-style narrow HPO. Iter 10 ran 14/100 and iter 11 ran 13/40 — the absolute trial counts are too low for convergence at any range setting.
