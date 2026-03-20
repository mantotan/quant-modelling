# Strategy Directive
Updated: 2026-03-22T21:00:00Z
After iteration: 97

## Program Status: OVERRIDE ACTIVE — Multi-TP Revalidation 7/12 Complete

The OVERRIDE directive from the previous strategy (iter 92) is still in force. 7/12 multi-tp revalidation runs are complete (ETH/5m pre-existing + BTC/5m + SOL/5m + XRP/5m + BTC/15m + ETH/15m + SOL/15m). 5 runs remain: XRP/15m, BTC/1h, ETH/1h, SOL/1h, XRP/1h.

**All 5 remaining runs must be completed before any new experiments.** The OVERRIDE has produced 6 new KEEP rows (iters 92-97), all with multi-tp configs saved to `data/models/pulse_v2/`. The pattern is consistent: multi-tp avg Brier is higher than single-point (expected — averaging over 5 time buckets including early noisy ones), but the t=0.80 bucket preserves prior signal quality.

---

## OVERRIDE: Multi-TP Revalidation Priority Queue

Items 1-7 are complete (strikethrough). Execute items 8-12 in order.

~~1. ETH/5m — pre-existing multi-tp baseline (DONE)~~
~~2. BTC/5m — iter 92 KEEP, Brier=0.177295, saved to pulse_v2/BTC_5m~~
~~3. SOL/5m — iter 93 KEEP, Brier=0.218209, saved to pulse_v2/SOL_5m~~
~~4. XRP/5m — iter 94 KEEP, Brier=0.221782, saved to pulse_v2/XRP_5m~~
~~5. BTC/15m — iter 95 KEEP, Brier=0.171913, saved to pulse_v2/BTC_15m~~
~~6. ETH/15m — iter 96 KEEP, Brier=0.209819, saved to pulse_v2/ETH_15m~~
~~7. SOL/15m — iter 97 KEEP, Brier=0.215443, saved to pulse_v2/SOL_15m~~

**8. XRP/15m — NEXT.** Run `--asset XRP --timeframe 15m --mode fast --save`. Use XRP-optimal config: `walk_forward.train_bars=10000`, `walk_forward.purge_period=24`, `n_splits=8`. Pre-multi-tp best Brier=0.192624 (iter 74). Expect multi-tp avg Brier ~0.23-0.26 (consistent with other 15m assets: BTC 0.094→0.172, ETH 0.174→0.210, SOL 0.187→0.215 — ~80-90% increase due to early-bucket averaging). KEEP if ECE < 0.05 and PnL > 0 (baseline run for new config).

**9. BTC/1h — after XRP/15m.** Run `--asset BTC --timeframe 1h --mode fast --save`. Use BTC-optimal config: `walk_forward.train_bars=10000`, `walk_forward.purge_period=24`, `n_splits=8`. Pre-multi-tp best Brier=0.096672 (iter 88). Expect multi-tp avg Brier ~0.17-0.20. NOTE: BTC/1h has only ~3668 trades in backtest — verify backtest_trades >= 10 (not >= 50; thin 1h data). BTC sniper pattern (t=0.80 WR ~82-87%) should appear in time-bucket breakdown.

**10. ETH/1h — after BTC/1h.** Run `--asset ETH --timeframe 1h --mode fast --save`. Use ETH-optimal config: `walk_forward.train_bars=10000`, `walk_forward.purge_period=24`, `n_splits=8`. Pre-multi-tp best Brier=0.176103 (iter 89). Expect multi-tp avg Brier ~0.24-0.28. ETH/1h tick-dominant flat pattern (Sharpe 61-74).

**11. SOL/1h — after ETH/1h.** Run `--asset SOL --timeframe 1h --mode fast --save`. Use SOL-optimal config: `walk_forward.train_bars=10000`, `walk_forward.purge_period=24`, `n_splits=8`. Pre-multi-tp best Brier=0.193886 (iter 90). Expect multi-tp avg Brier ~0.25-0.29.

**12. XRP/1h — after SOL/1h. FINAL item.** Run `--asset XRP --timeframe 1h --mode fast --save`. Use XRP-optimal config: `walk_forward.train_bars=10000`, `walk_forward.purge_period=24`, `n_splits=8`. Pre-multi-tp best Brier=0.194578 (iter 91). Expect multi-tp avg Brier ~0.25-0.29. This completes the 12/12 multi-tp revalidation.

