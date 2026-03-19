# Strategy Directive
Updated: 2026-03-19T11:00:00Z
After iteration: 12

## Priority Queue
1. **Drop 0.10 from time_pcts** — the pruning strategy has 75% KEEP rate (3/4). Current time_pcts [0.10, 0.20, 0.30, 0.40, 0.60, 0.80]. At 10% elapsed (~30s into 5m), tick features are still weak. Each prior drop yielded: -3.3%, -4.7%, -5.8% Brier improvement. Risk: 0.10 has real tick signal (partial range, trade intensity). If this DISCARDs, the pruning strategy is exhausted.
2. **Walk-forward n_splits 5→8** — more CV folds with brier-primary should give even more stable Brier estimates. test_bars=2000 was a KEEP. The brier-primary objective now actually differentiates trials (hpo_objective=0.168, no longer 0.0). More folds should help further.
3. **Lower learning_rate upper bound to 0.05** — the brier-primary optimum found lr=0.005 (the floor). The HPO still explores up to 0.1 which wastes trials. Narrowing lr [0.005, 0.05] concentrates search near the productive low-learning-rate regime. NOTE: this is range narrowing, which was blacklisted for reg/tree params — but those failed because the sharpe-primary optimum was stuck. The brier-primary optimum is fundamentally different, so HPO narrowing may now help.
4. **Increase min_child_samples lower bound to 500** — brier-primary optimum found min_child=726-951. The current range [100, 1000] wastes trials on low values. Narrowing to [500, 1000] concentrates search in the productive high-regularization regime.
5. **Try ETH asset** — 12 consecutive BTC iterations. The time_pcts + brier-primary improvements should transfer to ETH. Run `--asset ETH` to validate universality. If ETH also benefits → the changes are structural, not BTC-specific overfitting.

## Observations
- **Two-phase discovery**: Phase 1 (sharpe-primary) optimized via data quality (time_pcts pruning). Phase 2 (brier-primary) optimized via model structure (slow learning, simple trees). Both independently productive.
- **KEEP rates**: Objective tuning 2/2 (100%), walk-forward 1/1 (100%), sampling density 3/4 (75%), feature selection 0/1 (0%), HPO range changes 0/3 (0%)
- **Brier trajectory**: 0.2055 → 0.1989 → 0.1893 → 0.1886 → 0.1777 → 0.1759. Accelerated in phase 2 — the brier-primary change was transformative.
- **ECE trajectory**: 0.0461 → 0.0474 → 0.0402 → 0.0342 → 0.0300 → **0.0071**. Dramatic improvement when switching to brier-primary. ECE 0.007 is exceptional — well below 0.05 acceptance.
- **Best params shifted radically**: sharpe-primary found fast-learning big-tree models (lr=0.086, leaves=83). brier-primary found slow-learning simple-tree models (lr=0.005, leaves=33). The model is fundamentally different — simpler, more regularized, better calibrated.
- **HPO range changes remain unproductive (0/3)**: Both narrowing (iters 2-3) and widening (iter 12) failed. The TPE sampler finds good params regardless. Only data and objective changes create real improvement.
- **Both-sides PnL tracking single-side**: $86K → $358K → $758K → $1.03M → $1.17M → $1.82M. Consistent amplification but highly sensitive to model changes.
- **Alpha features still inactive**: All 30 alpha features are in the code but the data hasn't been downloaded. Running `scripts/download_funding.py` and regenerating the .npz cache is the next major capability uplift.
- **Researcher compliance**: Excellent. Followed all strategist priorities in order (skipped #2 initially, came back to it). Autonomous iteration (n_estimators widening) was a reasonable but unproductive choice — consistent with the pattern that HPO range changes don't help.

## Blacklist
- HPO range narrowing (regularization): iters 2 DISCARD
- HPO range narrowing (tree structure): iter 3 DISCARD
- HPO range widening (n_estimators to 3000): iter 12 DISCARD
- Time_pcts densification (adding 0.50): iter 10 DISCARD — neutral
- Feature selection (drop hour_sin/cos): iter 6 DISCARD — neutral
- **Generic: any HPO range change** — 0/3 across all attempts. The search space is fine.

## HPO Range Recommendations
- **learning_rate**: Consider [0.005, 0.05] — brier-primary finds lr=0.005, but only recommend this AFTER one more brier-primary iteration confirms convergence
- **min_child_samples**: Consider [500, 1000] — same caveat: wait for convergence confirmation
- Do NOT widen any range — iter 12 showed widening n_estimators was counterproductive
- The n_estimators range [100, 1500] is correct — the brier-primary optimum uses ~1400, giving headroom but not waste
