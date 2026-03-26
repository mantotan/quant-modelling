# Dutch Strategy
Updated: after iteration 12 (2026-03-27T04:00:00Z) — STRATEGIST rotation 1 post-RESET analysis

## Summary

Post-RESET rotation 1 complete (iters 1-12). All 12 iterations are baselines with magnitude_gate=0.08.
**KEEP rate this rotation: 0/12 = 0%** (all are BASELINE, not experiments — expected).

**Critical finding from rotation 1:**
- magnitude_gate=0.08 collapses pair formation to 0% matched_ratio for 11 of 12 pairs
- XRP_1h uniquely survived gate=0.08: matched_ratio=3.6%, pair_cost=0.855, correct_side=82.6%
- All current knobs files already set to magnitude_gate=0.04 (set from prior rotation 9 state)
- **Rotation 2 goal: establish magnitude_gate=0.04 baselines for ALL 12 pairs** before optimization

**Stale knobs from pre-RESET (must fix FIRST, before any experiment on affected pair):**
- SOL_1h: knobs_SOL_1h.json shows bar_budget=400 but confirmed KEEP is 300 (iter 86 pre-RESET)
  Researcher MUST set bar_budget=300 in knobs_SOL_1h.json before any SOL_1h experiment
- XRP_5m: FREEZE maintained from pre-RESET auditor directive (structural dead-end)

**Prior rotation 9 knowledge retained (iters 1-119 pre-RESET):**
The prior strategy's structural conclusions carry forward completely. Skip floors, onesided floors,
pace_urgency findings, and blacklists are all inherited. The RESET only affected the running
experiment state — the analytical conclusions remain valid.

---

## Phase priorities for rotation 2 (iters 13-24)

**PHASE 1 (iters 13-24): magnitude_gate=0.04 baselines**
Run one BASELINE per pair (magnitude_gate=0.04, all other params per current knobs files).
Do NOT change any other parameter during baseline runs. Record all 12 baselines, then
strategist will analyze and set experiment queue for rotation 3.

Pair order for rotation 2: BTC_5m, BTC_15m, BTC_1h, ETH_5m, ETH_15m, ETH_1h,
SOL_5m, SOL_15m, SOL_1h, XRP_5m (skip — FREEZE), XRP_15m, XRP_1h

For SOL_1h: fix bar_budget=300 in knobs file BEFORE running baseline, then run baseline.
For XRP_5m: skip (FREEZE maintained from auditor directive, structural dead-end confirmed).

---

## BTC_5m (pair_cost=N/A at gate=0.04, KEEP rate 0/1=0% post-RESET)

Gate=0.08 BASELINE: matched_ratio=0%, pair_cost=0.000 (no pairs).
Current knobs: magnitude_gate=0.04, skip=0.50, max_onesided_cost=2.0, pace_urgency_lo=0.35.
Prior best (pre-RESET): pair_cost=0.922, avg_profit=+$0.19/bar, correct_side=65.4%.

Priority queue (after gate=0.04 baseline):
1. magnitude_gate=0.04 BASELINE — establish new baseline with the pre-RESET best knobs.
   This is the first and only task for BTC_5m in rotation 2.
   Accept as BASELINE (not a KEEP/DISCARD experiment).
2. pace_urgency_lo 0.35->0.30 — primary lever from prior rotation 9 (untested on BTC_5m).
   XRP_15m showed 18% gain. BTC_5m matched_ratio=0.1% means collapse risk; test cautiously.
   Accept KEEP if pair_cost improves >5% vs gate=0.04 baseline.
3. max_onesided_cost floor confirmed at 2.0 — do NOT test 1.5 (COLLAPSE confirmed pre-RESET iter 117).

Blacklists (BTC_5m): conviction_buy_skip 0.45 (D iter 33), conviction_buy_skip 0.55 (D iter 50),
cheap_threshold 0.07, cheap_threshold 0.12, max_onesided_cost 2.0->1.5 (COLLAPSE iter 117),
max_onesided_cost 5->3 (D iter 89), conviction_market_start (GLOBALLY BLACKLISTED).
ONESIDED SERIES EXHAUSTED at floor=2.0. SKIP SERIES EXHAUSTED.

