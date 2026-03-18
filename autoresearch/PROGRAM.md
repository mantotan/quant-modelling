# Sentinel Autoresearch Program

## Objective
Minimize OOS Brier score on the Sentinel model while maintaining:
- ECE < 0.05
- Backtest PnL > 0
- No data snooping (never look at test set to decide what to change)

## Primary Metric
**OOS Brier score** — lower is better. A result is KEPT only if Brier improves
AND constraints are not violated.

## Config-Driven Architecture

Experiment config lives in `autoresearch/knobs.json` (NOT in Python source).
The training script `scripts/train_sentinel_fast.py` is **read-only** — no agent edits it.

### Config File Protocol

| File | Purpose |
|------|---------|
| `knobs.json` | Current experiment config — researcher edits this |
| `best_knobs.json` | Last KEEP'd config — copied on KEEP |

**KEEP flow:** `cp knobs.json → best_knobs.json`
**DISCARD flow:** `cp best_knobs.json → knobs.json`
**CRASH flow:** same as DISCARD

No `git checkout`, no `git reset`, no Python file editing.

### Knobs You May Change

All fields in `autoresearch/knobs.json`:
- `exclude_features` — which features to drop
- `feature_selection` — thresholds (missing, target corr, pairwise corr)
- `hpo_search_space` — Optuna parameter bounds (all ranges as `[lo, hi]`)
- `walk_forward` — cross-validation config (splits, purge, embargo)
- `backtest` — simulation params (fees, spread, min_edge, kelly)

### What You Must NOT Change
- Target definition (close[t+1] >= open[t+1])
- Train/test split ratio (80/20 temporal)
- The training script code
- Any `src/qm/` module

## Multi-Agent System

Three agents operate on this research loop:

| Agent | Model | Cadence | Role | Writes to |
|-------|-------|---------|------|-----------|
| `sentinel-researcher` | sonnet | every 8 min | Run experiments, KEEP/DISCARD | knobs.json, best_knobs.json, results.tsv |
| `sentinel-strategist` | sonnet | every ~5 iterations | Tactical analysis, priority queue | strategy.md |
| `sentinel-auditor` | opus | every ~20 iterations | Deep analysis, macro directives | audit.md |

**All loops run in ONE session** (serial execution prevents git conflicts).

### Communication Protocol

1. Strategist reads results.tsv → writes `strategy.md` with priority queue + blacklist
2. Auditor reads results.tsv + strategy.md → writes `audit.md` with CONTINUE/RESET/SWITCH/ESCALATE/WIDEN
3. Researcher reads strategy.md + audit.md → follows directives, falls back to autonomous mode if stale

### File Ownership (strict — prevents conflicts)

| File | Written by | Read by |
|------|-----------|---------|
| knobs.json | researcher | all |
| best_knobs.json | researcher | researcher |
| results.tsv | researcher | all |
| strategy.md | strategist | researcher |
| audit.md | auditor | researcher, strategist |
| researcher_ack.txt | researcher | strategist, auditor |
| last_run.log | training script | strategist |

## Operational Constraints

### Bash Timeouts
- Fast mode: `timeout: 480000` (8 min) — for 40-trial runs
- Verify mode: `timeout: 600000` (10 min) — for 100-trial verification runs

### Verification Protocol
When a KEEP improves Brier by >2% relative, immediately re-run with `--mode verify --trials 100`.
If verify confirms improvement → KEEP-VERIFIED. If it regresses → VERIFY-FAILED (revert).

### Stagnation Escape
- 3+ consecutive DISCARDs on same category → try different category
- 5+ consecutive DISCARDs overall → random large perturbation
- 15+ iterations on one asset → switch to next asset

## Anti-Patterns
- Don't make multiple changes at once — isolate variables
- Don't widen search spaces without reason (unless auditor says WIDEN)
- Don't reduce regularization without evidence of underfitting
- Don't chase backtest PnL at the expense of Brier/ECE
- Don't repeat experiments that are on the strategist's blacklist
