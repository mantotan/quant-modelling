# Strategy Directive
Updated: 2026-03-19T10:00:00Z
After iteration: 8

## Priority Queue
1. **Drop 0.05 from time_pcts** — continue the proven pruning strategy. Currently [0.05, 0.10, 0.20, 0.30, 0.40, 0.60, 0.80]. The 5% point (~15s into 5m bar) has partial tick info but still weak. Each prior time_pcts drop improved Brier: -3.34% (drop 0.003), -4.72% (drop 0.01). Diminishing returns expected but still the highest-probability KEEP. If this fails, the pruning path is exhausted.
2. **Add 0.50 time point** — try [0.05, 0.10, 0.20, 0.30, 0.40, 0.50, 0.60, 0.80]. Denser coverage in the 40-60% range where the model transitions from tick-dominated to history-dominated features. Different from pruning — this ADDS data rather than removing it.
3. **Walk-forward: increase n_splits from 5 to 8** — more CV folds give lower-variance Brier estimates during HPO. test_bars=2000 was a KEEP; more folds is the same category. Evidence: HPO still converges to identical params → the evaluation signal needs more stability, not different params.
4. **Switch to ETH** — 8 consecutive iterations on BTC. Per researcher rules, after 15+ iterations switch assets. But trying ETH early could validate whether the time_pcts + test_bars improvements transfer across assets. If ETH also improves → the changes are universal, not BTC-specific.
5. **Try brier-primary objective** — switch objective.primary from "sharpe" to "brier" for 1-2 iterations. The sharpe-primary objective always returns 0.0 (even with threshold=0.20). A brier-primary run would directly optimize for calibration, potentially finding a different HPO optimum. Evidence: all 8 runs converge to identical best_params — changing the objective function is the only way to break out of this convergence.

## Observations
- **KEEP rates**: Sampling density: 2/2 (100%), Walk-forward: 1/1 (100%), Objective: 1/1 (100%), Feature selection: 0/1 (0%), HPO range: 0/2 (0%)
- **Brier trajectory decelerating**: -3.34% → -4.72% → -0.36% → -0.002%. The 8.2% total improvement from baseline is almost entirely from time_pcts pruning (iters 4-5). Walk-forward and objective tuning gave marginal gains.
- **ECE dramatically improved**: 0.0461 → 0.0342 (-25.8%). The calibration quality improvement comes mostly from test_bars=2000 (iter 7), not time_pcts changes. ECE is now well below the 0.05 acceptance threshold.
- **Best params fully converged**: All 8 runs find n_estimators=624, lr=0.086, max_depth=5, num_leaves=83. The TPE sampler is in a local optimum. Only changing the objective function or the data itself (features, sampling) can break this.
- **Both-sides strategy stabilized**: After volatile early iterations (-$470K to +$358K), recent runs consistently show $750K-$1.04M. The both-sides PnL tracks single-side improvements but with 10-30x amplification.
- **Alpha features still inactive**: Need to run `download_funding.py` and `download_deribit_iv.py` to populate alpha stores, then regenerate the .npz cache. This is the biggest untapped improvement vector.
- **Single-side Sharpe is unrealistically high**: 36.03 at iter 8. This likely reflects the fixed-bet backtester structure rather than true risk-adjusted returns. Do not optimize for Sharpe — focus on Brier and ECE.

## Blacklist
- HPO range narrowing (regularization): iter 2 DISCARD
- HPO range narrowing (tree structure): iter 3 DISCARD
- Feature selection (drop hour_sin/cos): iter 6 DISCARD — marginal, not worth revisiting
- Any HPO range narrowing: generic blacklist — params are converged, narrowing only hurts

## HPO Range Recommendations
- **No changes** — ranges are fine. The TPE sampler converges to the same optimum regardless. Research leverage is in data and objective changes.
- **Future direction**: Once alpha features are in the cache (after data download + regen), the feature space will change from 23 to ~50 features. This will break the current HPO convergence and create real optimization surface to explore. That's when HPO range tuning becomes relevant again.
