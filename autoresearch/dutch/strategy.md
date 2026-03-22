# Dutch Strategy
Updated: after iteration 107 (2026-03-23T20:35:00Z) — STRATEGIST analysis

## Summary

Seventh rotation complete on V7.3 (iters 96-107). KEEP rate this rotation: 6/12 = 50% — best rotation yet.
Overall V7.3 KEEP rate (iters 33-107): 29/75 = 38.7%.

Key findings from rotation 7:
1. **BTC_5m finally KEEP**: max_onesided_cost 5.0->2.0 (iter 104) first KEEP in 8 rotations.
   pair_cost 0.9480->0.9220 (2.74%), max_dd 33.2%->15.3%. Matches ETH_5m/SOL_5m pattern.
   BTC_5m no longer stuck — onesided=2.0 is the confirmed repair lever.
2. **ETH_5m onesided series advancing**: onesided 2.0->1.5 KEEP (iter 107) with avg_profit
   turning positive (+$0.01/bar), pair_cost 0.6390->0.6329. ETH_5m onesided series: 5->2->1.5 all KEEP.
3. **SOL_5m floor confirmed**: onesided 2.0->1.5 DISCARD (iter 97) — no pair_cost improvement
   (0.6760->0.6760, 0.0%). Pairs not forming in the 1.5-2.0 range on SOL_5m. Floor = 2.0.
4. **SOL_15m risk_ceil success**: risk_ceil 0.15->0.20 KEEP (iter 99) — 2.7% gain (+$0.42/bar).
   SOL_15m now risk_ceil=0.20 confirmed (combined with bar_budget=300). Capital scaling on profitable pair.
5. **XRP_15m pace_urgency_lo breakthrough**: pace_urgency_lo 0.35->0.30 KEEP (iter 102) — 18.0%
   pair_cost improvement (0.7780->0.6378). MASSIVE gain. pace_urgency_lo is the highest-value
   untested lever for selective pairs with low matched_ratio.
6. **XRP_1h pace_urgency_lo confirmed inactive on 1h**: 0.35->0.45 DISCARD (iter 103) — zero effect.
   1h bars too long for urgency timing differentiation. Remove pace_urgency_lo from XRP_1h queue.
7. **SOL_1h re-eval regression**: pair_cost spiked 25.6% (0.6547->0.8224) on just 2 new bars.
   risk_ceil test (iter 101) also DISCARD. SOL_1h best_knobs are valid but dataset variance is high.
   Dataset is thin (36 bars). Run fresh re-eval before any structural changes.
8. **BTC_1h dataset variance critical**: re-eval DISCARD (iter 105), pair_cost regressed to 0.909 from best 0.7988.
   conviction_market_start DISCARD (iter 106). Pair is operating at 36 bars — extremely thin.

Current best_knobs state (post-iter-107):
- ETH_5m: onesided=1.5, skip=0.45 (pair_cost=0.633, max_dd=13.8%, avg_profit=+$0.01/bar) — POSITIVE PROFIT
- XRP_15m: pace_urgency_lo=0.30, skip=0.45, onesided=2.0 (pair_cost=0.638, avg_profit=-$0.01/bar)
- ETH_15m: onesided=1.5 (pair_cost=0.560 best / volatile on new bars)
- SOL_1h: skip=0.45, bar_budget=300 (best KEEP pair_cost=0.655, dataset volatile on 36 bars)
- XRP_1h: skip=0.50 default (pair_cost=0.674, avg_profit=+$1.08/bar)
- SOL_5m: onesided=2.0, skip=0.45 (pair_cost=0.676, max_dd=18.1%)
- SOL_15m: skip=0.45, bar_budget=300, risk_ceil=0.20 (pair_cost=0.696, avg_profit=+$0.42/bar) — PROFITABLE
- ETH_1h: skip=0.45 (pair_cost=0.706, max_dd=17%)
- BTC_1h: skip=0.40, conviction=0.30 (best KEEP pair_cost=0.799, but current 36-bar shows 0.909 — variance)
- XRP_5m: baseline V7.3 (pair_cost=0.909, max_dd=68.7%) — WORST PAIR, skip/onesided both untested
- BTC_5m: onesided=2.0 (pair_cost=0.922, max_dd=15.3%) — first KEEP, next: onesided=1.5 series
- BTC_15m: baseline (pair_cost=0.933) — zero KEEPs, all skip=0.45 attempts collapse