---

## BTC_15m (pair_cost=N/A at gate=0.04, KEEP rate 0/1=0% post-RESET)

Gate=0.08 BASELINE: matched_ratio=0%, pair_cost=0.000 (no pairs).
Current knobs: magnitude_gate=0.04, skip=0.50, max_onesided_cost=5.0, pace_urgency_lo=0.35.
Prior best (pre-RESET): pair_cost=0.933, avg_profit=+$0.50/bar, correct_side=63%.

Priority queue (after gate=0.04 baseline):
1. magnitude_gate=0.04 BASELINE — establish new baseline. Only task for rotation 2.
2. max_onesided_cost 5.0->2.0 — highest remaining lever (untested pre-RESET). BTC_15m has
   12% matched_ratio which is the HIGHEST in the system — lowest collapse risk of any pair.
   ETH_5m/SOL_5m/BTC_5m all KEEP at onesided=2.0. High confidence this will KEEP.
   Accept KEEP if pair_cost improves >2% vs gate=0.04 baseline.
3. pace_urgency_lo 0.35->0.30 — XRP_15m 18% gain pattern. BTC_15m moderate matched_ratio (12%)
   means low collapse risk. Test after onesided resolves.

Blacklists (BTC_15m): conviction_buy_skip 0.45 in ANY combination (3 tests confirm collapse),
bar_budget 400, conviction_market_start (GLOBALLY BLACKLISTED).
SKIP=0.45 DIRECTION DEFINITIVELY EXHAUSTED.

---

## BTC_1h (pair_cost=N/A at gate=0.04, KEEP rate 0/1=0% post-RESET)

Gate=0.08 BASELINE: matched_ratio=0%, pair_cost=0.000 (no pairs).
Current knobs: magnitude_gate=0.04, skip=0.40 (per best pre-RESET), onesided=5.0.
Prior best (pre-RESET): pair_cost=0.799 (33 bars), regression to 0.904 on 37 bars.

Note: Dataset is thin (33-37 bars). Pre-RESET showed regression deepening — each new bar
adding negative signal. The RESET may help by resetting the dataset window.
BTC_1h is one of the most important re-evaluations: if magnitude_gate=0.04 restores
pair_cost closer to 0.799, it signals dataset was the problem, not the parameters.

Priority queue (after gate=0.04 baseline):
1. magnitude_gate=0.04 BASELINE — essential to establish new cost floor on the fresh dataset.
2. max_onesided_cost 5.0->2.0 — if baseline stabilizes near 0.799, test this lever next.
   iter 91 (5->3) showed only 1% gain; 2.0 is the final onesided test.
3. pace_urgency_lo 0.35->0.45 — was set in knobs pre-RESET but may not have been tested.
   Verify in post-RESET baselines whether this was documented. If not, run the test.

Blacklists (BTC_1h): risk_ceil 0.10, sell_loss_start tightening, pace_urgency_hi loosening,
bar_budget 400, conviction_buy_skip 0.50 (D iter 64), max_onesided_cost 5->3 (D iter 91),
conviction_market_start (GLOBALLY BLACKLISTED).

---

## ETH_5m (pair_cost=N/A at gate=0.04, KEEP rate 0/1=0% post-RESET)

Gate=0.08 BASELINE: matched_ratio=0%, pair_cost=0.000; correct_side=51.6%, avg_profit=-$47.84 total.
Current knobs: magnitude_gate=0.04, skip=0.45, max_onesided_cost=1.5, pace_urgency_lo=0.35.
Prior best (pre-RESET): pair_cost=0.633, avg_profit=+$0.01/bar, max_dd=13.8% — ALL BENCHMARKS MET.
Note: knobs file correct (skip=0.45, onesided=1.5 per pre-RESET KEEPs iters 65+66+92+107).

Priority queue (after gate=0.04 baseline):
1. magnitude_gate=0.04 BASELINE — re-establish the 0.633 baseline performance.
2. pace_urgency_lo 0.35->0.30 — after baseline confirms performance. Prior rotation 9 directive.
   XRP_15m showed 18% gain. ETH_5m at 0.8% matched_ratio is selective; earlier urgency gate
   may slightly expand qualifying pool. High-value test.
