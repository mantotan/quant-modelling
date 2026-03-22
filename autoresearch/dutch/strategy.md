# Dutch Strategy
Updated: after iteration 119 (2026-03-23T21:30:00Z) — STRATEGIST rotation 9 analysis

## Summary

Rotation 8 complete (iters 108-119). KEEP rate this rotation: **0/12 = 0%** — worst rotation yet.
Overall V7.3 KEEP rate (iters 33-119): 29/87 = 33.3%.

Key findings from rotation 8:
1. **ETH_5m onesided floor confirmed at 1.5** (iter 119): onesided 1.5->1.0 COLLAPSE (same as ETH_15m
   at iter 94). Floor pattern: ETH_5m=1.5, ETH_15m=1.5, SOL_5m=2.0, BTC_5m=2.0. Onesided series
   fully exhausted on all tested pairs.
2. **BTC_5m onesided floor confirmed at 2.0** (iter 117): onesided 2.0->1.5 COLLAPSE. Floor=2.0
   confirmed (same as SOL_5m). BOTH onesided series exhausted on BTC/SOL 5m pairs.
3. **SOL_15m onesided=2.0 COLLAPSES** (iter 111): floor could not be confirmed without COLLAPSE.
   SOL_15m is fundamentally different — onesided cap BLACKLISTED entirely for SOL_15m.
4. **SOL_15m budget scaling exhausted** (iter 112): bar_budget 300->400 neutral cost (+0.01%),
   max_dd improved but pair_cost didn't beat best. Budget at 300 confirmed optimum.
5. **conviction_market_start globally failing**: iters 115 (XRP_15m), 116 (XRP_1h) both DISCARD.
   Prior DISCARDs: iter 106 (BTC_1h). GLOBALLY BLACKLISTED — do not test on any remaining pair.
6. **ETH_1h bar_budget exhausted**: 200->250 DISCARD (iter 108), 200->300 already exhausted at baseline.
   Budget=200 confirmed optimum for ETH_1h.
7. **SOL_5m dataset instability** (iter 109): matched_ratio collapsed to 0% on 416 bars. Pair is
   structurally fragile at 0.94% matched_ratio. Re-eval needed before any new experiments.
8. **BTC_1h dataset regression deepening** (iter 118): pair_cost 0.9042 on 37 bars — far above best
   KEEP of 0.7988 (33 bars). Each new bar adding negative signal. Dataset too thin for reliable results.

Critical stale knobs issues detected:
- **ETH_15m**: knobs + best_knobs show conviction_buy_skip=0.55 but KEEP iter 54 confirmed skip=0.45.
  Researcher MUST fix this immediately before any ETH_15m experiment.
- **SOL_1h**: knobs_SOL_1h.json shows bar_budget=400 but best KEEP for budget is 300 (iter 86);
  iter 112 confirmed 400 DISCARD. Researcher MUST fix SOL_1h knobs to bar_budget=300.
- **BTC_1h**: best_knobs_BTC_1h.json shows risk_ceil=0.20 but no KEEP ever confirmed this.
  Correct value is risk_ceil=0.15 (V7.3 baseline).

Current best_knobs state (post-iter-119):
- ETH_5m: skip=0.45, onesided=1.5 (pair_cost=0.633, max_dd=13.8%, avg_profit=+$0.01/bar) — PROFITABLE, floor confirmed
- XRP_15m: skip=0.45, pace_urgency_lo=0.30, onesided=2.0 (pair_cost=0.638, avg_profit=-$0.01/bar) — near-profitable
- ETH_15m: skip=0.45 (STALE FILE says 0.55), onesided=1.5 (pair_cost=0.560 best / volatile 123-bar)
- SOL_1h: skip=0.45, bar_budget=300 (pair_cost=0.655, avg_profit=+$0.69/bar; knobs file STALE at 400)
- XRP_1h: skip=0.50, pace_urgency_lo=0.35 (pair_cost=0.674, avg_profit=+$1.08/bar)
- SOL_5m: skip=0.45, onesided=2.0, pace_urgency_lo=0.30 (pair_cost=0.676, avg_profit=+$0.06/bar) — PROFITABLE
- SOL_15m: skip=0.45, bar_budget=300, risk_ceil=0.20 (pair_cost=0.696, avg_profit=+$0.42/bar) — PROFITABLE
- ETH_1h: skip=0.45 (pair_cost=0.706, avg_profit=-$0.49/bar)
- BTC_1h: skip=0.40 (best KEEP=0.799, current 37-bar=0.904 regression)
- XRP_5m: FREEZE (pair_cost=0.909, max_dd=68.7%)
- BTC_5m: skip=0.50, onesided=2.0 (pair_cost=0.922, avg_profit=+$0.19/bar)
- BTC_15m: skip=0.50 (pair_cost=0.933, zero KEEPs, skip=0.45 definitively blacklisted)