NOTE on best_knobs discrepancies found: BTC_1h file shows conviction_buy_skip=0.55 but iters 52+64 confirmed 0.40 is the KEEP value. SOL_1h file shows conviction_buy_skip=0.55 but iter 58 confirmed 0.45. These files are stale — researcher must use results.tsv KEEP values, not stale best_knobs files.

---

## BTC_5m (pair_cost=0.922, KEEP rate 1/7=14%, max_dd=15.3%)
V7.3 + 1 KEEP: max_onesided_cost 5.0->2.0 (iter 104), pair_cost 0.9480->0.9220 (+2.74%).
First KEEP since V7.3 reset. DD resolved (33.2%->15.3%). avg_profit=+$0.19/bar positive.
All skip directions exhausted (skip=0.45 D iter 33, skip=0.55 D iter 50). cheap_threshold exhausted.
Next logical step: follow ETH_5m onesided series (5->2->1.5 all KEEP).

Priority queue:
1. max_onesided_cost 2.0->1.5 — ETH_5m confirmed 2.0->1.5 KEEP (iter 107). SOL_5m DISCARD
   at 1.5 (iter 97, 0.0% improvement). BTC_5m matched_ratio=0.1% is extremely thin —
   collapse risk at 1.5 is HIGH. Run test but monitor matched_ratio carefully.
   If matched_ratio collapses (<0.05%): floor=2.0 confirmed on BTC_5m.
2. pace_urgency_lo 0.35->0.30 — XRP_15m showed 18% gain with this move (iter 102).
   BTC_5m has 0.1% matched_ratio — earlier urgency timing may capture more pairs.
   Test if onesided=1.5 fails or if post-onesided series improvement is needed.
3. conviction_buy_skip 0.50->0.45 — PREVIOUSLY DISCARD (iter 33). But context changed:
   onesided=2.0 now active. Re-test with updated best_knobs — onesided cap may make skip
   change viable where it failed before. Low priority, test last.

Blacklists (BTC_5m): unmatched_ratio tightening, sell_loss_start tightening,
conviction_buy_skip 0.45 standalone (D iter 33 — retest only with onesided cap active),
conviction_buy_skip 0.55 (D iter 50), cheap_threshold 0.07 (D iter 17), cheap_threshold 0.12 (D iter 62),
max_onesided_cost 5->3 (D iter 89 — sub-threshold). SKIP SERIES + CHEAP_THRESHOLD EXHAUSTED.

---

## BTC_15m (pair_cost=0.933, KEEP rate 0/7=0%, max_dd=23%)
V7.3 best: avg_profit=+$0.50/bar, correct_side=63%, matched_ratio=12%.
Zero KEEPs across 7 experiments. Skip=0.45 definitively incompatible (3 confirmations).
Strong fundamentals (63% correct_side, +$0.50/bar) but pair_cost stuck.

Priority queue:
1. max_onesided_cost 5.0->2.0 (ALONE, no skip change) — ETH_5m/SOL_5m/BTC_5m all KEEP at 2.0.
   BTC_15m has higher matched_ratio (12%) vs 5m peers — less collapse risk.
   Most promising remaining lever. Skip=0.45 direction definitively exhausted.
2. pace_urgency_lo 0.35->0.30 — XRP_15m 18% gain pattern. BTC_15m has moderate matched_ratio.
   Test after onesided experiment resolves. Earlier entry timing to improve fill quality.
3. bar_budget 200->300 — only after structural cost improvement. BTC_15m has +$0.50/bar profit;
   capital scaling would be high-value IF pair_cost can first drop below 0.90.
   NOTE: prior DISCARD (iter 63) was on baseline knobs — re-test with onesided improvement.

Blacklists (BTC_15m): unmatched_ratio tightening, max_marginal_pair_cost below 1.01,
cheap_threshold to 0.07, bar_budget before cost fix (D iter 63),
conviction_buy_skip 0.45 in ANY combination (D iters 51, 78, 90 — definitively confirmed collapse).
SKIP=0.45 DIRECTION DEFINITIVELY EXHAUSTED.

---