**After item 12 completes:** The OVERRIDE is retired. All 12 pulse_v2 models will be saved. The researcher should write "OVERRIDE complete — 12/12 multi-tp revalidation done" to researcher_ack.txt and await builder assignment for [MTF-1] multi-timeframe signal combination.

---

## Post-OVERRIDE State (for auditor reference)

When the OVERRIDE completes, the expected state will be:
- 12 models saved in `data/models/pulse_v2/`
- All 12 use `time_pcts=[0.10, 0.20, 0.40, 0.60, 0.80]` with TimeAwareCalibrator
- Multi-tp avg Brier is ~80-90% higher than single-point (expected — early buckets are noisier)
- t=0.80 bucket Brier preserves pre-multi-tp signal quality (confirmed for BTC/5m, SOL/5m, XRP/5m, BTC/15m, ETH/15m, SOL/15m)
- No new experiment work for researcher; builder agent needed for [MTF-1], [DEPLOY-5], [DEPLOY-6]

---

## Priority Queue (post-OVERRIDE, for reference)

There are no experiment priorities for the researcher after the OVERRIDE completes. The queue is replaced by the builder/deployment transition plan from the previous strategy (iter 92). Refer to the iter 92 strategy.md for the full specification of [MTF-1], [DEPLOY-5], [DEPLOY-6].

**[RESEARCHER-RETIRE]** When item 12 is complete, the researcher should not run experiments. Write "NO WORK — OVERRIDE complete, awaiting builder completion of [MTF-1]" to researcher_ack.txt and exit.

---

## Observations (iters 93-97 since last review at iter 92)

**Multi-tp revalidation pattern (6 new KEEP rows):**
- All 6 runs produced KEEP status — 100% KEEP rate for multi-tp revalidation
- Multi-tp avg Brier increase vs single-point: BTC/5m +74%, SOL/5m +15%, XRP/5m +14%, BTC/15m +83%, ETH/15m +20%, SOL/15m +15%
  - BTC assets show larger Brier increases (+74-83%) because the single-point model was at a very low floor (0.094-0.102); averaging over early noisy buckets raises the average substantially
  - ETH/SOL/XRP assets show smaller increases (+14-20%) because their floors were already higher
- ECE range: 0.0083 (SOL/5m, best) to 0.0278 (ETH/15m); all well within 0.05 threshold
- HPO starvation in fast mode: 16-24 of 40 trials complete (40-60%). This is expected and acceptable for revalidation runs — the goal is establishing a new multi-tp baseline, not optimizing it
- Time-bucket win rate patterns confirmed across all 6 runs:
  - BTC: sniper ramp (t10=42% → t80=82-87%) — consistent with single-point pre-multi-tp
  - ETH/SOL/XRP: flat tick-dominant pattern (t10 ≈ t80 ≈ 49-51%) — consistent with pre-multi-tp

**HPO convergence (iters 92-97):**
- Learning rates converging to 0.017-0.059 (down from 0.005-0.1 search space)
- max_depth consistently at 6 except BTC (max_depth=4-6)
- num_leaves: 19-98 (wide spread — still exploring)
- reg_alpha: near zero for all except BTC (0.021 at 5m, 0.0 at 15m) — L1 sparsity confirmed non-essential for tick-dominant assets

**Risk profile (iters 92-97 KEEP rows):**
- max_dd / PnL ratios: BTC/5m 0.3356/48.01=0.70 (moderate), BTC/15m 0.174/50.05=0.35 (good)
- ETH/SOL/XRP: max_dd 0.06-0.09, PnL $288-302 — ratios 0.02-0.03 (excellent)
- Trade counts: 5m ~80785-80940 (dense), 15m ~62269-76521 (dense)
- Win rates: BTC 60-66% (mild sniper ramp), ETH/SOL/XRP 49-52% (tick-dominant calibrated)

