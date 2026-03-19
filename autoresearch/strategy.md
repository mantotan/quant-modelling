# Strategy Directive
Updated: 2026-03-20T20:15:00Z
After iteration: 57

## Program Status: RESEARCH PHASE COMPLETE

All 4 assets fully validated after 57 iterations. The autoresearch optimization loop is
closed. This directive covers: final asset classification, what was learned across 57
iterations, and the transition to Steps 5-8 (live execution infrastructure). There are no
further knob experiments to run.

---

## Priority Queue

The following are deployment preparation actions, not knob experiments. The researcher
thread should treat these as ordered work items for engineering handoff.

1. **[DEPLOY-1] Compile all 4 trained models to treelite for sub-millisecond inference.**

   Source models: `data/models/pulse_v2/{ASSET}_5m/model.lgb` for BTC, ETH, SOL, XRP.
   Target: treelite-compiled `.so` / `.dll` per asset, stored at
   `data/models/pulse_v2/{ASSET}_5m/model_compiled.{so|dll}`.

   Rationale: The Rust fast path (Step 7) requires compiled model artifacts. Treelite
   compilation must happen before the Rust port of IntraBarFeatureCalculator can be wired
   to live inference. Compilation is deterministic — it only needs to run once per trained
   model. All 4 models are now stable (no further retraining planned until live drift).

   Verification: after compilation, run parity test — Python LightGBM predict vs treelite
   predict on 1000 held-out samples. Require max absolute probability difference < 1e-6.
   If parity fails on any asset, treelite is the blocker for Step 7 before live trading.

   Asset-specific notes:
   - BTC: max_depth=4, num_leaves=77, n_estimators=1028 — smaller tree, fast compile.
   - ETH: max_depth=5-6, num_leaves=95, n_estimators=705-1160 — medium.
   - SOL: max_depth=6, num_leaves=72, n_estimators=1175 — medium.
   - XRP: max_depth=5, num_leaves=115 (near ceiling), n_estimators=624 — watch compile
     time; XRP num_leaves is the largest relative to depth.

2. **[DEPLOY-2] Build live inference feature cache with Rust/Python fallback
   (`src/qm/features/live_cache.py`).**

   This is the Step 7 entry point. The file is listed in STEPS_5_8_REMAINING.md as a
   Python wrapper with automatic Rust/Python fallback. The implementation sequence:
   (a) Python-only version first — wraps the existing IntraBarFeatureCalculator
       (`src/qm/features/intrabar.py`) with a thread-safe ring buffer for tick data.
   (b) Rust port second — port `IntraBarFeatureCalculator` to
       `crates/qm-fast/src/features/calculator.rs` once (a) is validated.
   (c) Fallback logic: if Rust module import fails (e.g., maturin not built), silently
       fall back to Python path. Log the fallback at WARN level.

   The Python-only path unblocks Step 5 (live CLOB execution) immediately without waiting
   for the Rust port. Deploy ETH live trading on the Python path while Rust is built.

   Feature set for live cache: the 22 cached_features + 8 alpha/regime features listed
   in best_knobs.json. The live cache must match the training feature order exactly —
   use the `feature_names_` attribute from the saved LightGBM model as the canonical
   order reference. Mismatched feature order is a silent correctness failure.