## BTC_1h (pair_cost=0.799 best / 0.909 on current 36 bars, KEEP rate 2/8=25%, max_dd=9%)
V7.3 + 2 KEEPs: skip=0.45 (iter 52), skip=0.40 (iter 64).
Iters 105-106 (rotation 7): re-eval DISCARD (0.909 regression on 1 new bar) + conviction_market_start DISCARD.
Critical: best_knobs shows conviction_buy_skip=0.55 but correct value from iters 52+64 is 0.40.
Dataset thin (36 bars) — extreme variance on single new bars.

Priority queue:
1. Re-eval with correct knobs (skip=0.40) — confirm pair_cost vs current 36-bar snapshot.
   Researcher MUST verify best_knobs has conviction_buy_skip=0.40 before any new experiment.
   If re-eval shows pair_cost <0.80 (matching iter 64 result): proceed to #2.
   If still >0.90: structural regression, investigate dataset changes.
2. pace_urgency_lo 0.35->0.45 — delayed entry timing for already-selective pair (1.2% matched_ratio).
   Previous test (iter 6 D, pace_urgency_hi) was different param. pace_urgency_lo untested on BTC_1h.
3. max_onesided_cost 5.0->2.0 — ETH_5m/SOL_5m pattern. If pace_urgency_lo fails.
   Iter 91 (5->3) sub-threshold at 1.0%. Try 2.0 as final onesided test on BTC_1h.

Blacklists (BTC_1h): risk_ceil tightening, sell_loss_start tightening, pace_urgency_hi loosening,
bar_budget 400, conviction_buy_skip raising above 0.50, risk_ceil 0.15->0.20 (D iter 80),
max_onesided_cost 5->3 (D iter 91 — sub-threshold), conviction_market_start 0.30->0.25 (D iter 106).
Skip floor at 0.40.

---

## ETH_5m (pair_cost=0.633, KEEP rate 4/5=80%, max_dd=13.8%)
V7.3 + 4 KEEPs (iters 65, 66, 92, 107): re-eval + skip=0.45 + onesided=2.0 + onesided=1.5.
OUTSTANDING performance — highest KEEP rate among active pairs (80%).
iter 107: onesided 2.0->1.5 KEEP (0.96% gain) — avg_profit now POSITIVE (+$0.01/bar).
DD resolved: 13.8% (down from 47% baseline). All benchmarks met.
Onesided series: 5.0 -> 2.0 -> 1.5 all KEEP.

Priority queue:
1. max_onesided_cost 1.5->1.0 — continue series. ETH_15m collapsed at 1.0 (iter 94),
   but ETH_5m has 0.8% matched_ratio vs ETH_15m's 1.0% at collapse point. HIGH collapse risk.
   Monitor matched_ratio carefully — if drops below 0.3%: floor=1.5 confirmed.
   If KEEP: pair_cost may drop below 0.60 for first time.
2. conviction_buy_skip 0.45->0.40 — now safer with DD at 13.8% and positive avg_profit.
   correct_side=42.9% is borderline. Test with current onesided=1.5 context.
   If correct_side drops below 38%: abort and blacklist skip=0.40 on ETH_5m.
3. bar_budget 200->300 — positive avg_profit now makes capital scaling viable.
   Test after onesided series resolves (series still has room at 1.0).

Blacklists (ETH_5m): unmatched_ratio tightening, conviction_buy_skip raising above 0.50,
conviction_buy_skip 0.60 (D iter 37).

---

## ETH_15m (pair_cost=0.560 best / ~0.675 volatile, KEEP rate 4/9=44%, max_dd=27%)
V7.3 + 4 KEEPs: re-eval (iter 53), skip=0.45 (iter 54), onesided=2.0 (iter 68), onesided=1.5 (iter 82).
IMPORTANT: Re-eval regressions are structural — ETH_15m has 1% matched_ratio causing extreme bar-to-bar variance.
Onesided=1.0 collapsed (iter 94): floor confirmed at 1.5. Onesided series exhausted.

Priority queue:
1. bar_budget 200->300 — scale capital at confirmed onesided=1.5. High volatility means result
   uncertain. Accept KEEP if pair_cost stays below 0.72 (current moving average territory).
   ETH_15m is structurally unpredictable on <5 bar windows; require meaningful dataset for judgment.
2. pace_urgency_lo 0.35->0.30 — following XRP_15m's 18% gain pattern (iter 102).
   ETH_15m's 1% matched_ratio is limiting. Earlier urgency gate may capture more pairs.
   Test after bar_budget experiment if cost is stable.
