# Dutch Audit Report
After iteration 71 (2026-03-23T17:00:00Z)

## Directives
- FREEZE ETH_5m — correct_side=37.3% below 38% warning floor; skip=0.45 KEEP but approaching anti-predictive floor; no remaining levers beyond onesided_cost cap
- FREEZE XRP_5m — fill_rate structurally capped at 54% (fill_ticks=15 showed zero improvement), max_dd=69% with no profitable pathway; XRP_5m is a structural dead-end
- CONTINUE BTC_5m — both skip directions exhausted, cheap_threshold failed; only lever remaining is risk_ceil/pace_urgency_lo; still profitable baseline
- CONTINUE BTC_15m — both skip=0.45 (DD>30%) and bar_budget=300 failed; try compound change: skip=0.45 + max_onesided_cost=3.0
- CONTINUE BTC_1h — skip=0.40 KEEP (0.7988, best BTC cost); test skip=0.35 or risk_ceil/bar_budget scale
- CONTINUE ETH_15m — max_onesided_cost=2.0 KEEP (0.7032, max_dd halved to 32.5%); next: max_onesided_cost 2.0->1.5 or risk_ceil
- CONTINUE ETH_1h — skip=0.40 DISCARD confirms 0.45 is optimum; test risk_ceil or bar_budget scale
- CONTINUE SOL_5m — skip=0.45 KEEP (0.8140, near-breakeven); next: max_onesided_cost 5.0->2.0 to reduce max_dd=31.1%
- CONTINUE SOL_15m — skip=0.45 confirmed; skip=0.40 not yet tested (XRP_15m skip=0.40 collapsed, so skip this); test bar_budget 200->300
- CONTINUE SOL_1h — skip=0.45 confirmed at 0.6605; test skip=0.40 cautiously (skip=0.35 collapsed); still best pair
- CONTINUE XRP_15m — skip=0.40 collapsed pair formation; skip 0.45 is confirmed optimum; test bar_budget 200->300 next
- CONTINUE XRP_1h — both skip directions exhausted (0.45 worsened, 0.55 worsened); skip=0.50 is optimum; test risk_ceil or bar_budget scale

## Per-Pair Assessment
| Pair | BestCost | AvgProfit | MaxDD% | KEEPs | DISCARDs | Trajectory | Action |
|------|----------|-----------|--------|-------|----------|------------|--------|
| BTC_5m | 0.948 | +$0.055 | 24% | 0 | 4 | Stalled — all skip and cheap_threshold failed | CONTINUE |
| BTC_15m | 0.933 | +$0.498 | 23% | 0 | 3 | Stalled — skip DD>30%, bar_budget regressed | CONTINUE |
| BTC_1h | 0.799 | -$0.326 | 8.7% | 2 | 3 | Improving — skip series progressing (0.50->0.45->0.40) | CONTINUE |
| ETH_5m | 0.782 | -$0.210 | 47% | 2 | 2 | Fragile — correct_side at 37.3%, approaching floor | FREEZE |
| ETH_15m | 0.703 | -$0.322 | 32.5% | 3 | 3 | Improving — onesided cap effective; needs DD further reduction | CONTINUE |
| ETH_1h | 0.706 | -$0.487 | 17% | 2 | 2 | Stable — skip=0.45 optimum confirmed; needs profit lever | CONTINUE |
| SOL_5m | 0.814 | +$0.001 | 31.1% | 2 | 1 | Improving — skip=0.45 works; DD near 30% threshold | CONTINUE |
| SOL_15m | 0.796 | -$0.078 | 14.3% | 1 | 2 | Stable — skip=0.45 confirmed; skip=0.40 untested | CONTINUE |
| SOL_1h | 0.661 | +$0.542 | 9.1% | 3 | 2 | Best pair — stable and profitable, room to scale | CONTINUE |
| XRP_5m | 0.909 | -$0.323 | 69% | 1 | 1 | Dead-end — fill_rate structural floor, high DD | FREEZE |
| XRP_15m | 0.778 | +$0.010 | 17.2% | 1 | 3 | Stable — skip=0.40 collapsed; 0.45 is floor | CONTINUE |
| XRP_1h | 0.674 | +$1.081 | 6% | 1 | 2 | Optimal — both skip directions exhausted; scale now | CONTINUE |