3. conviction_buy_skip 0.45->0.40 — DD=13.8% provides buffer. Test after pace_urgency_lo resolves.
   Monitor correct_side; if below 40%, abort and blacklist skip=0.40.

Blacklists (ETH_5m): conviction_buy_skip 0.60, max_onesided_cost 1.5->1.0 (COLLAPSE iter 119),
conviction_market_start (GLOBALLY BLACKLISTED).
ONESIDED SERIES FULLY EXHAUSTED at floor=1.5.

---

## ETH_15m (pair_cost=N/A at gate=0.04, KEEP rate 0/1=0% post-RESET)

Gate=0.08 BASELINE: matched_ratio=0%, pair_cost=0.000; correct_side=73.2% — strong signal quality.
Current knobs: magnitude_gate=0.04, skip=0.45, max_onesided_cost=1.5, pace_urgency_lo=0.30.
Prior best (pre-RESET): pair_cost=0.560 best / volatile on 123-bar dataset.
Note: knobs file shows skip=0.45 (CORRECT — pre-RESET strategist noted this was fixed).
Pre-RESET stale file issue (skip=0.55) appears to have been corrected in current knobs file.
correct_side=73.2% in gate=0.08 baseline is the HIGHEST 15m signal quality — strong foundation.

Priority queue (after gate=0.04 baseline):
1. magnitude_gate=0.04 BASELINE — re-establish the volatile 0.560 baseline.
   correct_side=73.2% means this pair has strong directional signal at gate=0.08;
   at gate=0.04 it should form many more pairs with good quality.
2. pace_urgency_lo 0.30->0.25 — knobs already at 0.30; if gate=0.04 baseline shows
   0.30 performing well, continue the pace series. Check if 0.25 was already running.
3. bar_budget 200->300 — positive avg_profit at best_knobs makes capital scaling viable.
   Test after pace series resolves.

Blacklists (ETH_15m): conviction_buy_skip raising to 0.55, max_onesided_cost above 1.5,
max_onesided_cost 1.5->1.0 (D iter 94 — collapse), conviction_market_start (GLOBALLY BLACKLISTED).
ONESIDED SERIES EXHAUSTED at 1.5 floor.

---

## ETH_1h (pair_cost=N/A at gate=0.04, KEEP rate 0/1=0% post-RESET)

Gate=0.08 BASELINE: matched_ratio=0%, pair_cost=0.000; correct_side=70.4% strong signal.
Current knobs: magnitude_gate=0.04, skip=0.45, onesided=5.0, pace_urgency_lo=0.35.
Prior best (pre-RESET): pair_cost=0.706, avg_profit=-$0.49/bar (negative — below target).
Note: bar_budget confirmed optimum at 200 (tested 250 and 300 — all fail pre-RESET).

Priority queue (after gate=0.04 baseline):
1. magnitude_gate=0.04 BASELINE — re-establish baseline cost on fresh dataset.
2. pace_urgency_lo 0.35->0.30 — XRP_15m's 18% gain strongly suggests high value.
   ETH_1h at 7% matched_ratio is moderate — earlier urgency timing may capture better pairs.
   Primary lever after budget exhaustion confirmed.
3. pace_urgency_lo 0.30->0.25 — follow series if #2 KEEPs.

Blacklists (ETH_1h): max_onesided_cost increasing above 5 (D iter 55), conviction_buy_skip 0.40,
risk_ceil 0.15->0.20, bar_budget 250, bar_budget 300, conviction_market_start (GLOBALLY BLACKLISTED).
BUDGET OPTIMUM AT 200. SKIP FLOOR AT 0.45.

---

## SOL_5m (pair_cost=N/A at gate=0.04, KEEP rate 0/1=0% post-RESET)

Gate=0.08 BASELINE: matched_ratio=0%, pair_cost=0.000; correct_side=59.8%, total_profit=$63.12.
Current knobs: magnitude_gate=0.04, skip=0.45, max_onesided_cost=2.0, pace_urgency_lo=0.30.
Prior best (pre-RESET): pair_cost=0.676, avg_profit=+$0.06/bar — PROFITABLE (all benchmarks met).
Note: Pre-RESET iter 109 showed SOL_5m can collapse (matched_ratio 0%->0% on 416 bars).
This pair is structurally fragile. The RESET provides a fresh opportunity.