3. conviction_buy_skip 0.45->0.40 — with DD at 27% (near threshold), test only if onesided
   series and bar_budget both stabilize pair_cost below 0.65.

Blacklists (ETH_15m): unmatched_ratio tightening, conviction_buy_skip raising to 0.55,
max_onesided_cost increasing above 1.5 (zero effect), max_onesided_cost 1.5->1.0 (D iter 94 — collapse).
ONESIDED SERIES EXHAUSTED at 1.5 floor.

---

## ETH_1h (pair_cost=0.706, KEEP rate 2/6=33%, max_dd=17%)
V7.3 + 2 KEEPs: re-eval (iter 39), skip=0.45 (iter 40).
Skip floor at 0.45 (skip=0.40 D iter 69). risk_ceil sub-threshold (D iter 83). onesided zero-effect (D iter 55).
Rotation 7: no experiments ran for ETH_1h. Still on rotation queue.

Priority queue:
1. bar_budget 200->250 — cautious capital scale. ETH_1h matched_ratio=7% (better than XRP_1h 3.4%).
   avg_profit=-$0.49/bar negative, so test intermediate step (250, not 300).
   If 250 helps avg_profit approach zero: consider 300.
2. pace_urgency_lo 0.35->0.30 — XRP_15m's 18% gain strongly suggests this lever is underexplored.
   ETH_1h at 7% matched_ratio is moderate — earlier urgency timing may capture better pairs.
   High-confidence test given XRP_15m result.
3. conviction_market_start 0.30->0.25 — lower entry bar for qualifying predictions.
   Low matched_ratio (7%) suggests over-filtering. Cautious reduction may improve volume.
   NOTE: BTC_1h (iter 106) showed DISCARD — lower market_start degraded quality.
   ETH_1h may differ with skip=0.45 active.

Blacklists (ETH_1h): max_onesided_cost increasing above $5 (D iter 55 — zero effect),
conviction_buy_skip 0.40 (D iter 69), risk_ceil 0.15->0.20 (D iter 83 — only 3.8%).
NOTE: skip floor confirmed at 0.45. conviction_market_start caution: DISCARD on BTC_1h.

---

## SOL_5m (pair_cost=0.676, KEEP rate 4/6=67%, max_dd=18.1%)
V7.3 + 4 KEEPs (iters 70, 71, 84, 96): re-eval + skip=0.45 + onesided=2.0 + re-eval.
iter 97: max_onesided_cost 2.0->1.5 DISCARD — zero improvement (0.6760->0.6760). Floor=2.0 confirmed.
Onesided series floor confirmed at 2.0. Pairs not forming in the 1.5-2.0 cost range on SOL_5m.
ALL BENCHMARKS MET: pair_cost=0.676 (<0.85), max_dd=18.1% (<30%), avg_profit=+$0.06/bar.

Priority queue:
1. pace_urgency_lo 0.35->0.30 — XRP_15m's 18% gain strongly motivates this.
   SOL_5m at 0.94% matched_ratio (very selective). Earlier urgency timing may capture more pairs.
   SOL pairs have shown different budget/capital behavior — pace may also differ.
2. conviction_buy_skip 0.45->0.40 — DD now 18.1% and positive avg_profit provide buffer.
   However matched_ratio=0.94% is critically low — collapse risk high (same level as XRP_15m
   which collapsed at skip=0.40, iter 60). Use caution; monitor matched_ratio carefully.
3. bar_budget 200->300 — positive avg_profit is enabling factor. SOL_15m and SOL_1h both
   showed KEEP at 300 (iters 73, 86). SOL pair budget scaling pattern.

Blacklists (SOL_5m): conviction_buy_skip raising to 0.55 (D iter 41),
max_onesided_cost 2.0->1.5 (D iter 97 — confirmed floor at 2.0).
ONESIDED SERIES EXHAUSTED at 2.0 floor on SOL_5m.

---

## SOL_15m (pair_cost=0.696, KEEP rate 5/7=71%, max_dd=17.3%)
V7.3 + 5 KEEPs: skip=0.45 (iter 56), re-eval (iter 72), bar_budget=300 (iter 73), re-eval (iter 98), risk_ceil=0.20 (iter 99).
Highest KEEP rate in the system (71%). All benchmark targets met.
risk_ceil 0.15->0.20 KEEP (iter 99): pair_cost improved 2.7% (0.7151->0.6956), profit +$0.42/bar.
Current best_knobs: skip=0.45, bar_budget=300, risk_ceil=0.20.