## trader_a Gap Analysis
| Pair | BestCost | Target | Gap | Profit | DD | ETA (rotations) |
|------|----------|--------|-----|--------|----|-----------------|
| SOL_1h | 0.661 | <0.85 | -0.189 (BEATS +22%) | +$0.54 | 9% (OK) | DONE — scale capital |
| XRP_1h | 0.674 | <0.85 | -0.176 (BEATS +20%) | +$1.08 | 6% (OK) | DONE — scale capital |
| ETH_1h | 0.706 | <0.85 | -0.144 (BEATS +17%) | -$0.49 | 17% (OK) | Cost DONE — fix profit |
| ETH_15m | 0.703 | <0.85 | -0.147 (BEATS +17%) | -$0.32 | 32.5% (marginal) | Cost DONE — fix DD |
| XRP_15m | 0.778 | <0.85 | -0.072 (BEATS +8%) | +$0.01 | 17% (OK) | Cost DONE — scale modestly |
| SOL_15m | 0.796 | <0.85 | -0.054 (BEATS +6%) | -$0.08 | 14% (OK) | Cost DONE — scale modestly |
| BTC_1h | 0.799 | <0.85 | -0.051 (BEATS +6%) | -$0.33 | 8.7% (OK) | Cost DONE — fix profit |
| SOL_5m | 0.814 | <0.85 | -0.036 (BEATS +4%) | +$0.001 | 31% (marginal) | Cost DONE — reduce DD |
| ETH_5m | 0.782 | <0.85 | -0.068 (BEATS +8%) | -$0.21 | 47% (bad) | FREEZE — DD/anti-pred risk |
| BTC_15m | 0.933 | <0.85 | +0.083 | +$0.50 | 23% (OK) | ~2-3 rotations |
| BTC_5m | 0.948 | <0.85 | +0.098 | +$0.055 | 24% (OK) | ~3-4 rotations |
| XRP_5m | 0.909 | <0.85 | +0.059 | -$0.32 | 69% (bad) | FREEZE — structural floor |

## Key Findings from Rotation 4 (iters 59-71)

### 1. Skip series now complete across all testable pairs
The conviction_buy_skip=0.45 pattern (confirmed in rotation 3 on 15m/1h) has now been validated on
all 5m pairs where the signal supports it:
- SOL_5m skip=0.45: KEEP (0.8140, near-zero profit, max_dd=31.1%) — iter 71
- ETH_5m skip=0.45: KEEP (0.7819, max_dd=47.3%, correct_side=37.3%) — iter 66
- XRP_5m: NOT tested — structurally frozen (fill_rate floor, high DD)
- BTC_5m: Both skip directions DISCARD — skip is not the lever

**9 of 11 tested pairs now at or below 0.85 benchmark** (excluding frozen XRP_5m and stuck BTC_5m/BTC_15m).

### 2. Skip=0.40 results: mixed collapse pattern
- BTC_1h skip=0.40: KEEP (0.7988, 8.3% improvement) — iter 64
- XRP_15m skip=0.40: DISCARD (pair formation collapsed to 0%) — iter 60
- ETH_1h skip=0.40: DISCARD (pair_cost worsened 0.7058->0.7212) — iter 69
- SOL_1h skip=0.35: DISCARD (pair formation collapsed to 0%) — prior rotation
- SOL_15m skip=0.40: NOT YET TESTED

Pattern: skip=0.40 works only on BTC_1h (moderate-volume, 1h TF); collapses pair formation on
lower-throughput pairs (XRP_15m matched_ratio was only 2% at 0.45). The 0.40 floor appears to be
pair-specific. SOL_15m is worth testing once (matched_ratio 4.8% at 0.45 — borderline).