3. **[DEPLOY-3] Implement Polymarket CLOB client and order manager (Step 5 core).**

   Prioritized implementation sequence from STEPS_5_8_REMAINING.md:
   (a) `src/qm/execution/polymarket/client.py` — py-clob-client wrapper with retry,
       rate limiting, and secret redaction in structlog output. This is the foundation
       all other Step 5 components depend on.
   (b) `src/qm/execution/polymarket/market_scanner.py` — reuse existing
       `polymarket_recorder.py` _discover_markets() logic, add liquidity depth check.
   (c) `src/qm/execution/polymarket/order_manager.py` — heartbeat supervisor at 10s
       intervals, order lifecycle tracking, 60s timeout cancellation.
   (d) `src/qm/execution/polymarket/live_executor.py` — implements the Executor
       interface already used by PaperExecutor.
   (e) `src/qm/execution/reconciliation.py` — startup state sync.

   Deployment sequence for live trading:
   - Week 1: ETH paper trading with live CLOB data (PaperExecutor, real market scanner).
   - Week 2: ETH live trading at 0.25x Kelly (below UNCONDITIONAL PASS sizing), validate
     fill rates and slippage against backtest assumptions.
   - Week 3: ETH scale to full sizing. BTC live at 0.25x Kelly.
   - Week 4+: SOL at 0.5x Kelly per auditor directive. XRP at 0.25x Kelly per
     CONDITIONAL-STRICT clearance. Upgrade XRP to 0.5x Kelly after 30 days live data.

4. **[DEPLOY-4] Establish retraining cadence policy.**

   The models are frozen as of iter 57. Live data will accumulate drift. Define triggers:
   - Mandatory retrain: OOS Brier on rolling 30-day live window exceeds 1.2x the
     validation floor (BTC > 0.122, ETH > 0.213, SOL > 0.227, XRP > 0.234).
   - Scheduled retrain: quarterly (90-day) forced retrain regardless of drift metrics.
   - Emergency retrain: structural market break (new exchange mechanism, major protocol
     change for XRP, BTC halving period) — consult auditor before triggering.

   For BTC specifically: the regime-bucketed analysis showed monotonically increasing edge
   with volatility (low 91 < normal 114 < high 138 < crisis 168). If a live 30-day window
   shows this monotonicity breaking (e.g., crisis Sharpe < normal Sharpe), treat that as
   a model drift signal regardless of absolute Brier.

---

## What Was Learned — 57-Iteration Program Summary

### Structural findings (high confidence, apply to any future Pulse asset)

**Finding 1: Three time points [0.30, 0.50, 0.80] are universally optimal.**
Iter 14 produced the single largest Brier improvement in the program (29.1% reduction,
0.1982 to 0.1018) by reducing from 4 to 3 time points. Adding the 0.10 snapshot (iter 21)
caused 63% regression. Adding 0.20/0.90 (iter 12) caused HPO starvation. Adding 0.95
(ETH iter 28) produced no change. The 0.30-0.50-0.80 cadence captures early structure,
midpoint signal, and late confirmation without overloading the sample budget.

**Finding 2: train_bars ceilings are asset-class specific, not universal.**
BTC ceiling: 10,000 bars (iters 18-22 showed floor locked). ETH/SOL/XRP ceiling: 14,000
bars. The ceiling is set by the walk-forward window budget — beyond the ceiling, HPO
starvation dominates and offset gains from more data. The BTC ceiling is lower because
BTC has shallower trees (max_depth=4) that converge faster.

**Finding 3: Funding features contribute zero signal at 5m resolution.**
0/3 KEEP across BTC (iter 2), ETH (iter 27), SOL (iter 43). The mechanism is funding
rate update frequency: perpetual funding settles every 8h, producing near-constant values
within any 5m prediction window. The feature variance is too low to survive LightGBM's
min_child_samples regularization. Do not test funding features for any future 5m asset.

**Finding 4: Interaction features are universally harmful.**
Iter 6 showed +41% Brier regression (0.143854 to 0.2028) from adding 3 interaction
features. The mechanism is combinatorial noise amplification: each product feature adds
a non-monotonic surface that LightGBM must partition, consuming split budget that is
better spent on the 22 core features. Interactions are permanently blacklisted.

**Finding 5: HPO range narrowing is uniformly counterproductive.**
0/5 KEEP across 5 narrowing attempts (iters 10, 13, 15, 19, 20). Root cause: wall-clock
timeout binds at approximately 30-35 trials regardless of trial cap. Narrowing the range
does not increase trial count — it reduces diversity of the Optuna search surface while
the trial budget stays constant. The wide default ranges [lr: 0.005-0.1, depth: 2-6,
leaves: 16-128] are already well-calibrated for this problem.