Priority queue:
1. max_onesided_cost 5.0->2.0 — pre-emptive DD cap. Current max_dd=17.3% is fine but
   applying proven pattern before it becomes a problem. SOL pairs have different onesided response
   (SOL_1h has onesided=5 still). SOL_15m matched_ratio=8.8% (from iter 99) — reasonable for 2.0.
2. bar_budget 300->400 — SOL pairs uniquely budget-scalable. avg_profit=+$0.42/bar excellent.
   If onesided cap test is neutral/positive, scaling budget compounds returns.
3. pace_urgency_lo 0.35->0.30 — XRP_15m pattern. SOL_15m has moderate matched_ratio — earlier
   urgency may improve fill quality without collapsing matching.

Blacklists (SOL_15m): min_unmatched_shares tightening, conviction_buy_skip raising above 0.50,
conviction_buy_skip 0.40 (D iter 85 — confirmed collapse), bar_budget BEFORE cost/risk fixes.
SKIP SERIES FULLY EXHAUSTED.

---

## SOL_1h (pair_cost=0.655 best KEEP / 0.822 on current 36 bars, KEEP rate 3/7=43%, max_dd=5.8%)
V7.3 + 3 KEEPs: re-eval (iter 43), skip=0.45 (iter 58), bar_budget=300 (iter 86).
Rotation 7: pair_cost regressed 25.6% on 2 new bars (iter 100 re-eval DISCARD).
risk_ceil 0.15->0.20 DISCARD (iter 101) — still above best at 0.8170.
Dataset thin (36 bars) — 2 new bars caused massive regression. High structural variance.
NOTE: best_knobs file has conviction_buy_skip=0.55 but correct KEEP value is 0.45 (iter 58 confirmed).

Priority queue:
1. Re-eval with CORRECT knobs (skip=0.45, bar_budget=300) — verify current state.
   The best_knobs file is stale (conviction_buy_skip=0.55 vs correct 0.45). Researcher MUST
   fix best_knobs and run re-eval before any structural experiment.
   If re-eval pair_cost <0.70: proceed to #2. If >0.80: dataset structural variance; run 2 more re-evals.
2. bar_budget 300->400 — SOL pair budget scaling pattern. Wait for re-eval stability first.
   avg_profit=+$0.69/bar when not in regression window. High-value experiment if cost stable.
3. pace_urgency_lo 0.35->0.30 — XRP_15m pattern. SOL_1h fill rate=89.2%; earlier urgency
   may squeeze further quality at lower matched_ratio.

Blacklists (SOL_1h): conviction_buy_skip 0.35 (collapsed iter 57), skip=0.40 (D iter 74),
risk_ceil 0.15->0.20 (D iters 100-101 — pair_cost regressed, risk_ceil tested in regression window).
NOTE: risk_ceil test may need revisiting if re-eval confirms cost stability.
SKIP SERIES FULLY EXHAUSTED on SOL_1h.

---

## XRP_5m (pair_cost=0.909, KEEP rate 1/2=50%, max_dd=68.7%)
V7.3 + 1 KEEP (re-eval only, iter 44). fill_ticks=15 DISCARD (iter 59).
WORST PAIR: max_dd=68.7% is highest in system. No rotation 7 experiment ran.
Next: skip=0.45 (highest priority) then onesided=2.0 for DD repair.

Priority queue:
1. conviction_buy_skip 0.50->0.45 — analogous to SOL_5m (iter 71, +8.4% KEEP).
   Never tested on XRP_5m. Run before onesided cap to understand skip direction first.
   XRP_5m matched_ratio=7.6% — above the 5% collapse threshold; skip=0.45 should be safe.
2. max_onesided_cost 5.0->2.0 — CRITICAL DD repair regardless of skip outcome.
   max_dd=68.7% is unsustainable. ETH_5m (iter 92) and SOL_5m (iter 84) both confirmed 2.0 halves DD.
   Run as the most important structural fix after skip test.
3. pace_urgency_lo 0.35->0.30 — XRP_15m's 18% gain. Apply after structural fixes established.

Blacklists (XRP_5m): fill_ticks 10->15 (structural limit D iter 59 — try 20 as final test),
conviction_buy_skip raising above 0.50.

---

