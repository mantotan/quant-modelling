# Sentinel Autoresearch Program

## Objective
Minimize OOS Brier score on the Sentinel model while maintaining:
- ECE < 0.05
- Backtest PnL > 0
- No data snooping (never look at test set to decide what to change)

## Primary Metric
**OOS Brier score** — lower is better. A result is KEPT only if Brier improves
AND constraints are not violated.

## What You May Change
Edit ONLY the "RESEARCH KNOBS" section in `scripts/train_sentinel_fast.py`:

- `EXCLUDE_FEATURES` — which features to drop
- `FEATURE_SELECTION` — thresholds for feature selection
- `HPO_SEARCH_SPACE` — bounds for Optuna hyperparameter search
- `WALK_FORWARD` — cross-validation configuration
- `BACKTEST` — backtest parameters (fee, spread, min_edge, kelly)

## What You Must NOT Change
- Target definition (close[t+1] >= open[t+1])
- Train/test split ratio (80/20 temporal)
- The data loading or feature computation pipeline
- Code outside the RESEARCH KNOBS section
- `prepare.py` or any `src/qm/` module

## Strategy Suggestions
1. Start with feature selection — try different correlation thresholds
2. Narrow HPO ranges based on what past experiments found optimal
3. Try different regularization regimes (high reg vs low reg)
4. Adjust walk-forward splits (more splits = more robust but slower)
5. Experiment with min_edge and kelly_fraction for backtest profitability
6. Try excluding features that show up as low-importance consistently

## Anti-Patterns to Avoid
- Don't make multiple changes at once — isolate variables
- Don't widen search spaces without reason — narrow toward known-good regions
- Don't reduce regularization without evidence of underfitting
- Don't chase backtest PnL at the expense of Brier/ECE

## Operational Constraints

### Bash Timeout
Always set `timeout: 360000` (6 minutes) on the Bash call that runs training.
The default 120s timeout WILL kill the training mid-run.

### Crash Recovery
If the previous iteration left dirty git state:
1. `git checkout -- scripts/train_sentinel_fast.py`
2. Check `autoresearch/last_run.log` for the crash reason
3. If the crash was from a bad RESEARCH KNOBS edit, revert to known-good values
4. Log the CRASH to results.tsv before trying a new hypothesis

### Stagnation Escape
If 3+ consecutive DISCARDs with similar strategies:
- Pivot to a completely different knob category
- Try the opposite direction (e.g., if tightening didn't help, try loosening)
- Consider reverting to baseline and trying a fresh approach
