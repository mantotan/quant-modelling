# Strategy Directive
Updated: 2026-03-19T12:10:00Z
After iteration: 16

## AUDITOR OVERRIDE ACTIVE
The auditor has issued **SWITCH ETH for 5 iterations** (audit after iter 16).
All priority queue items below are for AFTER the ETH validation is complete.

## Priority Queue (ETH Phase — iterations 17-21)
1. **ETH baseline** — run with current best_knobs.json unchanged, `--asset ETH`. This is the first ETH run — auto-KEEP as baseline. Establishes ETH reference metrics.
2. **ETH iteration 2-5** — run with `--asset ETH`, NO knob changes. The purpose is to validate that the BTC-optimized config works on ETH, not to tune ETH-specific params. All 5 runs should use identical knobs. KEEP/DISCARD compare within ETH results only.

## Priority Queue (Post-ETH — iterations 22+)
1. **Download funding rate data** — run `scripts/download_funding.py` to populate `data/raw/funding/`. Then regenerate .npz cache with `scripts/train_pulse_v2.py --asset BTC --timeframe 5m` (delete old cache first). This adds 6 funding features to the training data. This is the biggest untapped improvement vector.
2. **Continue time_pcts exploration on ETH** — if ETH baseline is good, try same pruning strategy there.
3. **Walk-forward train_bars 5000→8000** — more training data per fold. Untried category.
4. **Subsample narrowing [0.7, 0.9]** — brier-primary optimum found subsample ~0.80. Concentrate search.

## Observations
- **16 iterations complete**: 10 KEEPs (62.5%), Brier 0.2055→0.1439 (-30.0%)
- **ALL acceptance criteria met** as of iter 15 (verified: DD 28.7% < 30%)
- **Time_pcts pruning exhausted**: [0.30, 0.40, 0.60, 0.80] is the optimal set. Floor found at iter 16.
- **Brier-primary objective was transformative**: Changed HPO optimum entirely — from fast-learning/big-tree to slow-learning/simple-tree models
- **Alpha features still inactive**: Biggest remaining improvement opportunity
- **Researcher compliance**: Excellent throughout. Followed all strategist priorities and made good autonomous decisions.

## Blacklist
- HPO range narrowing (any param): 0/3 KEEP across all attempts
- Time_pcts densification (adding points): neutral, DISCARD
- Feature selection (drop hour_sin/cos): neutral, DISCARD
- Time_pcts pruning below 0.30: floor found, DISCARD
- **NEW**: Do NOT change knobs during ETH validation phase (iters 17-21)

## HPO Range Recommendations
- No changes during ETH phase
- Post-ETH: consider [0.005, 0.05] for learning_rate (brier-primary consistently finds lr=0.005-0.070)