Priority queue (after gate=0.04 baseline):
1. magnitude_gate=0.04 BASELINE — CRITICAL. Prior rotation 9 showed instability.
   Must confirm matched_ratio is non-zero at gate=0.04 with current knobs.
   If matched_ratio returns to ~0.94%: proceed with experiments.
   If matched_ratio remains 0%: investigate engine/dataset issue; hold all SOL_5m experiments.
2. pace_urgency_lo verification — knobs already at 0.30. If gate=0.04 baseline shows
   non-zero pairs: document pace_urgency_lo=0.30 as confirmed or test 0.35->0.30 formally.
3. conviction_buy_skip 0.45->0.40 — only if baseline is stable. Collapse risk is high.

Blacklists (SOL_5m): conviction_buy_skip 0.55 (D iter 41), max_onesided_cost 2.0->1.5 (COLLAPSE iter 97).
ONESIDED SERIES EXHAUSTED at floor=2.0.

---

## SOL_15m (pair_cost=N/A at gate=0.04, KEEP rate 0/1=0% post-RESET)

Gate=0.08 BASELINE: matched_ratio=0.3%, pair_cost=0.567 (anomalously low — few pairs).
Note: SOL_15m is UNIQUE — it formed a tiny number of pairs at gate=0.08 (like XRP_1h).
correct_side=47.7% is WEAKEST in the system (below 50%). This is concerning.
Current knobs: magnitude_gate=0.04, skip=0.45, bar_budget=200 (NOT 300 — investigate).
Wait: prior rotation confirmed bar_budget=300 KEEP (iter 73). If knobs shows 200, it's stale.
Check knobs_SOL_15m.json before proceeding.
Prior best (pre-RESET): pair_cost=0.696, avg_profit=+$0.42/bar — PROFITABLE (all benchmarks met).

Priority queue (after gate=0.04 baseline):
1. magnitude_gate=0.04 BASELINE — re-establish the 0.696 baseline.
   correct_side=47.7% at gate=0.08 is alarming (below 50%); must confirm gate=0.04 restores quality.
2. pace_urgency_lo 0.35->0.30 — primary lever after onesided + budget exhaustion.
   SOL_15m 8.8% matched_ratio means moderate collapse risk; earlier urgency may improve fill quality.
3. risk_ceil 0.20->0.25 — only if baseline shows stable positive avg_profit.
   pre-RESET iter 99 KEPT risk_ceil=0.20. Further scaling possible.

Blacklists (SOL_15m): conviction_buy_skip 0.40 (D iter 85 — collapse), conviction_buy_skip above 0.50,
bar_budget before cost fixes, bar_budget 400 (D iter 112 — optimum at 300),
max_onesided_cost 5.0->2.0 (COLLAPSE — BLACKLISTED entirely for SOL_15m),
conviction_market_start (GLOBALLY BLACKLISTED).
ONESIDED BLACKLISTED. SKIP SERIES EXHAUSTED. BUDGET OPTIMUM AT 300.

---

## SOL_1h (pair_cost=N/A at gate=0.04, KEEP rate 0/1=0% post-RESET)

Gate=0.08 BASELINE: matched_ratio=0%, pair_cost=0.000; correct_side=68.4%, avg_profit=-$0.06/bar.
CRITICAL STALE KNOBS: knobs_SOL_1h.json shows bar_budget=400 but confirmed KEEP is 300 (iter 86).
Researcher MUST set bar_budget=300 in knobs_SOL_1h.json BEFORE running any SOL_1h experiment.
Current knobs (after fix): magnitude_gate=0.04, skip=0.45, bar_budget=300, pace_urgency_lo=0.35.
Prior best (pre-RESET): pair_cost=0.655, avg_profit=+$1.49/bar — PROFITABLE, strong fundamentals.