## XRP_15m (pair_cost=0.638, KEEP rate 2/6=33%, max_dd=11%)
V7.3 + 2 KEEPs: skip=0.45 (iter 46, +18.6%), pace_urgency_lo=0.30 (iter 102, +18.0%).
LANDMARK RESULT: pace_urgency_lo 0.35->0.30 gave 18% improvement (iter 102) — confirms
urgency timing is a high-value lever for selective low-matched-ratio pairs.
Current best_knobs: skip=0.45, pace_urgency_lo=0.30, max_onesided_cost=2.0.
avg_profit=-$0.01/bar (near-zero, close to profitable).

Priority queue:
1. pace_urgency_lo 0.30->0.25 — follow the series. XRP_15m responded strongly to 0.35->0.30
   (18% gain). Try next step. Risk: matched_ratio already dropped to 0.3% — any further
   reduction may collapse pair formation entirely. Monitor carefully.
   If matched_ratio drops to 0.0%: floor=0.30 confirmed.
2. conviction_market_start 0.30->0.25 — lower prediction entry bar.
   Very low matched_ratio (0.3%) suggests over-filtering. May qualify more predictions.
   Test after pace series resolves.
3. bar_budget 200->250 — cautious capital scale on near-profitable pair.
   XRP_15m confirmed 200 is optimum over 300 (D iter 75); try small intermediate step.

Blacklists (XRP_15m): conviction_buy_skip 0.40 (D iter 60 — collapsed),
bar_budget 300 (D iter 75 — optimum at 200), risk_ceil 0.15->0.20 (D iter 87 — worsened).
SKIP EXHAUSTED. BUDGET OPTIMUM AT 200.

---

## XRP_1h (pair_cost=0.674, KEEP rate 1/6=17%, max_dd=6%)
V7.3 + 1 KEEP: re-eval (iter 47, +5.87%).
All major levers tested: skip exhausted, risk_ceil failed, bar_budget failed at 300.
pace_urgency_lo 0.35->0.45 DISCARD (iter 103) — zero effect. 1h bars too long for urgency timing.
avg_profit=+$1.08/bar is system-best avg_profit. Pair fundamentally profitable but cost sticky.

Priority queue:
1. conviction_market_start 0.30->0.25 — lower entry bar for qualifying predictions.
   Low matched_ratio (3.4%) suggests over-filtering. Most untested lever remaining.
   Note: BTC_1h (iter 106) showed conviction_market_start worsened pair_cost. Risk exists.
2. pace_urgency_hi 0.85->0.75 — alternative urgency gate tuning (different from lo).
   Lower hi threshold may help timing cadence for 1h bars without impacting skip behavior.
3. max_onesided_cost 5.0->2.0 — DD is only 6%, very controlled. Onesided cap may be neutral.
   However BTC_1h (iter 91) showed only 1% improvement at 3.0 — XRP_1h may be similar.
   Test as final structural lever.

Blacklists (XRP_1h): conviction_buy_skip 0.45 (D iter 48), conviction_buy_skip 0.55 (D iter 61),
bar_budget 300 (D iter 76 — optimum at 200), risk_ceil 0.15->0.20 (D iter 88 — worsened),
pace_urgency_lo 0.35->0.45 (D iter 103 — zero effect on 1h TF).
BOTH SKIP DIRECTIONS EXHAUSTED. BUDGET OPTIMUM AT 200. PACE_URGENCY_LO INEFFECTIVE ON 1h.

---

## Cross-Pair Observations

**Rotation 7 breakthrough — pace_urgency_lo is a high-value lever:**
- XRP_15m: 0.35->0.30 gave 18% pair_cost gain (iter 102) — MASSIVE
- XRP_1h: 0.35->0.45 gave zero effect — urgency timing only works on sub-1h timeframes
- Hypothesis: pace_urgency_lo 0.30 should be tested on ALL 5m and 15m pairs that haven't tried it.
  Priority order: BTC_15m, ETH_15m, ETH_5m (post-onesided), SOL_5m, SOL_15m.

**Skip floor mapping (confirmed through rotation 7):**
- skip=0.40 confirmed floor: BTC_1h (KEEP iter 64)
- skip=0.45 confirmed floor: ETH_1h (D iter 69), SOL_1h (D iter 74), XRP_15m (D iter 60),
  SOL_15m (D iter 85), SOL_5m (KEEP iter 71 — 0.45 works)