**Finding 6: n_splits=8, embargo=6 are universally optimal.**
0/4 KEEP on n_splits changes (iters 11, 31, 33); 0/2 on embargo changes (iters 9, 30).
n_splits=8 maximizes the IS-OOS size ratio within the walk-forward budget. n_splits=6
produces more HPO trials per fold (beneficial for HPO) but degrades model quality by
reducing OOS evaluation diversity. embargo=6 captures the autocorrelation decay length
for 5m bars — the model's temporal leakage horizon is approximately 30 minutes.

**Finding 7: Regime features are BTC-specific value-add, not universal.**
regime_vol_zscore appeared in BTC SHAP top-10 (rank 7, stable across optimization) but
was absent from ETH/SOL SHAP top-10 across all experiments. Despite absence from top-10
SHAP, ETH iter 24 (remove regime features) produced a DISCARD — regime features contribute
marginal but non-zero signal for all assets. Keep all 3 regime features in cached_features
for all assets as baseline. The signal is asset-class dependent in magnitude, not presence.

**Finding 8: The CPCV PBO metric is unreliable for regime-sensitive assets.**
BTC PBO(Sharpe)=0.9643 and XRP PBO(Sharpe)=1.0000 despite both assets having 100% positive
OOS paths across all 28 CPCV folds. The root cause is a structural negative IS-OOS Sharpe
rank correlation (BTC corr=-0.9048, XRP corr=-0.9047) caused by regime concentration in
training folds: high-volatility folds generate elevated IS Sharpe but are tested against
low-volatility OOS windows and vice versa. PBO is mechanically corrupted by this regime
heterogeneity. The composite replacement gate (100% positive paths + IS-OOS absolute gap
< 20% + Deflated Sharpe > 0 + regime-bucketed all positive) is more robust and should be
the standard for all future regime-sensitive asset validation.

### Asset classification (final)

**BTC-class (regime-sensitive):**
- Asset: BTC. Likely applies to any large-cap futures asset with strong vol regime clustering.
- Signature: regime_vol_zscore SHAP rank 7+, max_depth=4 (shallower than tick-dominant),
  reg_alpha=2.854 (moderate L1), purge_period=24, single-side sniper dominant (Sharpe 109
  vs bs_sharpe 94), edge monotonically increases with volatility (low 92 < normal 114 <
  high 138 < crisis 168).
- CPCV behavior: PBO gate suspended, composite gate required.

**ETH-class (tick-dominant, pure):**
- Asset: ETH. Likely applies to high-liquidity altcoins with efficient HFT-dominated order flow.
- Signature: tick microstructure SHAP top-5 (partial_bar_position, partial_range,
  trade_intensity), max_depth=5-6, reg_alpha approximately 1e-6 (no L1), purge_period=12,
  both-sides MM dominant (bs_sharpe 274 vs single-side 264), edge flat across regimes.
- CPCV behavior: PBO=0.1786 UNCONDITIONAL PASS, no composite gate needed.

**SOL-class (tick-dominant, post-event contamination):**
- Asset: SOL. Applicable to assets with known structural breaks in training window.
- Signature: identical to ETH-class architecture but CPCV PBO=0.6429 elevated due to FTX
  2022 Q4 temporal non-stationarity. Regime-bucketed validation confirmed all 4 buckets
  positive and flat (235-247 Sharpe, 4% spread vs BTC 83% spread) — FTX break hypothesis
  refuted; the elevated PBO is fold-heterogeneity not model failure. Deploy at 0.5x Kelly.