---

## BTC_5m (pair_cost=0.922, KEEP rate 1/10=10%, max_dd=15.3%)
V7.3 + 1 KEEP: max_onesided_cost 5.0->2.0 (iter 104).
Onesided series exhausted: 2.0 KEEP, 1.5 COLLAPSE (iter 117). Floor=2.0 confirmed.
Skip directions exhausted (0.45 D iter 33, 0.55 D iter 50). cheap_threshold exhausted.
avg_profit=+$0.19/bar positive — structural fundamentals are OK.
pair_cost gap to target: 0.922 vs 0.85 = gap of +0.072.

Priority queue:
1. pace_urgency_lo 0.35->0.30 — XRP_15m showed 18% gain (iter 102). BTC_5m matched_ratio=0.1%
   is razor-thin. Earlier urgency timing (entering at 30% of urgency window) may capture more
   qualifying pairs. This is the highest-value untested lever remaining.
   Accept KEEP if pair_cost improves >5% (target: <0.876). Monitor matched_ratio — must stay >0.05%.
2. pace_urgency_lo 0.30->0.25 — follow series IF #1 KEEPs. BTC_5m may respond like XRP_15m.
3. sell_min_shares increase — currently untested. If pair_cost remains stuck above 0.90, explore
   sell_min_shares to reduce premature recycling. Test ONLY after pace_urgency levers resolved.

Blacklists (BTC_5m): unmatched_ratio tightening, sell_loss_start tightening,
conviction_buy_skip 0.45 (D iter 33), conviction_buy_skip 0.55 (D iter 50),
cheap_threshold 0.07 (D iter 17), cheap_threshold 0.12 (D iter 62),
max_onesided_cost 5->3 (D iter 89 — sub-threshold), max_onesided_cost 2.0->1.5 (COLLAPSE iter 117).
SKIP SERIES EXHAUSTED. ONESIDED SERIES EXHAUSTED at floor=2.0.

---

## BTC_15m (pair_cost=0.933, KEEP rate 0/7=0%, max_dd=23%)
V7.3 best: avg_profit=+$0.50/bar, correct_side=63%, matched_ratio=12%.
Zero KEEPs across 7 rotations. Skip=0.45 definitively incompatible (3 confirmations).
Strong fundamentals (63% correct_side, +$0.50/bar) but pair_cost persistently stuck.
No onesided experiments yet — highest remaining untested structural lever.
pair_cost gap to target: 0.933 vs 0.85 = gap of +0.083.

Priority queue:
1. max_onesided_cost 5.0->2.0 (ALONE, no skip change) — ETH_5m/SOL_5m/BTC_5m all KEEP at 2.0.
   BTC_15m has 12% matched_ratio — LOWEST collapse risk among all pairs. This is the most
   promising lever with the lowest risk. Should have been tested 2 rotations ago.
   Accept KEEP if pair_cost improves >2% (given BTC_15m has already improved from 0.963 to 0.933).
2. pace_urgency_lo 0.35->0.30 — XRP_15m 18% gain pattern. BTC_15m moderate matched_ratio (12%)
   means less collapse risk than low-matched pairs. High confidence in positive outcome.
   Test after onesided experiment (compound improvement possible).
3. max_onesided_cost 2.0->1.5 — IF #1 KEEPs. BTC_15m higher matched_ratio means less collapse
   risk than 5m peers. ETH_15m floor was 1.5 (10% matched_ratio) — BTC_15m at 12% may match.

Blacklists (BTC_15m): unmatched_ratio tightening, max_marginal_pair_cost below 1.01,
cheap_threshold to 0.07, bar_budget before cost fix (D iter 63),
bar_budget 400 (D iter 36),
conviction_buy_skip 0.45 in ANY combination (D iters 51, 78, 90 — 3 tests confirm collapse),
conviction_market_start (GLOBALLY BLACKLISTED).
SKIP=0.45 DIRECTION DEFINITIVELY EXHAUSTED.