- skip=0.50 confirmed floor: XRP_1h (D iter 48+61), BTC_5m (D iter 33+50)
- skip=0.45 definitively fails: BTC_15m (D iters 51, 78, 90 — 3 tests confirm collapse)
- skip series active: ETH_5m (0.40 pending with onesided=1.5 context), XRP_5m (0.45 untested)

**max_onesided_cost confirmed dominant lever for 5m/15m pairs:**
- SOL_5m: onesided=2.0 floor (iter 97 DISCARD at 1.5)
- ETH_5m: onesided=1.5 KEEP (iter 107) — series continuing; try 1.0 next
- ETH_15m: onesided=1.5 floor (iter 94 DISCARD at 1.0)
- BTC_5m: onesided=2.0 KEEP (iter 104) — series just started; try 1.5 next
- BTC_15m: onesided untested — high confidence for improvement
- XRP_5m: onesided=5.0 (DD=68.7% critical) — immediate priority

**risk_ceil increase pattern updated:**
- CONFIRMED FAIL: BTC_1h (D iter 80), ETH_1h (D iter 83), XRP_15m (D iter 87), XRP_1h (D iter 88), SOL_1h (D iter 101 — regression window)
- CONFIRMED KEEP: SOL_15m (K iter 99 +2.7%) — positive avg_profit pairs differ
- Pattern: risk_ceil increase only works on pairs with ALREADY POSITIVE avg_profit + low DD
- SOL_1h should be retested after re-eval stabilizes (was in regression window)

**bar_budget scale-up pattern fully mapped:**
- XRP pairs: bar_budget 200 CONFIRMED OPTIMUM. 300 DISCARDs for XRP_15m (iter 75) and XRP_1h (iter 76).
- SOL pairs: budget scaling confirmed (SOL_15m 300 KEEP iter 73, SOL_1h 300 KEEP iter 86).
  SOL_15m risk_ceil=0.20 further confirms capital scaling viability.
- BTC/ETH pairs: budget scaling only after pair_cost < 0.85.

---

## trader_a Benchmark Comparison (post-iter-107 best_knobs)
| Pair | PairCost | Target | Gap | AvgProfit | MaxDD% | Trend |
|------|----------|--------|-----|-----------|--------|-------|
| BTC_5m | 0.922 | < 0.85 | +0.072 | +$0.19 | 15.3% | improving — onesided=1.5 next |
| BTC_15m | 0.933 | < 0.85 | +0.083 | +$0.50 | 23% | stuck — onesided=2.0 next |
| BTC_1h | 0.799 | < 0.85 | -0.051 | -$0.33 | 9% | beats benchmark; variance on 36 bars |
| ETH_5m | 0.633 | < 0.85 | -0.217 | +$0.01 | 13.8% | PROFITABLE; onesided=1.0 next |
| ETH_15m | 0.560 | < 0.85 | -0.290 | -$0.21 | 27% | BEST cost — volatile; bar_budget next |
| ETH_1h | 0.706 | < 0.85 | -0.144 | -$0.49 | 17% | beats benchmark; pace_urgency_lo next |
| SOL_5m | 0.676 | < 0.85 | -0.174 | +$0.06 | 18.1% | PROFITABLE; pace_urgency_lo next |
| SOL_15m | 0.696 | < 0.85 | -0.154 | +$0.42 | 17.3% | PROFITABLE; onesided=2.0 next |
| SOL_1h | 0.655 | < 0.85 | -0.195 | +$0.69 | 5.8% | PROFITABLE; re-eval needed (stale knobs) |
| XRP_5m | 0.909 | < 0.85 | +0.059 | -$0.32 | 68.7% | WORST pair, DD critical; skip=0.45 + onesided=2.0 urgent |
| XRP_15m | 0.638 | < 0.85 | -0.212 | -$0.01 | 11% | near-profitable; pace_urgency_lo=0.25 next |
| XRP_1h | 0.674 | < 0.85 | -0.134 | +$1.08 | 6% | BEST avg_profit; conviction_market_start next |

**5 pairs PROFITABLE** (ETH_5m, SOL_5m, SOL_15m, SOL_1h, XRP_1h) — up from 4 in rotation 6.
**10 pairs beating trader_a pair_cost benchmark** — BTC_5m (0.922) still above but improving.
BTC_15m remains the most stubborn pair (0/7 KEEPs, skip=0.45 incompatible).

---

## Blacklist (per-pair)

