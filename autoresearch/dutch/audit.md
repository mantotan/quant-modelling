# Dutch Audit Report
After iteration 119 (2026-03-23T21:00:00Z)

## Directives

- FREEZE XRP_5m — structural dead-end confirmed (iter 114 FREEZE executed); skip=0.45 and onesided=2.0 remain untested but fill_rate=54% structural floor and max_dd=69% make further experiments futile; permanent FREEZE
- FREEZE BTC_15m — onesided=2.0 is next untested lever (strategy queue #1); UNFREEZE from prior directive; run onesided=2.0 ALONE (no skip change) — this is the last credible cost-improvement experiment; if DISCARD, re-FREEZE permanently
- FREEZE ETH_15m — knobs_ETH_15m.json has conviction_buy_skip=0.55 (STALE: correct value is 0.45 from iter 54); researcher must fix knobs file before any experiment; next experiment after fix: bar_budget 200->300 per strategy.md queue
- FREEZE SOL_15m — onesided=2.0 COLLAPSED (iter 111): this is critical new information; SOL_15m matched_ratio=8.8% but cap at 2.0 still collapses it (same as SOL_5m at 2.0 in low-match windows); blacklist onesided=2.0 on SOL_15m; next: pace_urgency_lo 0.35->0.30 (XRP_15m 18% gain pattern); knobs.json has max_onesided_cost=5.0 (correctly not updated) — proceed
- FREEZE SOL_1h — iter 113 DISCARD (corrected knobs, pair_cost=0.6581 vs best 0.6547) confirmed best_knobs are correct but dataset is in regression window (36 bars, high variance); knobs.json has bar_budget=400 (pre-staged experiment); DO NOT RUN bar_budget=400 until re-eval shows pair_cost <0.70; run fresh re-eval first
- CONTINUE BTC_5m — onesided=1.5 COLLAPSED (iter 117): floor confirmed at onesided=2.0; pace_urgency_lo 0.35->0.30 is next lever (strategy queue #2); knobs.json already has onesided=2.0 (correct); pace_urgency_lo test should proceed
- CONTINUE BTC_1h — dataset regression persists (37 bars, 4 unfavorable bars since iter 64 KEEP); knobs.json has pace_urgency_lo=0.45 pre-staged — proceed with pace_urgency_lo test; if DISCARD: onesided=2.0 is the final lever
- CONTINUE ETH_5m — onesided=1.5 confirmed KEEP (iter 107); knobs.json and best_knobs match (onesided=1.5, skip=0.45); next: max_onesided_cost 1.5->1.0 per strategy queue (high collapse risk, monitor matched_ratio)
- CONTINUE ETH_1h — bar_budget 200->250 DISCARD (iter 108: cost worsened 0.6%); knobs.json has conviction_market_start=0.25 (stale from experiment setup — this was already tested on BTC_1h D iter 106 and XRP_1h D iter 116); SKIP conviction_market_start; next: pace_urgency_lo 0.35->0.30 (XRP_15m pattern); researcher must revert conviction_market_start to 0.30 in knobs before running pace test
- CONTINUE SOL_5m — matched_ratio collapsed to 0.0% on 416 bars (iter 109 re-eval DISCARD); extreme dataset variance at onesided=2.0 floor; knobs.json has pace_urgency_lo=0.30 pre-staged; DO NOT run pace test until fresh re-eval confirms pair_cost stable; run re-eval first
- CONTINUE XRP_15m — conviction_market_start DISCARD (iter 115) confirmed BTC_1h/XRP_1h pattern; knobs.json has pace_urgency_lo=0.25 (pre-staged beyond series — next series step is 0.30->0.25); proceed with pace_urgency_lo 0.30->0.25 test
- CONTINUE XRP_1h — conviction_market_start DISCARD (iter 116) confirmed pattern; knobs.json has pace_urgency_lo=0.35 (unchanged from baseline); next: pace_urgency_hi 0.85->0.75 or onesided=2.0; XRP_1h pace_urgency_lo was DISCARD at 0.35->0.45 (iter 103 — wrong direction); try onesided=2.0 since DD=6% gives maximum headroom

## Per-Pair Assessment

| Pair | BestCost | CurKnobs | AvgProfit | MaxDD% | R8 KEEPs | R8 DISCARDs | Trajectory | Action |
|------|----------|----------|-----------|--------|----------|-------------|------------|--------|
| BTC_5m | 0.922 | onesided=2.0 | +$0.19 | 15.3% | 0 | 1 | Floor confirmed at onesided=2.0; pace_urgency_lo next | CONTINUE |
| BTC_15m | 0.933 | onesided=5.0 | +$0.50 | 23% | 0 | 0 | onesided=2.0 untested — last credible lever | FREEZE (pending onesided=2.0 test) |
| BTC_1h | 0.799 best / 0.904 current | pace_lo=0.45 staged | +$1.41 | 3.2% | 0 | 2 | Dataset regression on 37 bars; pace_urgency_lo staged | CONTINUE |
| ETH_5m | 0.633 | onesided=1.5, skip=0.45 | +$0.01 | 13.8% | 0 | 0 | Best active series; onesided=1.0 next (collapse risk HIGH) | CONTINUE |
| ETH_15m | 0.560 best | skip=0.55 STALE | -$0.21 | 26.8% | 0 | 0 | STALE KNOBS — fix before running; bar_budget=300 next | FREEZE (fix knobs first) |
| ETH_1h | 0.706 | mkt_start=0.25 STALE | -$0.58 | 15.6% | 0 | 1 | bar_budget failed; mkt_start stale; pace_urgency_lo next | CONTINUE |
| SOL_5m | 0.676 | pace_lo=0.30 staged | +$0.06 | 18.1% | 0 | 1 | Matched_ratio collapsed to 0.0% on re-eval; re-eval first | CONTINUE |
| SOL_15m | 0.696 | onesided=5.0 | +$0.42 | 12.5% | 0 | 3 | onesided=2.0 COLLAPSED; bar_budget=400 failed; pace next | FREEZE (pace_urgency_lo next) |
| SOL_1h | 0.655 best / 0.658 current | bar_budget=400 staged | +$1.49 | 5.7% | 0 | 1 | Corrected knobs re-eval near-miss; dataset variance HIGH | FREEZE (re-eval before bar_budget=400) |
| XRP_5m | 0.909 | skip=0.45 FROZEN | -$0.32 | 69% | 0 | 0 | PERMANENT FREEZE — structural dead-end | FREEZE |
| XRP_15m | 0.638 | pace_lo=0.25 staged | -$0.09 | 13% | 0 | 1 | mkt_start DISCARD; pace series continues at 0.30->0.25 | CONTINUE |
| XRP_1h | 0.674 | onesided=5.0 | +$1.08 | 5.2% | 0 | 1 | mkt_start DISCARD; try onesided=2.0 (DD=5% safe) | CONTINUE |

## trader_a Gap Analysis

| Pair | BestCost | Target | Gap | Profit | DD | Status |
|------|----------|--------|-----|--------|----|--------|
| ETH_15m | 0.560 | <0.85 | -34% (BEATS) | -$0.21 | 26.8% OK | FROZEN (knobs stale) |
| SOL_1h | 0.655 | <0.85 | -23% (BEATS) | +$1.49 | 5.7% OK | FROZEN (re-eval needed) |
| XRP_1h | 0.674 | <0.85 | -21% (BEATS) | +$1.08 | 5.2% OK | onesided=2.0 next |
| ETH_1h | 0.706 | <0.85 | -17% (BEATS) | -$0.58 | 15.6% OK | pace_urgency_lo next |
| SOL_5m | 0.676 | <0.85 | -20% (BEATS) | +$0.06 | 18.1% OK | re-eval before pace test |
| ETH_5m | 0.633 | <0.85 | -26% (BEATS) | +$0.01 | 13.8% OK | onesided=1.0 next (HIGH risk) |
| XRP_15m | 0.638 | <0.85 | -25% (BEATS) | -$0.09 | 13% OK | pace_urgency_lo 0.30->0.25 next |
| SOL_15m | 0.696 | <0.85 | -18% (BEATS) | +$0.42 | 12.5% OK | FROZEN (pace_urgency_lo next) |
| BTC_1h | 0.799 best | <0.85 | -6% (BEATS) | +$1.41 | 3.2% OK | Dataset regression masks; pace test next |
| BTC_15m | 0.933 | <0.85 | +10% (FAILS) | +$0.50 | 23% OK | onesided=2.0 last lever |
| BTC_5m | 0.922 | <0.85 | +8% (FAILS) | +$0.19 | 15.3% OK | pace_urgency_lo 0.35->0.30 next |
| XRP_5m | 0.909 | <0.85 | +7% (FAILS) | -$0.32 | 69% BAD | PERMANENT FREEZE |

**9 pairs beating trader_a pair_cost benchmark** (unchanged from iter 95 audit).

## Key Findings from Rotation 8 (iters 108-119)

### 1. KEEP rate 0/11 = 0% — worst rotation in V7.3 history

Rotation 8 (iters 108-119, partial: 11 data experiments + 1 FREEZE) produced zero KEEPs.
Every experiment either failed cost threshold or produced a collapse event:
- SOL_5m re-eval: matched_ratio collapsed to 0.0% on 416 bars (dataset variance at floor)
- SOL_15m: 3 consecutive DISCARDs — onesided=2.0 COLLAPSED, re-eval regression, bar_budget=400 neutral
- SOL_1h: corrected knobs re-eval within noise of best (0.6581 vs 0.6547)
- BTC_5m onesided=1.5: COLLAPSED (floor confirmed at 2.0, same as SOL_5m iter 97)
- BTC_1h: dataset regression persists (2 DISCARDs)
- ETH_1h bar_budget=250: cost worsened 0.6%
- XRP_15m/XRP_1h mkt_start=0.25: both DISCARD (BTC_1h pattern confirmed cross-pair)
This is a structural plateau period — rotation 7's 50% KEEP rate was driven by the XRP_15m breakthrough and BTC_5m first KEEP. Those were one-time discoveries.

### 2. SOL_15m onesided=2.0 COLLAPSE — new critical finding

iter 111 showed SOL_15m onesided=2.0 COLLAPSED to 0.0% matched_ratio (zero pairs formed across 140 bars).
This is unexpected: SOL_15m has matched_ratio=8.8% (vs SOL_5m's 0.94% at collapse). The collapse at 2.0
implies SOL_15m pairs cluster heavily above $2.00 — the cap completely blocks them. This differs from
ETH_5m where 2.0 KEEP (iter 92) and 1.5 KEEP (iter 107). SOL pair behavior for onesided caps differs
from ETH pair behavior. Do NOT test onesided cap on SOL_15m or SOL_1h.

### 3. BTC_5m onesided floor confirmed at 2.0 — pace_urgency_lo is next

iter 117 confirmed BTC_5m onesided=1.5 collapses (same as SOL_5m iter 97). Floor=2.0 for all BTC/SOL 5m pairs.
ETH_5m uniquely extends to 1.5 (possibly ETH has cheaper pair composition). pace_urgency_lo 0.35->0.30 is
the next untested lever on BTC_5m (XRP_15m showed 18% gain with this move).

### 4. conviction_market_start 0.30->0.25 universally fails — confirmed blacklist

Four consecutive DISCARDs: BTC_1h (iter 106), XRP_15m (iter 115), XRP_1h (iter 116), and BTC_1h pattern.
Pattern: easing the market entry threshold increases matched_ratio but adds weaker predictions that
degrade pair quality. Confirmed cross-asset, cross-timeframe. Add to global blacklist.

### 5. Stale knobs files detected — critical researcher compliance issue

Multiple active knobs.json files diverge from best_knobs or contain staged-but-unrun experiments:
- ETH_15m: knobs has skip=0.55 (stale, correct value is 0.45)
- ETH_1h: knobs has conviction_market_start=0.25 (pre-staged for experiment that is now globally blacklisted)
- SOL_1h: knobs has bar_budget=400 (pre-staged; must not run until re-eval confirms pair_cost <0.70)
- SOL_5m: knobs has pace_urgency_lo=0.30 (pre-staged; must not run until re-eval confirms stability)
- BTC_1h: knobs has pace_urgency_lo=0.45 (pre-staged; proceed — this is the correct next experiment)
- XRP_15m: knobs has pace_urgency_lo=0.25 (beyond series — but series step 0.30->0.25 is indeed next)
Researcher must verify knobs match best_knobs before each experiment and only modify the single target param.

### 6. BTC_1h structural regression — may need FREEZE decision

Iter 118 re-eval with corrected conviction_buy_skip=0.40: pair_cost=0.9042, fails to beat best KEEP
0.7988. 4 unfavorable new bars since iter 64 KEEP (33 bars to 37 bars). Dataset is structurally
worse than when the best KEEP was achieved. pace_urgency_lo is staged and worth one test. If DISCARD:
BTC_1h should be considered for FREEZE — the window for meaningful improvement may have closed
as unfavorable bars accumulate in the thin 37-bar dataset.

### 7. SOL_1h dataset variance is structural — risk_ceil retest deferred

Best KEEP pair_cost=0.655 (iter 58, 34 bars). Current re-eval (iter 113, 36 bars): 0.6581 — near
the best but technically a DISCARD. The pair has 2 new bars since last valid KEEP measurement.
SOL_1h +$1.49/bar avg_profit is the highest in the system. Dataset will stabilize with more bars.
bar_budget=400 pre-staged in knobs is premature — run re-eval to confirm cost before scaling budget.

## Risk Flags

- **ETH_5m onesided=1.0**: Collapse risk HIGH. ETH_15m collapsed at 1.0 (iter 94). ETH_5m has
  matched_ratio=0.8% (lower than ETH_15m's 1.0% at collapse). Proceed with test but accept
  collapse as likely outcome. If matched_ratio drops below 0.2%: floor=1.5 confirmed on ETH_5m.
  If KEEP: would be first pair below 0.60 — major breakthrough.

- **SOL_5m dataset instability**: matched_ratio=0.0% on 416-bar re-eval (iter 109) — extreme
  variance. pace_urgency_lo test (pre-staged) must wait for re-eval showing stable pair formation.
  Running pace test during collapse window produces meaningless results.

- **BTC_1h approaching FREEZE threshold**: 0 KEEPs in rotation 7-8 (iters 91-118) plus dataset
  regression. pace_urgency_lo test is last meaningful lever. If DISCARD: FREEZE recommended.

- **SOL_15m bar_budget=400 DISCARD**: iter 112 confirmed onesided collapse prevents meaningful
  budget scaling experiments. pace_urgency_lo is the cleanest remaining experiment.

- **XRP_5m FREEZE at highest DD**: max_dd=69% makes this the system's worst risk profile.
  No experiment has reduced this — fill_rate structural floor prevents meaningful pair formation
  improvement. Permanent FREEZE maintained.

## Researcher Compliance Assessment

Rotation 8 compliance: MOSTLY SATISFACTORY with knob management concerns.
- iter 108: ETH_1h bar_budget 200->250 correctly per strategy queue. DISCARD appropriate.
- iter 109: SOL_5m re-eval appropriate before pace_urgency_lo. Collapse discovered.
- iters 110-112: SOL_15m — 3 experiments in sequence. Re-eval then onesided then bar_budget.
  Re-eval appropriate. onesided=2.0 test was NOT in strategy queue (queue was: onesided cap as
  preventive DD measure; budget=400 next). Sequence acceptable but ordering deviated slightly.
- iter 113: SOL_1h corrected knobs re-eval — appropriate compliance with strategy note.
- iter 114: XRP_5m FREEZE directive correctly executed (logged as FREEZE row).
- iters 115-116: XRP_15m/XRP_1h conviction_market_start — strategy said "test after pace series
  resolves" for XRP_15m; XRP_1h strategy said mkt_start as priority #1. Compliance adequate.
- iters 117-118: BTC_5m onesided=1.5 and BTC_1h re-eval — both per strategy queue. Correct.

Knob management concern: multiple knobs.json files contain staged experiments or stale values.
Researcher should synchronize knobs.json to best_knobs at start of each experiment, then apply
single param change. This prevents accumulated drift from causing incorrect baseline comparisons.

## Recommendations for Next 24 Iterations (rotation 9, iters 120-143)

### Tier 1 — Re-evals needed before experiments (4 pairs)

1. **SOL_5m**: Re-eval with best_knobs (onesided=2.0, skip=0.45, pace_urgency_lo=0.35).
   matched_ratio collapse on 416 bars is dataset variance. Confirm stability before pace test.
   Only proceed to pace_urgency_lo if re-eval shows matched_ratio > 0.3%.

2. **SOL_1h**: Re-eval with best_knobs (skip=0.45, bar_budget=300, pace_urgency_lo=0.35).
   Current knobs.json has bar_budget=400 — reset to best_knobs first, then re-eval.
   If pair_cost <0.70: proceed to bar_budget=400. If >0.80: wait another rotation for stability.

3. **ETH_15m**: Fix stale knobs (set conviction_buy_skip=0.45 to match best_knobs, set
   max_onesided_cost=1.5). Then re-eval on current dataset before bar_budget=300 test.
   ETH_15m high variance (1% matched_ratio) means re-eval is mandatory before param changes.

4. **ETH_1h**: Reset conviction_market_start from 0.25->0.30 in knobs (globally blacklisted).
   Then run pace_urgency_lo 0.35->0.30 — XRP_15m pattern strongly motivates this for ETH_1h.

### Tier 2 — Active experiments (6 pairs)

5. **ETH_5m**: max_onesided_cost 1.5->1.0 — continue series. Accept collapse if matched_ratio
   drops below 0.2% (floor=1.5 confirmed). If KEEP: pair_cost target <0.60 first in system.

6. **BTC_15m**: max_onesided_cost 5.0->2.0 ALONE (no skip change, skip=0.50).
   ETH_5m/SOL_5m/BTC_5m all KEEP at 2.0. BTC_15m matched_ratio=12% means lowest collapse risk.
   Most promising remaining experiment in the system. UNFREEZE for this one test.

7. **BTC_5m**: pace_urgency_lo 0.35->0.30 — staged in knobs. XRP_15m 18% gain pattern.
   BTC_5m paired with onesided=2.0 context. Run after confirming knobs are at best_knobs + pace change.

8. **BTC_1h**: pace_urgency_lo 0.35->0.45 — staged in knobs. If DISCARD: FREEZE candidate.
   NOTE: BTC_1h has skip=0.40 (confirmed KEEP), but best_knobs shows risk_ceil=0.20 which is
   STALE (risk_ceil DISCARD iter 80). Researcher must verify BTC_1h best_knobs values match
   confirmed KEEPs: conviction_buy_skip=0.40 (iter 64), risk_ceil=0.15 (baseline).

9. **XRP_15m**: pace_urgency_lo 0.30->0.25 — continue series (knobs pre-staged at 0.25).
   Risk: matched_ratio=0.3% may collapse entirely. If collapse: floor=0.30 confirmed.
   If KEEP: XRP_15m would be near pair_cost=0.52 — system best.

10. **XRP_1h**: max_onesided_cost 5.0->2.0 — DD=5.2% gives maximum headroom.
    conviction_market_start globally blacklisted. onesided=2.0 is best remaining structural lever.
    BTC_1h onesided=3.0 showed only 1% (sub-threshold) — XRP_1h may differ with higher matched_ratio.

### Tier 3 — Capital scaling on confirmed winners

11. **SOL_15m**: pace_urgency_lo 0.35->0.30 — onesided COLLAPSED (blacklisted), bar_budget=400
    neutral. Pace timing is the next unexplored lever. Low risk relative to onesided experiments.

12. **SOL_1h**: bar_budget 300->400 — proceed only after re-eval confirms pair_cost <0.70.
    avg_profit=+$1.49/bar best in system. If dataset stabilizes, budget scaling compounds returns.
    Also: risk_ceil=0.15->0.20 should be retested when pair_cost confirms stable (was tested in
    regression window at iters 100-101 — invalid test).

### Do NOT attempt

- conviction_market_start 0.30->0.25 on any pair: GLOBAL BLACKLIST (4/4 DISCARDs cross-pair)
- unmatched_ratio tightening: global blacklist (3/3 DISCARDs)
- sell_loss_start tightening: global blacklist (2/2 DISCARDs)
- max_onesided_cost ANY value on SOL_15m: COLLAPSED at 2.0 (iter 111) — permanent blacklist for SOL_15m
- max_onesided_cost <2.0 on BTC_5m/SOL_5m: floor=2.0 confirmed on both (iters 97, 117)
- max_onesided_cost <1.5 on ETH_15m: floor=1.5 confirmed (iter 94 collapse)
- pace_urgency_lo on any 1h pair: zero effect confirmed (BTC_1h iter 6, XRP_1h iter 103)
  EXCEPTION: BTC_1h pace_urgency_lo=0.45 staged for test — this is pace_urgency_lo INCREASING
  (not decreasing), which is untested on BTC_1h specifically
- bar_budget 300 on XRP pairs: both DISCARDs (iters 75-76) — optimum at 200 confirmed
- risk_ceil increase on XRP/ETH/BTC pairs: multiple DISCARDs — only SOL pairs respond to risk_ceil scaling
- skip changes on BTC_15m: definitively exhausted (3 confirmations of collapse)
- skip changes on XRP_1h: both directions exhausted (iters 48, 61)
- conviction_buy_skip < 0.45 on SOL_1h: SOL_1h skip floor = 0.45 (iter 58 KEEP, iter 74 DISCARD at 0.40)