---

## BTC_1h (pair_cost=0.799 best / 0.904 on current 37 bars, KEEP rate 2/12=17%, max_dd=9%)
V7.3 + 2 KEEPs: skip=0.45 (iter 52), skip=0.40 (iter 64).
Dataset thin (37 bars) — every new bar adding negative signal. 4 unfavorable bars since KEEP.
IMPORTANT stale knobs: best_knobs_BTC_1h.json shows risk_ceil=0.20 but NO KEEP ever confirmed this.
Researcher MUST correct best_knobs to risk_ceil=0.15 before any experiment.
Dataset regression is structural — pair_cost will NOT return to 0.799 until data improves.

Priority queue:
1. pace_urgency_lo 0.35->0.45 — NOTE: knobs_BTC_1h already shows pace_urgency_lo=0.45 (set by
   researcher per rotation 7 strategy). Verify if this was actually tested. Check iter 118 description:
   iter 118 was a DISCARD but tested conviction_buy_skip re-eval, not pace_urgency_lo. So knobs
   may have been updated without running the test. If pace_urgency_lo=0.45 is untested in results.tsv:
   run this test now. If already tested: skip to #2.
2. max_onesided_cost 5.0->2.0 — if pace_urgency_lo test doesn't resolve dataset regression.
   Iter 91 (5->3) only 1% gain. 2.0 is final test. Low expectations given thin dataset.
3. HOLD pattern — if dataset regression continues for 5+ more iters without improvement,
   consider declaring BTC_1h as structural floor pair. Best known cost is 0.799 (33 bars).

Blacklists (BTC_1h): risk_ceil 0.10 (D iter 5), risk_ceil tightening,
sell_loss_start tightening, pace_urgency_hi loosening, bar_budget 400 (D iter 36),
conviction_buy_skip 0.50 (D iter 64 — confirmed skip=0.40 is floor),
max_onesided_cost 5->3 (D iter 91 — sub-threshold at 1%),
conviction_market_start 0.30->0.25 (D iter 106 — GLOBALLY BLACKLISTED).

---

## ETH_5m (pair_cost=0.633, KEEP rate 4/7=57%, max_dd=13.8%)
V7.3 + 4 KEEPs (iters 65, 66, 92, 107): re-eval + skip=0.45 + onesided=2.0 + onesided=1.5.
Rotation 8: onesided 1.5->1.0 COLLAPSED (iter 119). Floor=1.5 confirmed.
ALL onesided levels exhausted (5->2->1.5 all KEEP, 1.0 COLLAPSE).
OUTSTANDING performance: pair_cost=0.633 (<0.85 target), max_dd=13.8%, avg_profit=+$0.01/bar POSITIVE.
ALL BENCHMARKS MET.

Priority queue:
1. pace_urgency_lo 0.35->0.30 — XRP_15m 18% gain pattern; SOL_5m knobs already at 0.30.
   ETH_5m at 0.8% matched_ratio (ultra-selective). Earlier urgency timing may slightly expand
   qualifying pool. Highest remaining untested lever.
   Accept KEEP if pair_cost improves >2% (already below target; any gain is additive).
2. conviction_buy_skip 0.45->0.40 — context now has onesided=1.5 + positive avg_profit.
   DD=13.8% provides buffer. correct_side=42.9% is low-moderate. Monitor — if correct_side
   drops below 40%: abort and blacklist skip=0.40 on ETH_5m.
3. bar_budget 200->300 — POSITIVE avg_profit makes capital scaling viable.
   Test after pace_urgency_lo resolves. ETH_5m is the most scalable pair currently.

Blacklists (ETH_5m): unmatched_ratio tightening, conviction_buy_skip raising above 0.50,
conviction_buy_skip 0.60 (D iter 37), max_onesided_cost 1.5->1.0 (COLLAPSE iter 119).
ONESIDED SERIES FULLY EXHAUSTED at floor=1.5.

---