Priority queue (after gate=0.04 baseline):
1. FIX STALE KNOBS FIRST: set bar_budget=300 in knobs_SOL_1h.json.
2. magnitude_gate=0.04 BASELINE — re-establish the 0.655 baseline with corrected knobs.
3. bar_budget 300->400 — avg_profit=+$1.49/bar is excellent; capital scaling is high-value.
   Run after baseline confirms stability.
4. pace_urgency_lo 0.35->0.30 — SOL_1h 1.9% matched_ratio; earlier urgency may improve quality.

Blacklists (SOL_1h): conviction_buy_skip 0.35 (COLLAPSE iter 57), skip=0.40 (D iter 74),
risk_ceil 0.15->0.20 (D iters 100-101), conviction_market_start (GLOBALLY BLACKLISTED).
SKIP SERIES FULLY EXHAUSTED.

---

## XRP_5m (pair_cost=0.000 at gate=0.08, KEEP rate 0/1=0% post-RESET)

FROZEN — auditor directive from pre-RESET maintained. Structural dead-end:
fill_rate=54% (structural microstructure limit), max_dd=69% (critical, far above 30% threshold).
Even at gate=0.08 baseline: zero pairs formed, lowest fill_rate in system at 15.6%.
Gate=0.04 would form pairs but the underlying structural issues remain:
correct_side=57.8% is marginal, fill_rate is structurally limited.

Priority queue: FREEZE MAINTAINED. Do NOT run experiments.
Skip XRP_5m in rotation 2. Auditor must formally review before any experiments resume.

Blacklists (XRP_5m): ALL levers blacklisted pending auditor freeze lift.
fill_ticks 10->15 (D iter 59), conviction_market_start (GLOBALLY BLACKLISTED).

---

## XRP_15m (pair_cost=N/A at gate=0.04, KEEP rate 0/1=0% post-RESET)

Gate=0.08 BASELINE: matched_ratio=0%, pair_cost=0.000; correct_side=53.7%, fill_rate=39.7%.
Current knobs: magnitude_gate=0.04, skip=0.45, max_onesided_cost=2.0, pace_urgency_lo=0.30.
Prior best (pre-RESET): pair_cost=0.638, avg_profit=-$0.01/bar (near-profitable).
Note: XRP_15m LANDMARK — pace_urgency_lo 0.35->0.30 gave 18% improvement (pre-RESET iter 102).
Note: knobs shows pace_urgency_lo=0.30 (from KEEP iter 102). This is correct.
Pre-RESET strategist noted pace_urgency_lo=0.25 may have been pre-emptively set — check iter history.
Current knobs show 0.30 which is the confirmed KEEP value.

Priority queue (after gate=0.04 baseline):
1. magnitude_gate=0.04 BASELINE — re-establish the 0.638 baseline.
2. pace_urgency_lo 0.30->0.25 — XRP_15m responded massively to 0.35->0.30 (18% gain).
   Series continuation: test 0.25 next. Risk: matched_ratio=0.3% may collapse at 0.25.
   If matched_ratio drops to 0%: floor=0.30 confirmed. Accept KEEP only if pair_cost improves >5%.
3. bar_budget 200->250 — cautious capital scale on near-profitable pair.
   Only test after pace series resolves.

Blacklists (XRP_15m): conviction_buy_skip 0.40 (D iter 60 — collapse), bar_budget 300 (D iter 75),
risk_ceil 0.15->0.20 (D iter 87), conviction_market_start (GLOBALLY BLACKLISTED).
SKIP EXHAUSTED. BUDGET OPTIMUM AT 200.

---

## XRP_1h (pair_cost=0.855 at gate=0.08, KEEP rate 0/1=0% post-RESET)

Gate=0.08 BASELINE: matched_ratio=3.6%, pair_cost=0.855, correct_side=82.6%, DD=3.1%.
UNIQUE: only pair with non-zero pair formation at gate=0.08. 1h bars have sufficient
price movement to clear the 0.08 gate threshold.
correct_side=82.6% is the HIGHEST in the system — strongest directional signal.
pair_cost=0.855 is already close to 0.85 target even at gate=0.08.
Current knobs: magnitude_gate=0.04, skip=0.50, max_onesided_cost=5.0, flip_kill_after=4.
Note: knobs shows max_onesided_cost=5.0 — pre-RESET strategist flagged this as needing a test.
No results.tsv KEEP confirms onesided=2.0. Run onesided test after gate=0.04 baseline.
Prior best (pre-RESET): pair_cost=0.674, avg_profit=+$1.08/bar — system-best avg_profit.