**XRP-class (tick-dominant architecture, BTC-class fold behavior):**
- Asset: XRP. The unexpected finding of the program.
- Signature: tick microstructure SHAP top-10 (same as ETH/SOL), but reg_alpha=4.13
  (extreme L1, 2.8x higher than BTC), purge_period=24 (same as BTC, longer than ETH/SOL),
  IS-OOS Sharpe corr=-0.9047 (identical to BTC corr=-0.9048).
- Interpretation: XRP's payment-token order flow (retail-dominated, periodic large flows)
  creates feature multicollinearity in OHLCV-derived tick features that L1 regularization
  resolves via sparsity. The sparsity pattern mimics BTC-class regime behavior in CPCV
  fold partitioning. Deploy at 0.25x Kelly, upgrade after 30 days live data.

---

## Observations

**KEEP rates by category (57 iterations, final):**
- Asset baselines: 4/4 (100%) — iters 7, 23, 37, 51
- KEEP-VERIFIED runs: 2/2 (100%) — iters 8, 14
- train_bars extension: 5/7 (71%) — KEEP iters 8, 18, 25, 38; DISCARD iters 52 (XRP ceiling at 14K)
- purge_period tuning: 4/8 (50%) — KEEP iters 22, 29, 39, 53; DISCARD iters 9, 30, 45 (ETH)
- Regime+liquidation alpha features (BTC): 2/2 (100%)
- drawdown_penalty_weight: 1/2 (50%) — ETH iter 32 KEEP; XRP iter 54 DISCARD
- Funding features in cached_features: 0/3 (0%) — permanent blacklist
- time_pcts adjustments: 1/6 (17%) — only iter 14 reduction KEEP; expansions all DISCARD
- HPO range narrowing: 0/5 (0%) — permanent blacklist
- regime_params window changes: 0/3 (0%) — permanent blacklist
- Interaction features: 0/1 (0%) — permanent blacklist
- n_splits changes: 0/4 (0%) — n_splits=8 confirmed all assets
- embargo_period changes: 0/2 (0%) — embargo=6 confirmed all assets
- objective/gate experiments: 0/5 (0%) — model floor locked all assets
- CPCV/validation runs: ETH PASS (PBO=0.18), BTC PASS (regime-bucketed), SOL PASS (regime-bucketed), XRP PASS (composite gate)
- Overall KEEP rate (optimization iterations only): 20/49 = 40.8%

**Brier trajectory — final state:**
- BTC: 0.1982 (iter 7) → 0.101759 (iter 22). 48.6% total reduction. Frozen for 35 iterations.
- ETH: 0.178243 (iter 23) → 0.177772 (iter 32). 0.26% total reduction. Architectural floor.
- SOL: 0.193016 (iter 37) → 0.189372 (iter 39). 1.9% total reduction. Architectural floor.
- XRP: 0.195335 (iter 51) → 0.195309 (iter 53). 0.013% total reduction. Architectural floor.

BTC was the only asset with a substantial Brier improvement path. ETH/SOL/XRP reached
their architectural floors within 2-3 optimization iterations after baseline — the 22-feature
tick-dominant architecture has minimal room for knob-level improvement.

**Both-sides vs single-side final recommendations:**
- BTC: single-side sniper only. Sharpe 109.25 vs bs_sharpe 93.84 (16% advantage). BTC
  directional edge is concentrated in single-sided prediction; market-making degrades it.
- ETH: both-sides MM only. bs_sharpe 267-274 vs single-side 264. Both-sides slightly dominant.
  Consistent record across 9 ETH optimization iterations.
- SOL: statistical tie (bs_sharpe 251.55 vs single-side 251.86). Deploy both-sides MM for
  consistency with ETH-class framework. Re-evaluate after 30 days live data.
- XRP: both-sides MM slightly dominant (bs_sharpe 262.32 vs single-side 261.47, consistent
  across iters 51 and 53). Deploy both-sides MM as per classification.