## ETH_15m (pair_cost=0.560 best / volatile, KEEP rate 4/10=40%, max_dd=27%)
V7.3 + 4 KEEPs: re-eval (iter 53), skip=0.45 (iter 54), onesided=2.0 (iter 68), onesided=1.5 (iter 82).
CRITICAL STALE KNOBS: both knobs_ETH_15m.json AND best_knobs_ETH_15m.json show conviction_buy_skip=0.55
but iter 54 KEEP confirmed skip=0.45. Researcher MUST fix BOTH files immediately.
Onesided=1.0 collapsed (iter 94). Onesided series exhausted.
No rotation 8 experiments — structural stagnation.
pair_cost best=0.560 but volatile; 123-bar dataset shows ~0.675 average.

Priority queue:
1. FIX STALE KNOBS FIRST — Set conviction_buy_skip=0.45 in BOTH knobs_ETH_15m.json and
   best_knobs_ETH_15m.json before any experiment.
2. pace_urgency_lo 0.35->0.30 — XRP_15m's 18% gain. ETH_15m 1% matched_ratio is limiting;
   earlier urgency gate may capture more pairs. After fixing stale knobs, run this test with corrected baseline.
   Accept KEEP if pair_cost improves >5% on fresh re-eval (baseline ~0.675).
3. bar_budget 200->300 — scale capital at confirmed onesided=1.5.
   Test after pace_urgency_lo resolves. Accept KEEP if pair_cost stays below 0.72.

Blacklists (ETH_15m): unmatched_ratio tightening, conviction_buy_skip raising to 0.55,
max_onesided_cost increasing above 1.5 (zero effect), max_onesided_cost 1.5->1.0 (D iter 94 — collapse),
conviction_market_start (GLOBALLY BLACKLISTED).
ONESIDED SERIES EXHAUSTED at 1.5 floor.

---

## ETH_1h (pair_cost=0.706, KEEP rate 2/7=29%, max_dd=17%)
V7.3 + 2 KEEPs: re-eval (iter 39), skip=0.45 (iter 40).
Rotation 8: bar_budget 200->250 DISCARD (iter 108) — budget=200 confirmed optimum.
Bar_budget=200 AND 250 AND 300 all tested/exhausted. Skip floor at 0.45 confirmed.
pace_urgency_lo untested — highest remaining lever.
avg_profit=-$0.49/bar negative (worse than most other pairs).

Priority queue:
1. pace_urgency_lo 0.35->0.30 — XRP_15m's 18% gain strongly suggests this lever is high-value.
   ETH_1h at 7% matched_ratio is moderate — earlier urgency timing may capture better pairs.
   High-confidence test given XRP_15m result. Primary lever.
2. pace_urgency_lo 0.30->0.25 — follow series if #1 KEEPs.
3. max_onesided_cost 5.0->2.0 — if pace_urgency_lo fails. DD=17% provides headroom.
   Verify matched_ratio (7%) suggests moderate collapse risk — test cautiously.

Blacklists (ETH_1h): max_onesided_cost increasing above $5 (D iter 55 — zero effect),
conviction_buy_skip 0.40 (D iter 69), risk_ceil 0.15->0.20 (D iter 83 — only 3.8%),
bar_budget 250 (D iter 108), bar_budget 300 (exhausted from baseline context),
conviction_market_start (GLOBALLY BLACKLISTED).
BUDGET OPTIMUM AT 200. SKIP FLOOR AT 0.45.

---

## SOL_5m (pair_cost=0.676, KEEP rate 4/7=57%, max_dd=18.1%)
V7.3 + 4 KEEPs: re-eval + skip=0.45 + onesided=2.0 + re-eval (iters 70, 71, 84, 96).
Onesided floor=2.0 confirmed (iter 97 DISCARD at 1.5). All benchmarks met.
Rotation 8: re-eval COLLAPSED (iter 109) — matched_ratio 0%->0% on 416 bars. HIGH variance risk.
CRITICAL: pair is structurally fragile at 0.94% matched_ratio. MUST re-eval with fresh data before any experiment.
NOTE: knobs_SOL_5m.json shows pace_urgency_lo=0.30 — this was apparently set but results.tsv shows
no KEEP for pace_urgency_lo on SOL_5m. This was likely set from a stale auditor directive without testing.
Verify if pace_urgency_lo=0.30 is confirmed via a results.tsv experiment or revert to 0.35.

Priority queue:
1. Re-eval with current best_knobs — confirm matched_ratio is non-zero (iter 109 showed 0.0%).
   If matched_ratio returns to ~0.94%: proceed with structural experiments.
   If matched_ratio remains 0%: investigate engine/dataset issue; hold all SOL_5m experiments.