### 3. max_onesided_cost=2.0 confirmed effective on 15m TFs
ETH_15m: 5.0->2.0 halved max_dd (54.5%->32.5%) and improved pair_cost 6.3% — iter 68 KEEP.
This should be tested on SOL_5m (max_dd=31.1%), which is now near the 30% threshold.
Not applicable to 1h TFs (cap never triggered at $5).

### 4. BTC pairs remain the hardest to optimize
- BTC_5m: 0/4 KEEPs in V7.3 — skip, cheap_threshold, bar_budget all failed. Only untested levers:
  risk_ceil increase and pace_urgency_lo adjustment. Profitable baseline (+$0.055) but stuck at 0.948.
- BTC_15m: 0/3 KEEPs in V7.3 — skip caused DD>30%, bar_budget regressed cost, cheap_threshold marginal.
  Compound change (skip=0.45 + onesided_cap=3.0) is the last credible hypothesis.
- BTC_1h: 2/2 KEEPs in V7.3 — the only BTC success story. Skip series progressing well at 0.40.

### 5. ETH_5m approaching anti-predictive zone
ETH_5m: correct_side dropped 44.6% (baseline) -> 40.9% (re-eval) -> 37.3% (skip=0.45). Each KEEP
has pushed correct_side lower. The 38% warning floor has been breached (37.3%). Further skip
reduction would almost certainly enter fully anti-predictive territory. With max_dd=47% and
negative avg_profit, the only remaining lever (max_onesided_cost=2.0) could reduce DD but cannot
fix a near-random signal. ETH_5m should be FROZEN after this audit.

### 6. XRP_5m is structurally constrained
fill_ticks=15 showed exactly 0% improvement in fill_rate (still 54%). This is a microstructure
floor for XRP_5m — the market does not offer sufficient tick depth. With max_dd=69% and no
profitable pathway, further experiments waste iterations. FREEZE.

### 7. Profitable pairs ready for capital scaling
Three pairs are both profitable AND below 0.85 benchmark:
- SOL_1h: pair_cost=0.661, +$0.54/bar, max_dd=9% — prime candidate for bar_budget 200->400
- XRP_1h: pair_cost=0.674, +$1.08/bar, max_dd=6% — prime candidate for bar_budget 200->300+
- XRP_15m: pair_cost=0.778, +$0.01/bar, max_dd=17% — modest scale (bar_budget 200->300 cautiously)
- SOL_5m: pair_cost=0.814, +$0.001/bar, max_dd=31% — near-breakeven but DD needs reduction first

## Risk Flags
- **ETH_5m**: correct_side=37.3% below 38% floor. Skip has progressively degraded signal quality.
  Further experiments risk full anti-predictive regime. FREEZE directive issued.
- **XRP_5m**: fill_rate=54% is structural (confirmed by fill_ticks=15 showing zero improvement).
  max_dd=69% with -$0.32/bar profit makes this pair unviable for further experimentation. FREEZE.
- **ETH_15m**: max_dd=32.5% still above 30% acceptance threshold despite halving via onesided_cap.
  Further DD reduction needed before this pair meets criteria. Next lever: max_onesided_cost 2.0->1.5.
- **SOL_5m**: max_dd=31.1% is just over the 30% threshold. The skip=0.45 KEEP brought it to profitability
  but DD is marginal. Priority: test max_onesided_cost=2.0 before any other experiment.
- **BTC_1h**: avg_profit turned negative at skip=0.40 (-$0.33/bar). Cost improved well (0.7988) but
  the profit/cost tradeoff may be degrading. Monitor whether further skip reduction helps or hurts.
- **XRP_15m**: correct_side=33.3% is already very low. Do not test any further skip reduction.
  The skip=0.45 at 0.7780 is the floor for this pair. Budget scaling is the next lever.

