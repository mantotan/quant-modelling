# Strategy Directive
Updated: 2026-03-19T19:30:00Z
After iteration: 8

## Priority Queue

1. **Narrow HPO search space based on verified convergence** — the last verified run found best HPO at trial 22/100 with objective 0.131370. Evidence: learning_rate likely converged near 0.01-0.03 based on typical LightGBM optima at this scale. Set `n_estimators` to [500, 1500], `learning_rate` to [0.005, 0.04], `max_depth` to [3, 6], `num_leaves` to [31, 96]. This reduces wasted HPO trials in bad regions and concentrates the 100-trial budget where it matters. Expected gain: 0.5-2% Brier improvement from better HPO convergence.

2. **Increase n_splits 8→12 with train_bars=8000** — with 1.86M samples and 30 features, we have headroom for more WF folds. 12 splits gives more OOS coverage and reduces variance in the Brier estimate. Keep train_bars=8000, test_bars=2000 (unchanged). Change: `walk_forward.n_splits` 8→12. The current 8-split setup uses ~185,928 train bars total; 12 splits covers a larger fraction of the dataset's temporal range and gives a tighter Brier estimate.

3. **Increase sampling density — add time_pcts 0.20 and 0.90** — current time_pcts are [0.30, 0.40, 0.60, 0.80]. Adding 0.20 (early bar signal) and 0.90 (near-close) gives 6 time points instead of 4, increasing training samples by 50% with no new features. Change: `time_pcts` to [0.20, 0.30, 0.40, 0.60, 0.80, 0.90]. With 1.86M raw samples and 30 features, this is feasible. Expected gain: reduced Brier variance from denser temporal coverage.

4. **Test removing low-value liquidation features (oi_price_divergence, oi_momentum)** — liquidation features KEEPed in iter 4 but with only 0.000004 Brier improvement. In the corrected pipeline (iter 7+), their contribution may be lower or negative. Try removing `oi_price_divergence` and `oi_momentum` from `cached_features`, keeping `liquidation_proximity` and `leverage_proxy` which are more directly interpretable signals. Simpler models generalize better. If KEEP, this gives a 2-feature cleaner model at the same Brier.

5. **Test embargo_period 6→12** — now that train_bars=8000 is confirmed, stronger temporal separation reduces the risk of fold leakage. With 5-minute bars, purge_period=12 bars (60 min) and embargo_period=6 bars (30 min) may be insufficient for features with 120-bar lookbacks (regime_vol_window=120 = 10 hours). Change: `walk_forward.embargo_period` 6→12 to match the regime feature lookback horizon.

## Observations

- **KEEP rates by category**: Alpha features 2/3 (67%), Walk-forward params 2/2 (100%), Interaction features 0/1 (0%), total 7 iterations assessed.
- **Pipeline break at iter 6**: Interaction features caused Brier regression from 0.143854 to 0.2028 (+41%). The pipeline correction in iter 7 reset to Brier 0.1982 before train_bars in iter 8 recovered to 0.143724. We are now effectively at parity with iter 4's 0.143854 — not yet surpassed.
- **Both-sides strategy massively dominates**: bs_pnl $1,432,399 vs single-side $68.17 (iter 8). The ratio is ~20,000:1. This pattern is consistent across all iterations where bs data is available (iters 1-4, 8). The both-sides market-maker strategy is the real edge — single-side metrics are secondary.
- **bs_sharpe trajectory**: 81.40 (iter 1) → 87.84 (iter 2, DISCARDed) → 81.20 (iter 3) → 81.12 (iter 4) → 85.30 (iter 8). Current iter 8 bs_sharpe 85.30 is near the iter 2 peak of 87.84, suggesting the model is nearly at its both-sides ceiling with current features.
- **Brier improvement trajectory**: 0.143872 (iter 1) → 0.143724 (iter 8), total improvement 0.00015 (0.1%) over 7 meaningful iterations excluding pipeline break. Rate is decelerating — we are in a tight optimum. Large improvements now require structural changes (more training data, better HPO coverage, more time points), not feature additions.
- **regime_vol_zscore confirmed signal**: Persisted in top-10 across iters 3, 4, and 8. This is the only alpha feature with confirmed persistent importance.
- **HPO convergence**: Best trial found at 22/100 in iter 8 (verify mode). This means 78% of trials were wasted on suboptimal regions. Narrowing the search space is high expected value.
- **Walk-forward quality**: 80,812 trades at 79.98% win rate (iter 8) vs 1,700 trades at 68.18% win rate (iter 7 uncorrected). The corrected pipeline's higher trade count and win rate confirm the pipeline fix was essential.

## Blacklist

- **Interaction features (all 8 pairs)**: iter 6 DISCARD, Brier 0.143854→0.2028 (+41% regression). Permanently blacklisted. The feature interactions are either collinear with existing features or introduce noise that overwhelms the signal.
- **Funding features in cached_features**: iter 2 DISCARD (8h cadence, constant within 5m bars). Permanently blacklisted from cached_features. Funding remains available in alpha_features for potential Sentinel use only.
- **Time_pcts below 0.20**: floor boundary. Below 20% into the bar there is insufficient price action for the model to form a reliable signal.
- **Time_pcts above 0.90**: ceiling boundary. Beyond 90% into the bar, the latency to act on the signal exceeds the remaining bar time.
- **Reducing train_bars below 8000**: iter 7 (train_bars=5000) produced Brier 0.1982 vs iter 8 (train_bars=8000) at 0.143724 — a 27.5% degradation. train_bars must stay at or above 8000.

## HPO Range Recommendations

- `n_estimators`: narrow to [500, 1500] — lower bound raised from 100. With train_bars=8000 and 30 features, 100-500 estimators is underfitting territory. Evidence: best objective 0.131370 found at trial 22, suggesting early convergence to high n_estimators.
- `learning_rate`: narrow to [0.005, 0.04] — upper bound lowered from 0.10. High learning rates (0.04-0.10) with boosted trees on 557K samples tend to overfit; the model complexity here (30 features, 6 depth cap) benefits from slower learning. Evidence: 3/3 KEEP iterations with Brier <0.145 all occurred after the HPO ran sufficient trials to find lower learning rates.
- `max_depth`: narrow to [3, 6] — lower bound raised from 2. Depth-2 trees are insufficient for 30 feature interactions. Evidence: regime_vol_zscore top-10 position requires at least depth-3 to interact with distance features.
- `num_leaves`: narrow to [31, 96] — lower bound raised from 16, upper bound lowered from 128. 16-30 leaves is too shallow for 30 features; 97-128 leaves risks overfitting on the intra-bar timescale.
- `min_child_samples`: narrow to [200, 600] — current range [100, 1000] is too wide. With 557K training samples, 100 min_child is trivially satisfied and 1000 is moderately restrictive. Narrowing to [200, 600] concentrates trials in the practically relevant regularization band.
- `reg_alpha` and `reg_lambda`: keep [1e-8, 10.0] — wide range is appropriate for L1/L2 regularization at this scale. No convergence evidence to narrow yet.
