# Strategy Directive
Updated: 2026-03-19T15:35:00Z
After: Alpha feature activation (funding data downloaded, cache regenerated)

## Context

Funding rate data (25,337 rows, 4 assets, 2020-2026) downloaded from Binance Vision and stored in `data/raw/funding/`. The .npz dataset cache is being regenerated with 6 new funding features. The model now has ~50 features (8 tick + 15 TA + 6 funding + 21 other alpha placeholders).

Previous 21 iterations archived as `results_pre_alpha_v2.tsv`. Fresh start for alpha-enriched research.

## Priority Queue
1. **Run baseline with alpha features** — NO knob changes. This establishes the reference Brier/ECE/PnL for the 50-feature model. Compare to pre-alpha best (Brier 0.1439).
2. **Check funding feature importance** — if funding features appear in top-10 or top-20 feature importance, they're contributing. If not, the model may need different time_pcts or more data to leverage them.
3. **Try enabling/disabling funding feature groups** — toggle entire groups in `alpha_features.funding` to measure funding-specific lift.
4. **Try interaction features** — enable `funding_x_rsi`, `funding_x_vol`, `regime_x_funding` interactions. These cross alpha x TA signals for LightGBM to learn non-linear patterns.
5. **Continue proven optimizations** — brier-primary objective, n_splits=8, test_bars=2000, time_pcts [0.30, 0.40, 0.60, 0.80] are carried forward.

## Observations (from pre-alpha phase)
- **Optimal time_pcts**: [0.30, 0.40, 0.60, 0.80] — floor at 0.30, ceiling at 0.80
- **Brier-primary objective** found fundamentally different HPO optimum (slow learning, simple trees)
- **HPO range changes are blacklisted** (0/3 success rate)
- **Walk-forward tuning works** (2/2 KEEP rate)
- **Both BTC and ETH pass acceptance** with the same config

## Blacklist (carried forward)
- HPO range narrowing/widening: 0/3 across all attempts
- Time_pcts densification (adding points): neutral
- Feature selection (drop hour_sin/cos): neutral
- Time_pcts pruning below 0.30: floor found

## HPO Range Recommendations
- Keep current ranges — they work well with brier-primary
- After alpha features activate: revisit if HPO landscape changes fundamentally