Priority queue (after gate=0.04 baseline):
1. magnitude_gate=0.04 BASELINE — expected to form MORE pairs and potentially lower pair_cost
   below 0.855 seen at gate=0.08. This is the most anticipated baseline in the rotation.
   Prediction: pair_cost should approach 0.674 (pre-RESET best) at gate=0.04.
2. max_onesided_cost 5.0->2.0 — must be tested and documented. Pre-RESET strategist flagged
   this as unconfirmed in results.tsv. DD=6% means cap effect may be minimal.
   Accept KEEP if pair_cost improves >2% vs gate=0.04 baseline.
3. pace_urgency_hi 0.85->0.75 — pace_urgency_lo confirmed ineffective on 1h TF. pace_urgency_hi
   is the alternative urgency gate tuning. Untested lever with potential upside.

Blacklists (XRP_1h): conviction_buy_skip 0.45 (D iter 48), conviction_buy_skip 0.55 (D iter 61),
bar_budget 300 (D iter 76), risk_ceil 0.15->0.20 (D iter 88),
pace_urgency_lo 0.35->0.45 (D iter 103 — zero effect on 1h TF),
conviction_market_start (GLOBALLY BLACKLISTED).
BOTH SKIP DIRECTIONS EXHAUSTED. BUDGET OPTIMUM AT 200. PACE_URGENCY_LO INEFFECTIVE ON 1h.

---

## Cross-Pair Observations

**Post-RESET critical finding — magnitude_gate=0.08 is universally too aggressive:**
- 11 of 12 pairs: 0% matched_ratio at gate=0.08 (complete pair formation collapse)
- 1 exception: XRP_1h at 3.6% matched_ratio (1h bars have larger moves, clearing 8% gate)
- SOL_15m: 0.3% matched_ratio at gate=0.08 (near-collapse, pair_cost=0.567 artificially low)
- Gate=0.04 is already set in all knobs files — rotation 2 MUST run 0.04 baselines for all pairs

**Signal quality at gate=0.08 (even when pairs collapse, correct_side reflects model quality):**
- Highest: XRP_1h=82.6%, ETH_15m=73.2%, BTC_1h=66.7%, SOL_1h=68.4%, ETH_1h=70.4%
- Moderate: BTC_15m=60.8%, SOL_1h=68.4%, BTC_5m=65.4%, XRP_5m=57.8%
- Weakest: SOL_15m=47.7% (below 50%), ETH_5m=51.6%, XRP_15m=53.7%, SOL_5m=59.8%
- SOL_15m at 47.7% is alarming — correct_side below 50% means model is directionally wrong
  more often than right at gate=0.08. Gate=0.04 may restore this by sampling more pairs.

**Pre-RESET structural knowledge fully retained:**
- pace_urgency_lo series: primary remaining lever across all 5m/15m pairs (not 1h TF)
  XRP_15m landmark: 18% improvement at 0.30; series untested on BTC_5m, BTC_15m, ETH_1h, SOL_15m, SOL_1h
- conviction_market_start: GLOBALLY BLACKLISTED — do not test on any pair
- Onesided floors: ETH_5m=1.5, ETH_15m=1.5, SOL_5m=2.0, BTC_5m=2.0; SOL_15m onesided BLACKLISTED
- Skip floors: BTC_1h=0.40, BTC_15m skip=0.45 definitively fails; ETH/SOL/XRP pairs floor=0.45; XRP_1h/BTC_5m floor=0.50

**Rotation 2 experiment order (after gate=0.04 baselines complete):**
Priority pairs for first experiments (highest potential given prior best_knobs proximity to targets):
1. XRP_1h — best avg_profit system-wide, gate=0.08 already nearly at 0.85 target
2. ETH_15m — best pair_cost in system at 0.560, pace_urgency series can improve further
3. SOL_1h — excellent avg_profit +$1.49/bar, bar_budget=400 scale test pending
4. ETH_5m — all benchmarks met, pace_urgency_lo=0.30 can push further below target
5. SOL_15m — profitable, pace series next; but correct_side=47.7% must be monitored