- BTC_5m: unmatched_ratio tightening, sell_loss_start tightening, conviction_buy_skip 0.45 standalone (D iter 33),
  conviction_buy_skip 0.55 (D iter 50), cheap_threshold 0.07 (D iter 17), cheap_threshold 0.12 (D iter 62),
  max_onesided_cost 5->3 (D iter 89 — sub-threshold). SKIP + CHEAP_THRESHOLD EXHAUSTED.
- BTC_15m: unmatched_ratio tightening, max_marginal_pair_cost below 1.01, cheap_threshold to 0.07,
  bar_budget 300 before cost fix (D iter 63), conviction_buy_skip 0.45 in ANY combination
  (D iters 51, 78, 90 — definitively confirmed collapse on BTC_15m).
- BTC_1h: risk_ceil tightening, sell_loss_start tightening, pace_urgency_hi loosening, bar_budget 400,
  conviction_buy_skip raising above 0.50, risk_ceil 0.15->0.20 (D iter 80),
  max_onesided_cost 5->3 (D iter 91 — sub-threshold), conviction_market_start 0.30->0.25 (D iter 106).
- ETH_5m: unmatched_ratio tightening, conviction_buy_skip raising above 0.50, conviction_buy_skip 0.60 (D iter 37).
- ETH_15m: unmatched_ratio tightening, conviction_buy_skip raising to 0.55,
  max_onesided_cost increasing above 1.5 (zero effect), max_onesided_cost 1.5->1.0 (D iter 94 — collapse).
  ONESIDED SERIES EXHAUSTED at 1.5.
- ETH_1h: max_onesided_cost increasing (D iter 55 — zero effect above $5), conviction_buy_skip 0.40 (D iter 69),
  risk_ceil 0.15->0.20 (D iter 83 — only 3.8%). SKIP EXHAUSTED at 0.45.
- SOL_5m: conviction_buy_skip raising to 0.55 (D iter 41), max_onesided_cost 2.0->1.5 (D iter 97 — floor=2.0).
  ONESIDED SERIES EXHAUSTED at 2.0. Skip floor at 0.45.
- SOL_15m: min_unmatched_shares tightening, conviction_buy_skip raising above 0.50,
  conviction_buy_skip 0.40 (D iter 85 — confirmed collapse). SKIP SERIES FULLY EXHAUSTED.
- SOL_1h: conviction_buy_skip 0.35 (collapsed iter 57), conviction_buy_skip 0.45->0.40 (D iter 74),
  risk_ceil 0.15->0.20 (D iter 101 — tested in regression window; may revisit post re-eval).
  SKIP SERIES FULLY EXHAUSTED on SOL_1h.
- XRP_5m: fill_ticks 10->15 (structural limit D iter 59), conviction_buy_skip raising above 0.50.
- XRP_15m: conviction_buy_skip 0.40 (D iter 60 — collapsed), bar_budget 300 (D iter 75 — optimum at 200),
  risk_ceil 0.15->0.20 (D iter 87 — worsened). SKIP EXHAUSTED. BUDGET OPTIMUM AT 200.
- XRP_1h: conviction_buy_skip 0.45 (D iter 48), conviction_buy_skip 0.55 (D iter 61),
  bar_budget 300 (D iter 76 — optimum at 200), risk_ceil 0.15->0.20 (D iter 88 — worsened),
  pace_urgency_lo 0.35->0.45 (D iter 103 — zero effect on 1h TF).
  BOTH SKIP DIRECTIONS EXHAUSTED. BUDGET OPTIMUM AT 200. PACE_URGENCY_LO INEFFECTIVE ON 1h.

## Global Blacklist
- unmatched_ratio tightening: 3/3 DISCARDs (BTC_5m, ETH_5m, ETH_15m)
- sell_loss_start tightening: 2/2 DISCARDs (BTC_5m, BTC_1h)
- pace_urgency_hi loosening: 1/1 DISCARDs (BTC_1h)
- risk_ceil increase on negative-profit pairs: 4/4 DISCARDs (BTC_1h, ETH_1h, XRP_15m, XRP_1h) — only viable on PROVEN POSITIVE avg_profit pairs
- conviction_buy_skip 0.45 on BTC_15m: 3/3 DISCARDs — DEFINITIVELY INCOMPATIBLE
- pace_urgency_lo changes on 1h TF: D iter 103 — urgency timing only effective on 5m/15m bars
