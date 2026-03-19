# Audit Report
Updated: 2026-03-20T09:00:00Z
After iteration: 37

## Verdict: ESCALATE — Mandatory PBO/Deflated Sharpe validation before XRP expansion

BTC and ETH are both at confirmed architectural floors (0.101759 and 0.177772 respectively) with exhausted config search. Both assets pass Brier, ECE, PnL, Sharpe, and max drawdown criteria with large margins. Yet PBO and Deflated Sharpe -- two of six acceptance criteria listed in CLAUDE.md -- have never been measured across 37 iterations and 3 assets. This is a critical validation gap. The program has been optimizing for 15+ hours without confirming that the walk-forward results are not artifacts of combinatorial overfitting. With 16 KEEP configurations tested, the a priori probability of at least one spurious KEEP is material. SOL iterations 38-46 may proceed per the strategist's queue, but the researcher MUST run CPCV/PBO validation on BTC best (iter 22 config, commit 4b70d86) and ETH best (iter 32 config, commit 48e7719) before starting XRP (iter 47+). If PBO > 0.40 for either asset, halt all expansion and escalate to the auditor immediately.

## Directive Details

**ESCALATE criteria change (mandatory, time-bounded):**

1. Complete SOL iterations 38-46 per current strategy queue (no change to SOL plan).
2. Before iteration 47 (XRP baseline), the researcher MUST run CPCV with PBO calculation on:
   - BTC best model (iter 22 config, commit `4b70d86`)
   - ETH best model (iter 32 config, commit `48e7719`)
3. Record PBO and Deflated Sharpe values in results.tsv as special validation rows (status=VALIDATION, description includes asset and metric values).
4. If PBO >= 0.40 for either asset: HALT all expansion. Do not start XRP. Report to auditor.
5. If PBO < 0.40 and Deflated Sharpe > 0.0 for both assets: proceed to XRP baseline at iter 47.
6. The SOL best model should also receive PBO validation after SOL iterations complete (iter 46), before XRP begins.

This is a hard gate, not a suggestion. No XRP iteration may run without PBO validation results for BTC and ETH recorded in results.tsv.

## Progress Assessment
- Improvement rate: 0.0% Brier improvement per iteration over last 15 BTC iterations (stalled at floor); ETH improvement 0.03% per iteration over 10 iterations (stalled at floor); SOL has 1 baseline iteration only
- Estimated iterations to acceptance (Brier < 0.25): already met for all 3 assets (BTC 0.102, ETH 0.178, SOL 0.193)
- KEEP rate: 43% overall (16/37). BTC last 10: 10% (1 KEEP iter 22, then 14 DISCARDs). ETH: 40% (4/10). SOL: 100% (1/1 baseline).

## Risk Flags
- Overfitting: low -- hpo_objective vs oos_brier gaps are stable. BTC gap: 0.013 (oos 0.1018 vs hpo 0.0889). ETH gap: 0.004 (oos 0.1778 vs hpo 0.1736). SOL shows negative gap (oos 0.193 < hpo 0.217), meaning OOS outperforms in-sample, which is reassuring but unusual. No widening trend detected.
- Calibration drift: ECE stable within each asset. BTC: 0.0088 (best config). ETH: 0.0252 (best config). SOL baseline: 0.0342 (highest of all assets but well within 0.05 threshold). No sustained upward drift.
- PnL disconnect: moderate (unchanged from prior audit) -- BTC Brier improved 29% from iter 8 to 14 but single-side PnL dropped 32% ($68 to $46) due to halved trade count. Model is more accurate but less active. Sharpe improved, so per-trade quality is higher. ETH and SOL show no disconnect (PnL stable across iterations).
- Strategy divergence: BTC bs_pnl and single-side PnL move in same direction. ETH both-sides dominates (bs_sharpe 267 vs single-side 265). SOL baseline bs_sharpe 245 vs single-side 242 -- nearly identical, suggesting SOL edge is symmetric. No divergence concern.
- Search exhaustion: BTC definitively exhausted (14 consecutive non-improvements including 4 identical Brier results). ETH exhausted (10 iterations, floor confirmed). SOL fresh with 9 planned iterations and the highest-confidence lever (train_bars extension) still available.
- **UNMEASURED ACCEPTANCE CRITERIA: PBO and Deflated Sharpe have never been computed. This is the single largest risk to the program. 37 iterations of config search without combinatorial overfitting validation is the primary finding of this audit.**

## Acceptance Criteria Status
| Metric          | Target   | BTC Best    | ETH Best    | SOL Best    | Gap               |
|-----------------|----------|-------------|-------------|-------------|-------------------|
| Brier           | < 0.25   | 0.101759    | 0.177772    | 0.193016    | All PASS          |
| ECE             | < 0.05   | 0.0088      | 0.0252      | 0.0342      | All PASS          |
| PnL             | > 0      | $45.55      | $176.50     | $171.17     | All PASS          |
| Sharpe          | > 0.0    | 109.25      | 264.57      | 242.33      | All PASS          |
| Max Drawdown    | < 30%    | 13.61%      | 1.75%       | 1.62%       | All PASS          |
| BS PnL          | > 0      | $583,903    | $14,065,914 | $13,702,814 | All PASS (info)   |
| **PBO**         | **< 0.40** | **NOT MEASURED** | **NOT MEASURED** | **NOT MEASURED** | **CRITICAL GAP** |
| **Defl. Sharpe**| **> 0.0**  | **NOT MEASURED** | **NOT MEASURED** | **NOT MEASURED** | **CRITICAL GAP** |

## Cross-Asset Summary
| Asset | Best Brier | Best bs_sharpe | Iterations | Floor Status   | PBO Validated |
|-------|-----------|---------------|------------|----------------|---------------|
| BTC   | 0.101759  | 93.84         | 22         | Exhausted      | NO            |
| ETH   | 0.177772  | 267.08        | 10         | Exhausted      | NO            |
| SOL   | 0.193016  | 244.67        | 1          | Fresh          | NO            |
| XRP   | --        | --            | 0          | BLOCKED on PBO | NO            |

## Alpha Feature Assessment
- Regime (3 features): Confirmed signal on BTC (top-10 SHAP persistent) and SOL (top-10 at baseline). Zero signal on ETH. Most valuable alpha group.
- Liquidation (4 features): Net positive on BTC (removal hurts). Untested standalone on ETH/SOL.
- Funding (6 features): Zero lift on BTC and ETH. Untested on SOL (SOL funding dynamics are distinct -- worth one test per strategy priority #7).
- Options IV (5 features): Not implemented. Candidate for ADD_ALPHA after PBO validation and SOL completion.
- Polymarket (4 features): Not implemented. Candidate for ADD_ALPHA after PBO validation.

## Researcher Compliance
- Researcher is following directives correctly. SWITCH ETH (previous audit) was executed for exactly 10 iterations (iters 23-32). SOL baseline completed per strategy priority #1. Config reset between assets was handled properly. Researcher ack shows accurate state tracking (iteration 37, consecutive_discards reset for new asset).
- Minor note: knobs.json and best_knobs.json are currently identical (both BTC-optimal). best_knobs.json should reflect per-asset bests but this is cosmetic and does not affect training.

## Next Audit
After SOL iteration 46 (SOL completion) or after PBO validation results are recorded, whichever comes first. If PBO fails (>= 0.40), an emergency audit will be required.