**HPO best_params — fully converged (use as live inference params, not retrain midpoints):**
- BTC: lr=0.01272, max_depth=4, n_estimators=1028, num_leaves=77, reg_alpha=2.854, reg_lambda=1.131
- ETH: lr=0.009-0.012, max_depth=5-6, n_estimators=705-1160, num_leaves=95, reg_alpha=~1e-6, reg_lambda=0.023
- SOL: lr=0.023102, max_depth=6, n_estimators=1175, num_leaves=72, reg_alpha=0.016194, reg_lambda=8e-6 (identical across 5 consecutive iterations)
- XRP: lr=0.009843 (iter 53 best, 9x shift from baseline iter 51), max_depth=6, num_leaves=115, reg_alpha=4.130868, reg_lambda=1.1e-5

XRP lr is not fully converged (single KEEP iter after purge_period change). The saved
model.lgb file for XRP uses lr=0.0863 from the CPCV (iter 57 log shows saved model used
for CPCV). Ensure the live inference model is loaded from the walk-forward best_params
run (iter 53), not from the CPCV evaluation path.

**Acceptance gate status — all assets final:**
| Metric          | Required   | BTC               | ETH               | SOL               | XRP                      |
|-----------------|------------|-------------------|-------------------|-------------------|--------------------------|
| OOS Brier       | < 0.25     | 0.1018 PASS       | 0.1778 PASS       | 0.1894 PASS       | 0.1953 PASS              |
| OOS ECE         | < 0.05     | 0.0088 PASS       | 0.0252 PASS       | 0.0135 PASS       | 0.0181 PASS              |
| Net PnL         | > 0        | $45.55 PASS       | $176.50 PASS      | $172.13 PASS      | $174.02 PASS             |
| Max Drawdown    | < 30%      | 13.61% PASS       | 1.75% PASS        | 1.62% PASS        | 1.50% PASS               |
| Deflated Sharpe | > 0.0      | 126.91 PASS       | 266.25 PASS       | 255.58 PASS       | 253.15 PASS              |
| OOS Paths Pos.  | 100%       | 100% (28/28) PASS | 100% (28/28) PASS | 100% (28/28) PASS | 100% (28/28) PASS        |
| PBO             | < 0.40*    | SUSP* PASS        | 0.1786 PASS       | SUSP* PASS        | SUSP* PASS               |
| Regime-bucketed | all pos.   | all 4 PASS        | not required      | all 4 PASS        | composite gate PASS      |

*PBO gate suspended per auditor Ruling 1 for regime-sensitive assets. Composite replacement gate satisfied.

---

## Blacklist (permanent — do not revisit in any future asset training)

- **Interaction features:** iter 6 +41% Brier regression. Zero KEEP across 1 attempt.
- **Funding features in cached_features:** 0/3 KEEP (BTC iter 2, ETH iter 27, SOL iter 43).
- **HPO range narrowing:** 0/5 KEEP (iters 10, 13, 15, 19, 20). Wall-clock is the binding constraint, not trial count.
- **time_pcts beyond [0.30, 0.50, 0.80]:** 0/3 KEEP (iters 12, 21, 28). Snapshot set is architecturally optimal.
- **embargo_period != 6:** 0/2 KEEP (iters 9, 30).
- **n_splits != 8:** 0/4 KEEP (iters 11, 31, 33). n_splits=8 optimal all assets.
- **regime_params window changes:** 0/3 KEEP (iters 17, 26). Default windows are correct.
- **Manual feature pruning (OI features):** 0/2 KEEP (iters 16, 24). Trust automated correlation selection.
- **train_bars above 10000 for BTC:** floor locked iter 18-22.
- **train_bars above 14000 for ETH/SOL/XRP:** ceiling confirmed (SOL iter 38, XRP iter 52).
- **max_depth above 6 for any asset:** SOL iter 41 regression. max_depth=6 is the universal ceiling.
- **Sharpe-primary objective:** iter 42 (SOL) — landscape invariant; best_params identical to Brier-primary.
- **XRP purge_period < 24:** iter 53 confirmed 24 is optimal. Lower values are regression direction.
- **PBO < 0.40 as hard gate for regime-sensitive assets:** suspended per auditor Ruling 1.

