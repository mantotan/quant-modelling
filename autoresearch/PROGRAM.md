# Pulse Autoresearch Program

## Objective
Minimize OOS Brier score on the Pulse intra-bar model while maintaining:
- ECE < 0.05
- Backtest PnL > 0
- No data snooping (never look at test set to decide what to change)

## Primary Metric
**OOS Brier score** — lower is better. A result is KEPT only if Brier improves
AND constraints are not violated.

## Config-Driven Architecture

Experiment config lives in `autoresearch/knobs.json` (NOT in Python source).
The training script `scripts/train_pulse_fast.py` is **read-only** — no agent edits it.

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
- `cached_features` — which of 15 historical features to include (tick features 0-7 always included by the script)
- `time_pcts` — which intra-bar sampling points to use (subset of [0.003, 0.01, 0.05, 0.10, 0.20, 0.40, 0.60, 0.80])
- `hpo_search_space` — Optuna parameter bounds (all ranges as `[lo, hi]`)
- `walk_forward` — cross-validation config (splits, purge, embargo, train/test bars)
- `backtest` — simulation params (spread, min_edge, max_trades_per_bar, max_daily_trades)

### What You Must NOT Change
- `model` field (always "pulse")
- `market_sim.efficiency` — baked into the cached dataset, runtime changes have NO effect
- `backtest.fee_bps` — must stay 0 (maker-only strategy, no taker fees)
- `backtest.impact_bps` — must stay 0 (limit orders, no market impact)
- Target definition (close >= open for the current bar)
- Train/test split ratio (80/20 temporal at bar level)
- The training script code
- Any `src/qm/` module
- The cached dataset (.npz) — do NOT regenerate per iteration

### Pulse-Specific Rules
- **Tick features (indices 0-7) are ALWAYS included** — they are the core signal. Never suggest removing them.
- **min_child_samples must be >= 100** — Pulse has 8 correlated samples per bar; lower values cause overfitting.
- Walk-forward splits operate at **bar level**, not sample level. The script handles this automatically.

## System Phases

The autoresearch system operates in phases controlled by `autoresearch/phase.json`.
All agents read it; builder and auditor can write it.

### Phase A: Infrastructure Building
- **Active:** `sentinel-builder` (researcher/strategist/auditor paused via phase gate)
- **Goal:** Implement alpha downloaders, feature groups, interactions, regime detection
- **Workflow:** Builder picks next PENDING work unit from `build_plan.tsv`, implements with quality gates (ruff + pytest), commits
- **Transition:** All core build units (1-18) DONE → phase becomes `"research_enriched"`

### Phase B: Enriched Autoresearch
- **Active:** researcher, strategist, auditor, analyst (builder can run enhancement units 19-22 in parallel)
- **Goal:** Optimize model with expanded feature space (alpha + interaction + regime + objective knobs)
- **Workflow:** Same KEEP/DISCARD loop, but with 4 new knob categories
- **Transition:** Auditor issues `ADD_ALPHA` → phase becomes `"building"` for new source

### Phase C: Continuous Discovery
- **Active:** All five agents cycle between building and research
- **Goal:** Iterative build → research → discover → build more
- **Trigger:** After Phase B stalls for 50+ iterations or achieves acceptance criteria

## Multi-Agent System

Five agents operate on this system:

| Agent | Model | Cadence | Role | Writes to |
|-------|-------|---------|------|-----------|
| `sentinel-builder` | opus | Phase A: per invocation | Build alpha infra, quality workflow | src/qm/**, tests/**, build_progress.json |
| `sentinel-researcher` | sonnet | Phase B: every ~5 min | Run experiments, KEEP/DISCARD | knobs.json, best_knobs.json, results.tsv |
| `sentinel-strategist` | sonnet | Phase B: every ~5 iterations | Tactical analysis, priority queue | strategy.md |
| `sentinel-auditor` | opus | Phase B: every ~20 iterations | Deep analysis, macro directives | audit.md, phase.json |
| `sentinel-analyst` | sonnet | Any phase: on demand | Read-only progress reports | (none) |

**All loops run in ONE session** (serial execution prevents git conflicts).

### Communication Protocol

1. Builder reads build_plan.tsv → implements code → updates build_progress.json
2. Strategist reads results.tsv → writes `strategy.md` with priority queue + blacklist
3. Auditor reads results.tsv + strategy.md → writes `audit.md` with directives (CONTINUE/RESET/SWITCH/ESCALATE/WIDEN/ADD_ALPHA/RETRAIN_BASELINE)
4. Researcher reads strategy.md + audit.md → follows directives, falls back to autonomous mode if stale

### File Ownership (strict — prevents conflicts)

| File | Written by | Read by | Phase |
|------|-----------|---------|-------|
| phase.json | builder, auditor | all | all |
| build_plan.tsv | builder | builder, analyst | A |
| build_progress.json | builder | all | A |
| alpha_request.md | auditor | builder | C |
| knobs.json | researcher | all | B, C |
| best_knobs.json | researcher | researcher | B, C |
| results.tsv | researcher | all | B, C |
| strategy.md | strategist | researcher | B, C |
| audit.md | auditor | researcher, strategist | B, C |
| researcher_ack.txt | researcher | strategist, auditor | B, C |
| last_run.log | training script | strategist | B, C |
| src/qm/**/*.py | builder ONLY | all | A |
| tests/unit/**/*.py | builder ONLY | all | A |

### Enriched knobs.json Schema (Phase B)

New sections added to knobs.json after Phase A completes:
- `alpha_features` — dict of feature groups, each a list of feature names to include
- `interaction_features` — `{"enabled": bool, "pairs": [list of interaction names]}`
- `regime_params` — `{"enabled": bool, "vol_window": int, "lookback_window": int, ...}`
- `objective` — `{"primary": "sharpe"|"brier", "brier_threshold": float, ...}`

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
- Don't reduce min_child_samples below 100 (Pulse has 8 correlated samples per bar)
- Don't remove tick features (indices 0-7) — they ARE the signal
- Don't change fee_bps or impact_bps (maker-only: both are 0)
- Don't change market_sim.efficiency (baked into dataset)
- Don't chase backtest PnL at the expense of Brier/ECE
- Don't repeat experiments that are on the strategist's blacklist

## Maker-Only Fee Model
Polymarket crypto 5-min markets: makers pay 0 fees and earn 20% rebates.
Our strategy uses limit orders only, so fee_bps=0 and impact_bps=0 is correct.