2. pace_urgency_lo test — ONLY if re-eval confirms stability. If knobs already at 0.30 without a KEEP,
   run a proper experiment to document it in results.tsv. Test 0.35->0.30 or verify existing 0.30 value.
3. conviction_buy_skip 0.45->0.40 — DD=18.1% and positive avg_profit provide buffer.
   matched_ratio=0.94% is critically low — collapse risk. Use extreme caution.

Blacklists (SOL_5m): conviction_buy_skip raising to 0.55 (D iter 41),
max_onesided_cost 2.0->1.5 (D iter 97 — COLLAPSE, floor=2.0).
NOTE: pace_urgency_lo=0.30 in knobs file needs verification — check if properly tested.

---

## SOL_15m (pair_cost=0.696, KEEP rate 5/10=50%, max_dd=17.3%)
V7.3 + 5 KEEPs: skip=0.45 (56), re-eval (72), bar_budget=300 (73), re-eval (98), risk_ceil=0.20 (99).
Rotation 8: THREE DISCARDs (iters 110, 111, 112).
- iter 110: re-eval regression 2.7% on 3 new bars — dataset variance
- iter 111: onesided=2.0 COLLAPSED matched_ratio to 0% — BLACKLISTED
- iter 112: bar_budget 300->400 DISCARD — 300 confirmed optimum
ALL structural levers (onesided, budget scaling) now exhausted. Risk_ceil=0.20 is current best.
pair_cost gap to target: 0.696 vs 0.85 = TARGET MET (-0.154).

Priority queue:
1. pace_urgency_lo 0.35->0.30 — XRP_15m's 18% gain. SOL_15m has 8.8% matched_ratio — moderate,
   earlier urgency timing may improve fill quality without collapsing matching.
   This is the PRIMARY remaining lever after onesided and budget exhaustion.
2. risk_ceil 0.20->0.25 — current risk_ceil=0.20 KEEP (iter 99). Further scaling given positive
   avg_profit=+$0.42/bar. ONLY if pace_urgency_lo test is stable or positive.
3. conviction_buy_skip 0.45->0.40 — with DD=17.3% and positive profit, buffer exists.
   But skip=0.40 COLLAPSED on SOL_15m at iter 85. TEST ONLY with pace_urgency_lo in place first.

Blacklists (SOL_15m): min_unmatched_shares tightening,
conviction_buy_skip raising above 0.50, conviction_buy_skip 0.40 (D iter 85 — confirmed collapse),
bar_budget BEFORE cost/risk fixes, bar_budget 400 (D iter 112 — optimum at 300),
max_onesided_cost 5.0->2.0 (D iter 111 — COLLAPSE on SOL_15m, BLACKLISTED entirely),
conviction_market_start (GLOBALLY BLACKLISTED).
SKIP SERIES FULLY EXHAUSTED. ONESIDED BLACKLISTED. BUDGET OPTIMUM AT 300.

---

## SOL_1h (pair_cost=0.655 best KEEP / 0.658 last re-eval, KEEP rate 3/8=38%, max_dd=5.8%)
V7.3 + 3 KEEPs: re-eval (iter 43), skip=0.45 (iter 58), bar_budget=300 (iter 86).
Rotation 8: iter 113 re-eval with corrected skip=0.45 — pair_cost=0.6581 (vs best 0.6547, +0.5%).
DISCARD on strict criterion but within noise. Stale knob (skip=0.55) fixed by researcher.
CRITICAL stale knobs: knobs_SOL_1h.json shows bar_budget=400 but NO KEEP for 400.
iter 112 confirmed 400 DISCARD on SOL_15m; SOL_1h budget was never tested at 400 from results.tsv.
Researcher MUST set knobs_SOL_1h.json bar_budget=300 (the confirmed KEEP from iter 86).
Dataset relatively stable (iter 113 showed pair_cost≈best). Most stable of the volatile pairs.
avg_profit=+$1.49/bar (second only to XRP_1h). Strong fundamentals.

Priority queue:
1. FIX STALE KNOBS: set bar_budget=300 in knobs_SOL_1h.json before ANY experiment.
2. bar_budget 300->400 — SOL pair budget scaling pattern. avg_profit=+$1.49/bar is excellent.
   Re-eval in iter 113 showed stability (0.6581 vs best 0.6547). Run bar_budget 300->400 as
   next experiment after fixing knobs. HIGH VALUE given positive avg_profit.