---

## trader_a Benchmark Comparison (post-RESET iter 12 state)
| Pair | PairCost | Target | Gap | Status | Correct_Side | Priority |
|------|----------|--------|-----|--------|--------------|----------|
| BTC_5m | N/A | < 0.85 | N/A | Need gate=0.04 baseline | 65.4% | Medium |
| BTC_15m | N/A | < 0.85 | N/A | Need gate=0.04 baseline | 60.8% | Medium |
| BTC_1h | N/A | < 0.85 | N/A | Need gate=0.04 baseline | 66.7% | Medium |
| ETH_5m | N/A | < 0.85 | N/A | Need gate=0.04 baseline | 51.6% | Medium |
| ETH_15m | N/A | < 0.85 | N/A | Need gate=0.04 baseline | 73.2% | High |
| ETH_1h | N/A | < 0.85 | N/A | Need gate=0.04 baseline | 70.4% | Medium |
| SOL_5m | N/A | < 0.85 | N/A | Need gate=0.04 baseline | 59.8% | Medium |
| SOL_15m | N/A | < 0.85 | N/A | Need gate=0.04 baseline | 47.7% (!) | Monitor |
| SOL_1h | N/A | < 0.85 | N/A | Fix bar_budget first | 68.4% | High |
| XRP_5m | 0.909 (old) | < 0.85 | +0.059 | FROZEN | 57.8% | FREEZE |
| XRP_15m | N/A | < 0.85 | N/A | Need gate=0.04 baseline | 53.7% | Medium |
| XRP_1h | 0.855 | < 0.85 | +0.005 | Near target even at gate=0.08! | 82.6% | Highest |

Pre-RESET best performance reference (expected to return at gate=0.04):
| BTC_5m | 0.922 | BTC_15m | 0.933 | BTC_1h | 0.799 | ETH_5m | 0.633 |
| ETH_15m | 0.560 | ETH_1h | 0.706 | SOL_5m | 0.676 | SOL_15m | 0.696 |
| SOL_1h | 0.655 | XRP_5m | FROZEN | XRP_15m | 0.638 | XRP_1h | 0.674 |

---

## Blacklist (per-pair)
- BTC_5m: skip 0.45/0.55, cheap_threshold 0.07/0.12, onesided 2.0->1.5 (COLLAPSE)
- BTC_15m: skip=0.45 (definitive 3x collapse), bar_budget 400
- BTC_1h: risk_ceil 0.10, skip 0.50, onesided 5->3
- ETH_5m: skip 0.60, onesided 1.5->1.0 (COLLAPSE)
- ETH_15m: skip above 0.50, onesided above 1.5 or below 1.5 (COLLAPSE at 1.0)
- ETH_1h: onesided above 5, skip 0.40, risk_ceil 0.20, bar_budget 250/300
- SOL_5m: skip 0.55, onesided 2.0->1.5 (COLLAPSE at floor=2.0)
- SOL_15m: skip 0.40 (COLLAPSE), onesided 5.0->2.0 (COLLAPSE), bar_budget 400
- SOL_1h: skip 0.35 (COLLAPSE), skip 0.40, risk_ceil 0.20 (tested in regression)
- XRP_5m: ALL (FROZEN)
- XRP_15m: skip 0.40 (collapse), bar_budget 300, risk_ceil 0.20
- XRP_1h: skip 0.45/0.55, bar_budget 300, risk_ceil 0.20, pace_urgency_lo (ineffective on 1h)

## Global Blacklist
- conviction_market_start: GLOBALLY BLACKLISTED — fails across ALL tested pairs (BTC_1h, XRP_15m, XRP_1h, all 1h/15m TFs)
  DO NOT TEST on any remaining pair under any circumstances
- magnitude_gate=0.08: confirmed too aggressive for 11/12 pairs (complete pair formation collapse)
  All knobs files now set to 0.04 — do not revert to 0.08