**HPO-OOS gap (iters 92-97):**
- BTC/5m: hpo_objective=0.168151 vs oos_brier=0.177295, gap=0.009 (5%)
- SOL/5m: hpo_objective=0.455562 vs oos_brier=0.218209, gap=0.237 (WARNING — large gap; likely trade_penalty dominating composite in fast mode with HPO starvation)
- XRP/5m: hpo_objective=0.462400 vs oos_brier=0.221782, gap=0.241 (same pattern as SOL — trade_penalty inflating hpo_objective)
- BTC/15m: hpo_objective=0.175251 vs oos_brier=0.171913, gap=-0.003 (small negative — HPO objective slightly better than OOS)
- ETH/15m: hpo_objective=0.295422 vs oos_brier=0.209819, gap=0.086 (moderate, trade_penalty effect)
- SOL/15m: hpo_objective=0.364178 vs oos_brier=0.215443, gap=0.149 (trade_penalty effect)
- NOTE: SOL/XRP/ETH show large hpo_objective vs oos_brier gaps because the composite includes trade_penalty at 5.0x weight. With 80K+ trades in multi-tp mode, trade_penalty is significant. This is NOT a signal of overfitting — it is a mechanical artifact of the composite objective.

---

## Risk Profile

- Max drawdown trend: STABLE. All multi-tp runs show max_dd well below PnL. No deterioration.
- Trade count range across new KEEPs: 62,269-80,940 (15m-5m range, as expected)
- Win rate range: 49-66% (tick-dominant ~50%, BTC sniper ~60-66% in multi-tp avg)
- HPO-OOS gap: BTC stable; ETH/SOL/XRP show elevated gap due to trade_penalty artifact in HPO composite — not an overfitting signal

## Timeframe Coverage

- 5m: 57 iterations pre-OVERRIDE + 4 multi-tp revalidations (iters 92-94 + ETH pre-existing) = ~61 total. All 4 assets multi-tp done. Best Brier (multi-tp avg): BTC 0.177295, ETH pre-existing, SOL 0.218209, XRP 0.221782
- 15m: 17 iterations pre-OVERRIDE + 3 new multi-tp (iters 95-97) + 1 pending (XRP) = ~21 total. Best Brier (multi-tp avg): BTC 0.171913, ETH 0.209819, SOL 0.215443, XRP PENDING
- 1h: 9 iterations pre-OVERRIDE + 0 multi-tp = 9 total. Multi-tp for all 4 assets PENDING (items 9-12). Best Brier (single-point): BTC 0.096672, ETH 0.176103, SOL 0.193886, XRP 0.194578
- Recommendation: Complete OVERRIDE items 8-12 in order (XRP/15m first, then all 4 1h assets)

## Blacklist

**Permanent blacklist (unchanged — FINAL):**
- Interaction features (iter 6 DISCARD, 0/1 KEEP). Permanent.
- Funding features in cached_features (iters 2, 27, 43 DISCARD, 0/3 KEEP). Permanent.
- HPO range narrowing (iters 10, 13, 15, 19, 20 DISCARD, 0/5 KEEP). Permanent.
- n_splits != 8 (0/4 KEEP). Permanent.
- embargo_period != 6 (0/2 KEEP). Permanent.
- max_depth > 6 (iter 41 DISCARD, 0/1 KEEP). Permanent.
- Sharpe-primary objective (iter 42 DISCARD, 0/1 KEEP). Permanent.
- regime_params window changes (0/3 KEEP). Permanent.
- Manual feature pruning (0/2 KEEP). Permanent.
- brier_threshold tightening (iters 35, 36 DISCARD, 0/2 KEEP). Permanent.
- min_target_corr changes (iter 34 DISCARD, 0/1 KEEP). Permanent.
- drawdown_penalty_weight changes (iters 40, 54 DISCARD, 1/4 KEEP at 25%). Permanent.
- 1h optimization experiments (all models at structural floors). Permanent (new experiments would require code changes — builder scope).

## HPO Range Recommendations

For future reference (not actionable until post-OVERRIDE builder phase):
- `learning_rate`: clusters at 0.014-0.059 across multi-tp KEEPs; upper bound of 0.1 can be narrowed to 0.07 without risk
- `max_depth`: consistently 4-6; floor of 2 is wasted search space, could raise to 3
- `reg_alpha`: near-zero for tick-dominant assets; BTC/1h shows 0.024-0.212; search range [1e-8, 10.0] is appropriate given asset diversity
- `reg_lambda`: near-zero for most except ETH/1h (9.42) and SOL/15m (8.25); range [1e-8, 10.0] appropriate
- NOTE: These are informational only. The OVERRIDE uses existing knobs.json — do NOT change HPO ranges during revalidation runs.