3. pace_urgency_lo 0.35->0.30 — XRP_15m pattern. SOL_1h fill_rate=89.2%; earlier urgency
   may squeeze further quality at 1.9% matched_ratio.

Blacklists (SOL_1h): conviction_buy_skip 0.35 (COLLAPSE iter 57), skip=0.40 (D iter 74),
risk_ceil 0.15->0.20 (D iters 100-101 — tested in regression window, avoid retesting until stable),
conviction_market_start (GLOBALLY BLACKLISTED).
SKIP SERIES FULLY EXHAUSTED on SOL_1h.

---

## XRP_5m (pair_cost=0.909, KEEP rate 1/3=33%, max_dd=68.7%)
FROZEN (iter 114 — auditor directive). Structural dead-end:
fill_rate=54% (structural microstructure limit), max_dd=69% (critical), no profitable pathway confirmed.
fill_ticks experiments exhausted (D iter 59 at 15). Do not run experiments until auditor lifts freeze.

Priority queue: FREEZE MAINTAINED. No experiments.

Blacklists (XRP_5m): ALL levers blacklisted pending freeze review.
conviction_buy_skip raising above 0.50, fill_ticks 10->15 (D iter 59 — structural limit),
conviction_market_start (GLOBALLY BLACKLISTED).

---

## XRP_15m (pair_cost=0.638, KEEP rate 2/7=29%, max_dd=11%)
V7.3 + 2 KEEPs: skip=0.45 (iter 46, +18.6%), pace_urgency_lo=0.30 (iter 102, +18.0%).
LANDMARK: pace_urgency_lo 0.35->0.30 gave 18% improvement (iter 102).
Rotation 8: conviction_market_start 0.30->0.25 DISCARD (iter 115) — globally blacklisted.
NOTE: knobs_XRP_15m.json shows pace_urgency_lo=0.25 — this appears pre-emptively set without a KEEP.
Verify results.tsv: no iter shows pace_urgency_lo 0.30->0.25 KEEP on XRP_15m.
If pace_urgency_lo=0.25 is not in results.tsv as KEEP, researcher must revert to 0.30 and TEST properly.
avg_profit=-$0.01/bar (near-zero, close to profitable).

Priority queue:
1. pace_urgency_lo 0.30->0.25 — MUST be properly tested and documented in results.tsv.
   If knobs file shows 0.25 without a results.tsv KEEP: run the test from 0.30->0.25.
   XRP_15m responded MASSIVELY to 0.35->0.30 (18% gain). Series continuation high-priority.
   Risk: matched_ratio already at 0.3% — any further reduction may collapse pair formation entirely.
   If matched_ratio drops to 0.0%: floor=0.30 confirmed, revert knobs to 0.30.
2. bar_budget 200->250 — cautious capital scale on near-profitable pair.
   XRP_15m confirmed 200 is optimum over 300 (D iter 75); try small intermediate step (250).
   Only test after pace series resolves.
3. max_onesided_cost 2.0->1.5 — IF matched_ratio can support it. Very risky given 0.3%.

Blacklists (XRP_15m): conviction_buy_skip 0.40 (D iter 60 — collapsed),
bar_budget 300 (D iter 75 — optimum at 200), risk_ceil 0.15->0.20 (D iter 87 — worsened),
conviction_market_start (GLOBALLY BLACKLISTED — D iter 115).
SKIP EXHAUSTED. BUDGET OPTIMUM AT 200.

---

## XRP_1h (pair_cost=0.674, KEEP rate 1/7=14%, max_dd=6%)
V7.3 + 1 KEEP: re-eval (iter 47, +5.87%).
All major levers tested: skip exhausted, risk_ceil failed, bar_budget failed at 300.
pace_urgency_lo zero effect on 1h TF (D iter 103).
Rotation 8: conviction_market_start 0.30->0.25 DISCARD (iter 116) — globally blacklisted.
NOTE: knobs_XRP_1h.json shows max_onesided_cost=2.0 — this appears to have been set without a KEEP.
Verify results.tsv: no iter shows onesided KEEP on XRP_1h. Iter 48 D was conviction_buy_skip.
If max_onesided_cost=2.0 is not in results.tsv as KEEP: researcher must document the experiment.
avg_profit=+$1.08/bar is system-best avg_profit. max_dd=6% excellent.

