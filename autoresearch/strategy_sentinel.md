# Strategy Directive
Updated: 2026-03-19T02:45:00
After iteration: 4

## Priority Queue

1. **Narrow reg_alpha + reg_lambda HPO ranges to [0.01, 5.0]**
   Change: `hpo_search_space.reg_alpha: [0.01, 5.0]`, `hpo_search_space.reg_lambda: [0.01, 5.0]`
   Rationale: Regularization is the only major HPO dimension not yet explored. Current ranges span 8 orders of magnitude ([1e-8, 10.0]) — Optuna wastes the majority of its 40 trials sampling the extreme tails. Financial time-series LightGBM models with 19 features and 354k samples typically land in [0.01, 5.0]. Tighter range → same Optuna budget covers 2x more useful configurations. Expected improvement: 0.5–1.5% relative Brier reduction. KEEP probability estimate: 50–60%.

2. **Narrow learning_rate HPO range to [0.005, 0.04]**
   Change: `hpo_search_space.learning_rate: [0.005, 0.04]`
   Rationale: The fast-mode HPO in last_run.log found best Brier 0.247566 — indicating Optuna found good territory. LightGBM on financial series with 40 trials consistently selects low learning rates. Cutting the upper bound from 0.1 to 0.04 removes the high-LR region that typically yields overtrained, poorly-calibrated models. Pairs naturally with keeping n_estimators upper bound at 1000 (allows many slow-learning trees). KEEP probability estimate: 45–55%.

3. **Loosen feature selection: min_target_corr 0.005 → 0.002**
   Change: `feature_selection.min_target_corr: 0.002`
   Rationale: Iter 2 showed that *tightening* (0.005→0.010) dropped features and Brier worsened by +0.000038. The opposite direction (loosening) re-admits weakly-correlated features with additive ensemble value. Current selection drops 28/53 features at the 0.005 threshold — loosening to 0.002 will likely retain 3–8 additional features that carry incremental signal. Risk: pairwise-corr filter (0.90 threshold) will prune any redundant additions. KEEP probability estimate: 40–50%.

4. **Narrow max_depth upper bound: [2, 8] → [2, 6]**
   Change: `hpo_search_space.max_depth: [2, 6]`
   Rationale: With 19 features and financial noise, depth > 6 promotes overfitting. Iter 3 showed constraining num_leaves (a correlated parameter) to 63 hurt Brier — but that was an overly aggressive cap. Capping max_depth at 6 is a softer constraint that still allows 63-leaf trees while preventing extreme depth. Unexplored category; moderate expected value. KEEP probability estimate: 35–45%.

5. **Increase min_child_samples lower bound: [50, 500] → [100, 500]**
   Change: `hpo_search_space.min_child_samples: [100, 500]`
   Rationale: Prevents leaf nodes from being fit on very small samples, a key anti-overfit lever for financial data with regime shifts. Current lower bound of 50 may permit low-sample leaves on minority-regime bars. Unexplored; conservative change. KEEP probability estimate: 30–40%.

## Observations

- **KEEP rates by category:**
  - Feature selection (1 experiment, iter 2): 0/1 = 0% — tightening corr filter hurt
  - HPO range narrowing (1 experiment, iter 3): 0/1 = 0% — num_leaves cap was too aggressive
  - Walk-forward tuning (1 experiment, iter 4): 0/1 = 0% — more CV folds hurt marginally
  - Regularization: 0 experiments — highest-priority unexplored category
  - Backtest tuning: 0 experiments — irrelevant to Brier optimization, defer

- **Brier trajectory (4 iters):** 0.249371 (KEEP) → 0.249409 → 0.249429 → 0.249416. All changes degraded baseline by 0.000038–0.000058 (0.015–0.023% relative). Degradation is small but consistent — the baseline configuration is robust.

- **Baseline quality:** HPO fast-mode found Brier 0.247566 (last_run.log line: "Best HPO Brier: 0.247566"). This is 0.76% better than the OOS 0.249371 — the gap is expected (calibration + test-set variance). Baseline is healthy but sits just above the 0.25 acceptance threshold (needs ~0.4% relative improvement to pass).

- **Feature selection efficiency:** 53 raw features → 19 selected (28 dropped by target corr < 0.005, 6 by pairwise corr > 0.90). The 28-feature drop at iter 2 was the largest single filter; reversing it slightly (priority #3) is worth testing.

- **Researcher compliance:** No previous strategy existed (strategy.md was a placeholder after iteration 0). Researcher operated correctly in autonomous mode, making sensible exploratory changes. No compliance issue.

- **Convergence data:** Only 1 KEEP (baseline). Insufficient data to identify HPO parameter convergence regions. Recommend 2–3 more KEEPs before drawing convergence conclusions.

- **Backtest anomaly:** fee_bps=0.0 in all runs. This understates real trading costs. Do NOT optimize backtest metrics — Brier is the sole optimization target per PROGRAM.md. Backtest PnL at zero fees is uninformative.

## Blacklist

- **Raising min_target_corr above 0.005** — iter 2 (2026-03-19T00:30:00): Brier 0.249371→0.249409 (+0.000038). Tighter feature filtering removes additive weak signal. Do not retry unless Brier is confirmed overfitting.
- **Capping num_leaves below 64** — iter 3 (2026-03-19T01:00:00): Brier 0.249371→0.249429 (+0.000058). Model expressiveness needs the full range; hard caps on tree complexity parameters hurt more than they help at this dataset scale.
- **Increasing n_splits above 5** — iter 4 (2026-03-19T01:30:00): Brier 0.249371→0.249416 (+0.000045). More folds added fold-variance noise without improving generalization. n_splits=5 is sufficient for 354k bars.

## HPO Range Recommendations

- **reg_alpha**: narrow to [0.01, 5.0] — evidence: current [1e-8, 10.0] is 9-order span; no KEEP data yet but 40-trial Optuna cannot meaningfully explore this range. Financial LightGBM priors favor [0.01, 2.0].
- **reg_lambda**: narrow to [0.01, 5.0] — same rationale as reg_alpha.
- **learning_rate**: narrow to [0.005, 0.04] — evidence: HPO found best result at 0.247566 in fast mode, suggesting low-LR region is productive. Cutting [0.04, 0.1] removes overtrained configurations.
- **max_depth**: consider cap at 6 — evidence: iter 3 showed tree complexity constraints have risk; soft cap on depth is safer than hard cap on leaves.
- **num_leaves**: keep at [7, 127] — iter 3 confirmed that capping at 63 hurts. Do not narrow until 3+ KEEPs cluster the optimal value.
