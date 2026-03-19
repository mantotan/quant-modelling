# Strategy Directive
Updated: 2026-03-19T18:00:00Z
After iteration: 4 (alpha-enriched phase)

## Alpha Feature Assessment

**Clear result after 4 iterations:**
- Funding features (6): USELESS for intra-bar. 8h cadence = constant within 5m bars. Blacklisted.
- Regime features (3): **regime_vol_zscore in top-10** (position 7). The model uses vol regime context. KEEP.
- Liquidation features (4): Marginal positive. Not in top-10 but absorbed without degradation. KEEP.
- Total improvement from alpha: Brier 0.143872 → 0.143854 (0.013%). Incremental, not transformational.

**Conclusion: The model was already near-optimal from pre-alpha tuning.** Alpha features provide context but the intra-bar prediction is dominated by tick features (positions 1-6). The regime vol z-score is the only alpha signal with measurable importance.

## Priority Queue
1. **Add interaction features** — try `regime_x_funding` and `funding_x_vol` even though funding alone failed. The interaction (regime state × funding rate) might capture regime-dependent funding effects that the individual features miss. Add to cached_features: `regime_x_funding`, `funding_x_vol`, `leverage_x_proximity`.
2. **Try removing liquidation features** — they KEPT but with only 0.000004 improvement. Test if removing them (back to 26 features) produces the same Brier — if so, simpler model is better.
3. **Increase embargo_period 6→12** — with more features, the model may benefit from stronger temporal separation to prevent feature leakage between WF folds.
4. **Try walk-forward train_bars 5000→8000** — more training data per fold may help the model learn alpha feature patterns.
5. **Return to BTC-only optimization** — no ETH switch needed. The alpha features are the exploration frontier.

## Observations
- **4 iterations, 3 KEEPs (75%)** — healthy KEEP rate
- **Brier plateau**: 0.143872 → 0.143854 after 4 iterations. The model is in a very tight optimum. Improvements of 0.00001 are noise-level.
- **regime_vol_zscore persistence**: Appears in top-10 in both iters 3 and 4 — this is a genuine signal, not noise
- **Top features unchanged**: vol_norm_distance (#1), distance_from_open (#2) dominate. Alpha features contribute marginally at best.
- **Funding features definitively useless**: 8h update cadence provides zero information for within-bar prediction. Would only be useful for Sentinel (bar-level) model.

## Blacklist
- Funding features in cached_features: iter 2 DISCARD (8h cadence)
- All HPO range changes: 0/3 from pre-alpha (carried forward)
- Time_pcts below 0.30: floor found (carried forward)
- Time_pcts above 0.80: ceiling found (carried forward)

## HPO Range Recommendations
- No changes. The model converges to the same HPO optimum regardless of alpha features.
- Focus research on feature composition, not HPO tuning.