Priority queue:
1. max_onesided_cost test verification — if knobs show 2.0 without results.tsv KEEP:
   run onesided 5.0->2.0 test and document. DD=6% so cap effect may be minimal.
2. pace_urgency_hi 0.85->0.75 — alternative urgency gate tuning (different from lo).
   pace_urgency_lo confirmed INEFFECTIVE on 1h TF. pace_urgency_hi untested.
   Lower hi threshold may help timing cadence for 1h bars.
3. max_per_prediction test — if all other levers exhausted. Very low matched_ratio (3.4%)
   suggests constraint on order frequency. Untested lever.

Blacklists (XRP_1h): conviction_buy_skip 0.45 (D iter 48), conviction_buy_skip 0.55 (D iter 61),
bar_budget 300 (D iter 76 — optimum at 200), risk_ceil 0.15->0.20 (D iter 88 — worsened),
pace_urgency_lo 0.35->0.45 (D iter 103 — zero effect on 1h TF),
conviction_market_start (GLOBALLY BLACKLISTED — D iter 116).
BOTH SKIP DIRECTIONS EXHAUSTED. BUDGET OPTIMUM AT 200. PACE_URGENCY_LO INEFFECTIVE ON 1h.

---

## Cross-Pair Observations

**Rotation 8 lesson — onesided collapse is universal at low matched_ratio:**
- ETH_5m floor=1.5, ETH_15m floor=1.5, SOL_5m floor=2.0, BTC_5m floor=2.0
- SOL_15m: onesided=2.0 COLLAPSES — fundamentally different; onesided blacklisted
- Pattern: pairs with matched_ratio <2% collapse at lower onesided values
- For remaining pairs (BTC_15m 12% matched_ratio): onesided=2.0 should be SAFE

**pace_urgency_lo series is the dominant remaining lever:**
- XRP_15m: 0.35->0.30 gave 18% gain (iter 102) — LANDMARK
- SOL_5m: knobs at 0.30 (needs verification)
- Untested on: BTC_5m, BTC_15m, ETH_5m, ETH_15m, ETH_1h, SOL_15m, SOL_1h, XRP_1h (lo ineffective on 1h)
- Hypothesis: pace_urgency_lo 0.30 should be the NEXT test for all 5m and 15m pairs

**conviction_market_start globally blacklisted (CONFIRMED rotation 8):**
- DISCARDs: iter 106 BTC_1h, iter 115 XRP_15m, iter 116 XRP_1h
- Pattern confirmed across 1h and 15m TFs: lower market entry bar admits weaker predictions
- DO NOT test on any remaining pair

**Stale knobs audit required before rotation 9 begins:**
- ETH_15m: conviction_buy_skip 0.55 -> 0.45 (BOTH files)
- SOL_1h: bar_budget 400 -> 300 (knobs file only)
- BTC_1h: risk_ceil 0.20 -> 0.15 (best_knobs file only)
- SOL_5m: verify pace_urgency_lo=0.30 is documented in results.tsv or revert to 0.35
- XRP_15m: verify pace_urgency_lo=0.25 is documented in results.tsv or revert to 0.30
- XRP_1h: verify max_onesided_cost=2.0 is documented in results.tsv or run the experiment

**Skip floor mapping (fully confirmed through rotation 8):**
- skip=0.40 floor: BTC_1h (KEEP iter 64)
- skip=0.45 floor: ETH_1h, SOL_1h, XRP_15m, SOL_15m, SOL_5m, ETH_5m, ETH_15m
- skip=0.50 floor: XRP_1h, BTC_5m
- skip=0.45 definitively fails: BTC_15m (3 tests confirm collapse)
- Series still active: none confirmed open on ETH_5m (skip=0.40 possible with buffer)

**Dataset variance warning — 1h pairs are unreliable:**
- BTC_1h: 37 bars, each new bar adds negative signal, pair_cost 0.799->0.904 regression
- SOL_1h: 36 bars, 2 new bars caused 25.6% regression in rotation 7 (now stabilizing at iter 113)
- ETH_1h: 36 bars (estimated), high variance expected
- All 1h pairs require fresh re-eval before every structural experiment

---

