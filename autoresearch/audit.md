# Audit Report
Updated: 2026-03-20T01:15:00Z
After iteration: 21

## Verdict: SWITCH ETH for 10 iterations
The BTC search is stalled: 7 of the last 8 iterations are DISCARD (the sole KEEP was marginal, delta 0.000008). The strategist's top two priorities have both been definitively exhausted -- narrow HPO ranges (5 attempts, all DISCARD due to wall-clock timeout) and time_pct 0.10 addition (iter 21, catastrophic +63% Brier regression). Remaining priorities are validation hygiene, not structural improvements. The model already passes all acceptance criteria with large margins. The highest-value next action is cross-validating on ETH to confirm the pipeline generalizes beyond BTC before investing further in BTC-specific tuning or alpha source implementation.

## Directive Details
Switch to ETH BTC for 10 iterations using the current best knobs (from iter 18). Start with a baseline run using identical configuration (time_pcts=[0.30,0.50,0.80], train_bars=10000, n_splits=8). This serves three purposes: (1) confirms the pipeline and feature set generalize to a different asset, (2) establishes an ETH baseline for future comparison, (3) provides cross-validation signal on whether regime_vol_zscore (the only confirmed persistent alpha) carries signal on ETH. If the ETH baseline Brier is within 20% of BTC (i.e., below 0.122), the pipeline is robust. If it regresses beyond 0.15, the BTC model may be overfit to BTC-specific microstructure.

## Progress Assessment
- Improvement rate: 0.001% Brier improvement per iteration over last 8 iterations (stalled)
- Estimated iterations to acceptance (Brier < 0.25): already met -- current best 0.101829
- KEEP rate: 38% overall (25% over last 8 iterations, declining)
- Two step-function improvements drove all progress: iter 8 (train_bars, -27.5%) and iter 14 (3 time_pcts, -29.1%). All subsequent tuning has yielded zero material gain.

## Risk Flags
- Overfitting: low -- hpo_brier vs oos_brier gap: ~0.013 (stable across iters 8, 14, 18)
- Calibration drift: ECE trend over last 8 iterations: 0.0094, 0.0077, 0.0101, 0.0094, 0.0099, 0.0138, 0.0138, 0.0064. Slight upward creep in iters 19-20 (0.0138) but iter 21 returned to 0.0064. No sustained drift. All values well below 0.05 threshold.
- PnL disconnect: moderate -- Brier improved 29% from iter 8 to iter 14 (0.1437 to 0.1018) but single-side PnL dropped 32% ($68 to $46) and bs_pnl dropped 59% ($1.43M to $593K). Trade count halved (80K to 44K). The model is more accurate but less active. Sharpe improved (74 to 107 single-side), so per-trade quality is better, but absolute PnL decline warrants monitoring.
- Strategy divergence: bs_pnl and single-side PnL move in the same direction (both declined with the iter 14 Brier improvement), suggesting the model is concentrating predictions in higher-confidence regions rather than improving across the full distribution. Not a bug -- this is expected behavior for a more calibrated model -- but it means further Brier improvements may not translate to PnL gains.
- Search exhaustion: clear evidence. 7/8 recent iterations DISCARD. Strategist's top 2 priorities confirmed exhausted. Remaining priorities are minor hygiene items.
- Config inconsistency: knobs.json has interaction_features.enabled=true, but interaction features are permanently blacklisted (iter 6, +41% Brier regression). This should be set to false to prevent accidental activation.

## Acceptance Criteria Status
| Metric | Target  | Current Best | Gap      |
|--------|---------|-------------|----------|
| Brier  | < 0.25  | 0.101829    | 59% margin (passing) |
| ECE    | < 0.05  | 0.0042      | OK (92% margin) |
| PnL    | > 0     | $45.72      | OK (passing) |
| Sharpe | > 0.0   | 106.72      | OK (passing) |
| BS PnL | > 0     | $584,953    | OK (informational) |
| Max DD | < 30%   | 15.23%      | OK (49% margin) |

## Alpha Feature Assessment
- Funding (6 features): zero lift confirmed (iter 2 DISCARD). Not in cached_features. Correctly excluded.
- Regime (3 features): confirmed persistent alpha. regime_vol_zscore in top-10 SHAP across multiple iterations.
- Liquidation (4 features): net positive contributors (iter 16 confirmed removal hurts). In cached_features.
- Options IV (5 features): defined in knobs.json alpha_features but NOT implemented/downloaded. Candidate for ADD_ALPHA in future.
- Polymarket (4 features): defined in knobs.json alpha_features but NOT implemented/downloaded. Candidate for ADD_ALPHA in future.
- Interaction features: permanently blacklisted. Config should reflect this (enabled=false).

## Researcher Compliance
- Researcher is following strategy priorities in order. Acknowledged exhaustion of priority #1 after 5 attempts.
- Iter 21 correctly attempted priority #2 (time_pct 0.10) which also failed.
- Researcher ack shows correct state tracking (current_iteration=21, consecutive_discards=2).
- Minor: iteration numbering has a gap (no iter 5 in results.tsv). Cosmetic only.

## Next Audit
After 10 ETH iterations (approximately iteration 31).