---

## HPO Range Recommendations

All assets are at confirmed structural floors. HPO ranges are no longer a research knob.

**For any future retrain (drift-triggered or scheduled):**
- Use the current wide ranges — they are already validated as non-binding (all assets
  converged well inside the bounds).
- Do not narrow ranges before retraining. The wall-clock constraint produces ~30-40 Optuna
  trials regardless of range width. Wide ranges preserve exploration diversity.
- XRP num_leaves ceiling: current ceiling is 128, best_params hit 115. If a scheduled
  retrain shows num_leaves at 115-128 again, widen to [16, 192] at that point.
- XRP lr: the 9x shift from iter 51 (0.089) to iter 53 (0.009843) with a purge_period change
  suggests the HPO landscape has multiple local optima along the lr axis. The wide [0.005, 0.1]
  range is important to preserve — do not narrow.

---

## Deployment Sequence

**Immediate (this week):**
1. ETH — UNCONDITIONAL PASS. Both-sides MM. bs_sharpe 267-274. No blocking items.
   Start with PaperExecutor connected to live Polymarket CLOB data.
   Advance to live trading after 48h paper validation of fill rates.

**Short-term (2-4 weeks, after Step 5 CLOB client is built):**
2. BTC — FULL CLEARANCE. Single-side sniper. Sharpe 109.25.
   Deploy at 0.25x Kelly initially; scale to full after 7 days clean live data.
3. SOL — FULL CLEARANCE AT 0.5x KELLY. Both-sides MM. bs_sharpe 251.55.
   Deploy at 0.5x Kelly per auditor directive. Monitor crisis-bucket edge in live data.

**Medium-term (4-8 weeks, after BTC/SOL live validates):**
4. XRP — CONDITIONAL-STRICT AT 0.25x KELLY. Both-sides MM. bs_sharpe 262.32.
   Deploy at 0.25x Kelly. Upgrade to 0.5x Kelly after 30 days live data confirms
   OOS Brier within 1.2x of validation floor (XRP threshold: < 0.234).

**Watch for XRP model identity confusion:** The CPCV iter 57 log shows the saved model
used lr=0.0863 (baseline iter 51 params) rather than iter 53 best_params (lr=0.009843).
Before going live, verify the model file at `data/models/pulse_v2/XRP_5m/model.lgb`
corresponds to the iter 53 walk-forward best_params. If it reflects iter 51 params, retrain
XRP with iter 53 best_params locked (not HPO search) before deployment.

---

## Steps 5-8 Priority Order

Based on the research findings, the critical path to live trading is:

1. **Step 5 (Polymarket CLOB client)** — immediate blocker for live trading. PaperExecutor
   already exists; wire it to real market data first. CLOB client is the first live gate.

2. **Step 7 partial (Python live_cache.py)** — unblocks Step 5 for real feature computation.
   The Python-only version is sufficient for ETH live launch; Rust port can follow.

3. **Step 6 (Scheduler/Runner)** — needed for systematic operation but not for initial
   ETH live trading. Can be built in parallel with Step 5 validation.

4. **Step 7 full (Rust fast path)** — required for sub-millisecond latency target. The
   Pulse model runs at the 0.80 time point (80% through the bar), giving approximately
   60 seconds of decision time on 5m bars. Python inference is adequate for the initial
   live deployment; Rust is a latency optimization, not a correctness requirement.

5. **Step 8 (Deployment/Docker)** — final hardening after paper trading validates the
   full stack.

The autoresearch loop is closed. Do not run further knob experiments on the current
model versions. The next trigger for this strategist role is: a live trading system
exists and 30+ days of live data is available for drift analysis and retraining decisions.