## trader_a Benchmark Comparison (post-iter-119 best_knobs)
| Pair | PairCost | Target | Gap | AvgProfit | MaxDD% | Trend |
|------|----------|--------|-----|-----------|--------|-------|
| BTC_5m | 0.922 | < 0.85 | +0.072 | +$0.19 | 15.3% | stuck — pace_urgency_lo=0.30 next |
| BTC_15m | 0.933 | < 0.85 | +0.083 | +$0.50 | 23% | stuck — onesided=2.0 URGENT, untested |
| BTC_1h | 0.799 | < 0.85 | -0.051 | variable | 9% | regression on thin 37-bar dataset |
| ETH_5m | 0.633 | < 0.85 | -0.217 | +$0.01 | 13.8% | PROFITABLE; pace_urgency_lo=0.30 next |
| ETH_15m | 0.560 | < 0.85 | -0.290 | -$0.21 | 27% | BEST cost — stale knobs critical fix needed |
| ETH_1h | 0.706 | < 0.85 | -0.144 | -$0.49 | 17% | beats benchmark; pace_urgency_lo=0.30 next |
| SOL_5m | 0.676 | < 0.85 | -0.174 | +$0.06 | 18.1% | PROFITABLE; re-eval needed first |
| SOL_15m | 0.696 | < 0.85 | -0.154 | +$0.42 | 17.3% | PROFITABLE; pace_urgency_lo=0.30 next |
| SOL_1h | 0.655 | < 0.85 | -0.195 | +$0.69 | 5.8% | PROFITABLE; stale knob fix + budget=400 test |
| XRP_5m | 0.909 | < 0.85 | +0.059 | -$0.32 | 68.7% | FROZEN — structural dead-end |
| XRP_15m | 0.638 | < 0.85 | -0.212 | -$0.01 | 11% | near-profitable; pace_urgency_lo=0.25 next (verify knobs) |
| XRP_1h | 0.674 | < 0.85 | -0.134 | +$1.08 | 6% | BEST avg_profit; onesided test needed (verify knobs) |

**5 pairs PROFITABLE** (ETH_5m, SOL_5m, SOL_15m, SOL_1h, XRP_1h) — unchanged from rotation 7.
**10 pairs beating trader_a pair_cost benchmark** — BTC_5m, BTC_15m, XRP_5m still above.
BTC_15m remains most stubborn pair (0/7 KEEPs, onesided=2.0 is last high-confidence lever).

---

## Global Blacklist
- conviction_market_start: ALL pairs (D iters 106, 115, 116 — confirmed globally useless)
- conviction_buy_skip raising (all pairs: raises always worsen, never lower)
- unmatched_ratio tightening (D iters 16, 19, 20 — always worsens pair_cost)
- max_onesided_cost below pair-specific floors (onesided COLLAPSE patterns confirmed)
- sell_loss_start tightening (D iters 1, 18 — disrupts pair formation)
- max_marginal_pair_cost below 1.01 (D iter 3 — collapses pair formation)

## Pair Blacklist Summary
- BTC_5m: skip 0.45/0.55, cheap_threshold 0.07/0.12, onesided 1.5 (COLLAPSE)
- BTC_15m: skip 0.45 (3x confirmed), max_marginal_pair_cost <1.01, onesided TBD
- BTC_1h: skip raising >0.50, risk_ceil tightening, sell_loss_start, pace_urgency_hi, bar_budget 400
- ETH_5m: skip raising >0.50, skip 0.60, onesided 1.0 (COLLAPSE)
- ETH_15m: skip raising to 0.55, onesided 1.0 (COLLAPSE), bar_budget before onesided fix
- ETH_1h: skip 0.40, risk_ceil increase, bar_budget 250/300
- SOL_5m: skip raising to 0.55, onesided 1.5 (COLLAPSE floor=2.0)
- SOL_15m: skip 0.40, skip raising, onesided 2.0 (COLLAPSE — all onesided blacklisted), bar_budget 400
- SOL_1h: skip 0.35 (COLLAPSE), skip 0.40, risk_ceil increase
- XRP_5m: ALL (FROZEN)
- XRP_15m: skip 0.40 (COLLAPSE), bar_budget 300, risk_ceil increase
- XRP_1h: skip 0.45/0.55, bar_budget 300, risk_ceil increase, pace_urgency_lo

---