## Researcher Compliance Assessment
researcher_ack (iter 70-71) correctly identified SOL_5m as the next target and executed the
recommended skip=0.45 test per strategy.md priority order. The KEEP on both re-eval (iter 70) and
skip change (iter 71) followed proper KEEP RELAXED criteria. Compliance is satisfactory.

Prior rotation compliance: researcher correctly tested XRP_5m fill_ticks (iter 59), XRP_15m skip=0.40
(iter 60), XRP_1h skip=0.55 (iter 61), BTC_5m cheap_threshold (iter 62), BTC_15m bar_budget (iter 63)
before the profitable segment. All per strategy.md priority order. No compliance issues.

## Recommendations for Next 24 Iterations (rotation 5, iters 72-95)

### Tier 1 — Scale confirmed winners with low DD
1. **SOL_1h** (0.661, +$0.54/bar, 9% DD): bar_budget 200->400. Lowest DD, positive profit — safest scale.
2. **XRP_1h** (0.674, +$1.08/bar, 6% DD): bar_budget 200->300. Best profit in system, very safe DD.
3. **XRP_15m** (0.778, +$0.01/bar, 17% DD): bar_budget 200->300. Modest scale on benchmark-beating pair.

### Tier 2 — Fix DD on marginal pairs
4. **SOL_5m** (0.814, +$0.001, 31% DD): max_onesided_cost 5.0->2.0. DD just over 30% threshold.
   ETH_15m analog confirms this lever is effective. PRIORITY before any other SOL_5m experiment.
5. **ETH_15m** (0.703, -$0.32, 32.5% DD): max_onesided_cost 2.0->1.5. Need DD below 30%.
   If this reduces max_dd below 30%, pair meets all acceptance criteria except profit.

### Tier 3 — Continue profitable series
6. **BTC_1h** (0.799, -$0.33, 8.7% DD): skip=0.40 confirmed. Test risk_ceil 0.15->0.20 to improve
   avg_profit. Low DD (8.7%) provides headroom. Alternatively bar_budget 200->300 cautiously.
7. **SOL_15m** (0.796, -$0.08, 14% DD): test skip=0.45->0.40 ONE TIME. Matched_ratio 4.8% at 0.45
   is borderline — collapse possible (XRP_15m precedent). If collapses, move to bar_budget=300.
8. **ETH_1h** (0.706, -$0.49, 17% DD): test risk_ceil 0.15->0.20 or bar_budget 200->300.
   Skip series exhausted at 0.45. Need profit lever without disturbing cost.

### Tier 4 — Unlock BTC pairs
9. **BTC_15m**: compound change conviction_buy_skip 0.50->0.45 WITH max_onesided_cost 5.0->3.0.
   Single-lever skip=0.45 caused DD>30%. Simultaneous DD cap may control this. High-impact test.
10. **BTC_5m**: pace_urgency_lo 0.35->0.45. Skip exhausted, cheap_threshold failed. Entry timing
    is the only untested lever. Alternatively risk_ceil 0.15->0.20 (24% DD provides headroom).

### Do NOT attempt
- ETH_5m: FROZEN. correct_side=37.3%, anti-predictive trajectory.
- XRP_5m: FROZEN. Structural fill_rate floor confirmed.
- XRP_15m skip further reduction: skip=0.40 collapsed pair formation — do not retry.
- XRP_1h skip reduction or raising: both directions DISCARD — skip=0.50 is permanent optimum.
- ETH_1h skip=0.40: DISCARD confirmed — skip=0.45 is permanent optimum.
- bar_budget doubling (200->400) on BTC pairs: BTC_1h confirmed worse at 400 (iter 36).
- max_onesided_cost increasing on 1h TFs: confirmed no-op (ETH_1h iter 55).
- unmatched_ratio tightening: Global blacklist (3/3 DISCARDs).
- sell_loss_start tightening: Global blacklist (2/2 DISCARDs).
