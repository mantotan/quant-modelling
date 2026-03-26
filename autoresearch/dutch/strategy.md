# Dutch Strategy
Updated: after iteration 60 (2026-03-27T19:15:00Z) — STRATEGIST rotation 6 pre-run analysis

## Summary

Rotation 5 complete (iters 49-59) + BTC_5m diagnostic (iter 60): 7 SKIPs + 2 DISCARDs (ETH_1h pace, XRP_1h onesided) + 1 SKIP+DIAGNOSTIC (BTC_5m spot outcomes test).
**KEEP rate this rotation: 0/2 active experiments = 0%**
**Cumulative KEEP rate: 0/60 = 0% across all rotations.**

Rotation 6 has NOT started (no experiments run yet). This strategist update confirms the
fill_ticks=2 experiments are ready to stage and provides explicit researcher instructions.

Critical findings from rotation 5 + diagnostic:
1. ETH_1h pace lever is statistically inert below ~10 matched pairs (confirmed twice: iters 29, 53)
2. XRP_1h onesided=2.0 causes complete pair-formation collapse (same mechanism as pace=0.30 collapse)
3. BTC_5m diagnostic: spot outcomes do NOT unblock frozen pairs — fill mechanics are the binding constraint
   - P(both sides fill in 5m bar) = fill_rate^2 ≈ 0.237^2 = 5.6% — structurally impossible
   - This CONFIRMS all 5m pairs are permanently frozen regardless of outcome source
4. Fill mechanics hypothesis for 15m/1h frozen pairs:
   - 15m: P(both sides fill) ≈ 0.40^2 = 16% — possible but low
   - 1h: P(both sides fill) ≈ 0.80^2 = 64% — viable (explains why ETH_1h/XRP_1h are only active pairs)

**Researcher compliance (rotation 5):** EXCELLENT — 100% compliance. All frozen pair SKIPs respected,
experiments run exactly per priority queue, diagnostic task completed per auditor mandate.

---

## AUDITOR FREEZES (active — do NOT run experiments)

- **XRP_5m**: FROZEN permanently. fill_rate=15.6% structural floor. Zero pairs at all gates.
- **SOL_15m**: FROZEN. correct_side=45.5% (both measurements below 50%). Resume only when correct_side > 50%.
- **XRP_15m**: FROZEN (iter 48 audit). correct_side=49.2% declining monotonically. Gate exhausted.
- **BTC_5m**: FROZEN permanently (confirmed by diagnostic iter 60). Fill mechanics block pair formation
  regardless of outcome source. P(both sides fill in 5m) ≈ 5.6%. No levers remain.
- **BTC_15m**: FROZEN. 3 consecutive zero-pair baselines. Outcome sparsity (11/139=7.9%).
- **BTC_1h**: FROZEN. Extreme sparsity (1/34=2.9%). Gate series exhausted.
- **ETH_5m**: FROZEN. max_dd=28.7% near 30% kill threshold. 3 consecutive zero-pair baselines.
- **ETH_15m**: FROZEN. Gate series fully exhausted R4 (iters 5/17/40 = gate=0.08/0.04/0.0 all zero pairs).
- **SOL_5m**: FROZEN. 3 consecutive zero-pair runs. max_dd=23.2% elevated.
- **SOL_1h**: FROZEN. 3 consecutive zero-pair baselines. Outcome sparsity (3/35=8.6%).

---

## ETH_1h (pair_cost=0.594 at gate=0.04 pace=0.35, KEEP rate 0% but trending — pair_cost BEATS target)

### Status: ACTIVE — PRIORITIZE (auditor directive)

Full trajectory:
- Iter 6 (R1): cost=0.000, zero pairs at gate=0.08
- Iter 18 (R2 baseline): cost=0.594, matched=2.0%, profit=-$0.06/bar, DD=13.8%
- Iter 29 (R3 pace=0.25): DISCARD — identical to baseline (thin dataset, pace inert)
- Iter 41 (R4 baseline pace=0.35): cost=0.594, matched=2.0%, profit=+$0.08/bar, DD=7.6%
- Iter 53 (R5 pace=0.30): DISCARD — identical to baseline (pace lever confirmed statistically inert)
- Iters 61+ (R6): fill_ticks 1->2 experiment STAGED and ready to run

ETH_1h is the **best performer in the system**: pair_cost=0.594 ALREADY BEATS trader_a target of <0.85.
DD improved 13.8%->7.6% between R2 and R4 baselines. Profit improved -$0.06->+$0.08/bar.
The pair_cost metric is excellent — focus is now on increasing matched_ratio from 2.0% to improve
statistical significance and profit stability.

**Current knobs state (VERIFIED rotation 6 start):**
- knobs_ETH_1h.json: fill_ticks=1 — MUST STAGE fill_ticks=2 before running
- best_knobs_ETH_1h.json: fill_ticks=1 — baseline reference (do NOT modify until KEEP confirmed)
- Note: conviction_buy_skip=0.45 in both files (correct for ETH_1h)

**Staging instruction for researcher:**
BEFORE running ETH_1h experiment, set fill_ticks=2 in knobs_ETH_1h.json fill_simulator section.
Do NOT modify best_knobs_ETH_1h.json until KEEP is confirmed.

**Priority queue for rotation 6:**
1. **fill_ticks 1->2 EXPERIMENT** — stage fill_ticks=2 in knobs_ETH_1h.json before running
   - Hypothesis: fill_ticks=2 allows limit orders to persist across 2 tick intervals instead of 1,
     increasing fill_rate from ~85% toward ~95%+ and potentially increasing matched_ratio above 2%
   - Baseline ref: pair_cost=0.594, profit=+$0.08/bar, DD=7.6%, matched=2.0%
   - Accept KEEP if: matched_ratio > 2.0% OR avg_profit > +$0.08/bar (ANY improvement)
   - DISCARD if: pair_cost increases above 0.65 OR DD exceeds 12% OR matched_ratio drops below 1.5%
   - If KEEP: update best_knobs_ETH_1h.json with fill_ticks=2
   - If DISCARD: restore fill_ticks=1 in knobs_ETH_1h.json; next lever = chase_threshold 0.03->0.05
2. If fill_ticks=2 KEEPs: chase_threshold 0.03->0.05 (wider chase window may improve fill quality)
3. If fill_ticks=2 DISCARDs: try pace_urgency_hi 2.0->1.5 (reduce late urgency spike)
4. If all fill sim experiments DISCARD: try bar_budget 200->250 (more capital per bar, may improve pair
   formation in thin dataset) — note: bar_budget 250/300 is blacklisted but 250 was from early rotation;
   worth re-testing now that pair_cost baseline is 0.594 not 0.98

Blacklist (cumulative): onesided above 5, skip 0.40, risk_ceil 0.20, bar_budget 250/300,
pace_urgency_lo 0.25 AND 0.30 (both DISCARD — pace lever is DEAD on thin dataset),
conviction_market_start (GLOBAL BLACKLIST).
**PACE_LO LEVER: EXHAUSTED for ETH_1h. All tested values (0.25, 0.30, 0.35) produce identical results.**

---

## XRP_1h (pair_cost=0.812 at gate=0.04 onesided=5.0, KEEP rate 0%)

### Status: ACTIVE — CONTINUE (auditor directive)

Full trajectory:
- Iter 12 (R1 baseline): cost=0.855, matched=3.6%, profit=N/A, DD=3.1%
- Iter 23 (R2 baseline): cost=0.812, matched=4.2%, profit=+$0.10/bar, DD=8.0%
- Iter 35 (R3 pace=0.30): DISCARD — COLLAPSE (0% matched vs 4.2%); PACE FLOOR CONFIRMED 0.35
- Iter 47 (R4 baseline onesided=5.0): cost=0.812, matched=4.1%, profit=-$0.14/bar, DD=9.8%
- Iter 59 (R5 onesided=2.0): DISCARD — COLLAPSE (0% matched vs 4.1%)
- Iters 61+ (R6): fill_ticks 1->2 experiment STAGED and ready to run

XRP_1h meets pair_cost target (<0.85) but profit has turned negative. Two consecutive collapse events
(pace=0.30 and onesided=2.0) confirm XRP_1h is extremely sensitive to constraint tightening.
The onesided=2.0 collapse reveals the same mechanism as pace=0.30: any constraint that limits
the $3-5 unmatched spend required to form pairs causes complete pair formation failure.

**Current knobs state (VERIFIED rotation 6 start):**
- knobs_XRP_1h.json: fill_ticks=1, onesided=5.0, magnitude_gate=0.04 — MUST STAGE fill_ticks=2
- best_knobs_XRP_1h.json: fill_ticks=1, onesided=5.0, magnitude_gate=0.04 — baseline reference
- Both files are IDENTICAL (post-DISCARD restoration confirmed iter 59)
- Note: conviction_buy_skip=0.5 in both files (correct for XRP_1h)

**Staging instruction for researcher:**
BEFORE running XRP_1h experiment, set fill_ticks=2 in knobs_XRP_1h.json fill_simulator section.
Do NOT modify best_knobs_XRP_1h.json until KEEP is confirmed.
CRITICAL: do NOT change onesided, pace_urgency_lo, or magnitude_gate — only fill_ticks changes.

**Priority queue for rotation 6:**
1. **fill_ticks 1->2 EXPERIMENT** — stage fill_ticks=2 in knobs_XRP_1h.json before running
   - Hypothesis: fill_ticks=2 increases fill persistence, improving fill quality for 1h limit orders
     without changing the unmatched spend mechanism that collapses pair formation
   - Baseline ref: pair_cost=0.812, profit=-$0.14/bar, DD=9.8%, matched=4.1%
   - Accept KEEP if: pair_cost < 0.812 OR avg_profit > -$0.14/bar (ANY improvement on either metric)
   - DISCARD if: matched_ratio drops below 2.0% OR DD exceeds 15%
   - Note: fill_ticks is a fill-sim parameter, not a pacing constraint — should NOT trigger collapse
   - If KEEP: update best_knobs_XRP_1h.json with fill_ticks=2
   - If DISCARD: restore fill_ticks=1; next lever = intermediate onesided test (see item 2)
2. If fill_ticks=2 DISCARDs: test onesided=3.5 (intermediate between 5.0 and 2.0 COLLAPSE)
   - Rationale: onesided=2.0 collapses at $2, onesided=5.0 is current reference; $3.5 middle ground
   - Accept KEEP if: pair_cost < 0.812 OR avg_profit > -$0.14/bar
   - If collapse (matched_ratio < 2.0%): DISCARD, confirm onesided floor at 5.0
3. If both fill_ticks and onesided=3.5 DISCARD: try pace_urgency_hi 2.0->1.5 (reduce late urgency)
4. If 3 consecutive DISCARDs: escalate to auditor — XRP_1h may be at structural floor

Blacklist (cumulative): skip 0.45/0.55, bar_budget 300, risk_ceil 0.20,
pace_urgency_lo 0.30 (COLLAPSE iter 35), pace_urgency_lo 0.45 (D pre-RESET),
max_onesided_cost 2.0 (COLLAPSE iter 59 — $2 too tight for sparse window).
PACE_LO FLOOR: 0.35 confirmed. Do NOT go below 0.35 on XRP_1h.
ONESIDED FLOOR: 5.0 current reference; do NOT go below 3.0 without testing 3.5 first.

---

## Rotation 6 Execution Plan (priority order)

1. **BTC_5m** — SKIP (FROZEN PERMANENT — diagnostic confirmed fill mechanics block, not outcomes)
2. **BTC_15m** — SKIP (FROZEN — 3 consecutive zero-pair baselines, outcome sparsity 7.9%)
3. **BTC_1h** — SKIP (FROZEN — extreme sparsity 2.9%)
4. **ETH_5m** — SKIP (FROZEN — DD=28.7% near kill threshold)
5. **ETH_15m** — SKIP (FROZEN — gate series exhausted, outcome sparsity 9.9%)
6. **ETH_1h** — **fill_ticks 1->2 EXPERIMENT** (stage fill_ticks=2 in knobs_ETH_1h.json, run backtest)
7. **SOL_5m** — SKIP (FROZEN — outcome sparsity 6.7%, DD elevated)
8. **SOL_15m** — SKIP (FROZEN — correct_side=45.5% < 50%)
9. **SOL_1h** — SKIP (FROZEN — outcome sparsity 8.6%)
10. **XRP_5m** — SKIP (FROZEN PERMANENT)
11. **XRP_15m** — SKIP (FROZEN — correct_side declining, gate exhausted)
12. **XRP_1h** — **fill_ticks 1->2 EXPERIMENT** (stage fill_ticks=2 in knobs_XRP_1h.json, run backtest)

**Rotation 6 success criteria:**
- At minimum 1 KEEP required
- If 0 KEEPs on fill_ticks experiments: auditor should assess whether fill_sim tuning is exhausted
  and recommend suspension pending structural engineering fix (outcome resolution or fill mechanics)
- The diagnostic finding (fill mechanics bottleneck) suggests fill_ticks is a targeted fix —
  optimism is warranted but expectations should be calibrated given 0/60 cumulative KEEP rate

---

## Cross-Pair Observations

### Rotation 5 + diagnostic critical findings

**Fill mechanics are the fundamental bottleneck for 5m pairs (and likely 15m pairs):**
- 5m: fill_rate ~15-25% → P(both sides fill) ≈ 2.25%-6.25% — structurally impossible
- 15m: fill_rate ~30-45% → P(both sides fill) ≈ 9%-20% — borderline
- 1h: fill_rate ~70-85% → P(both sides fill) ≈ 49%-72% — viable

This is the most important structural insight from 60 iterations. The gate experiments (R1-R3) and
the diagnostic (R6 iter 60) have definitively established that outcome sparsity is secondary to
fill mechanics. The engine cannot form pairs without both sides filling in the same bar.

**Outcome sparsity remains a secondary bottleneck for 1h pairs:**
- ETH_1h: 4/34 bars resolved = 11.8% resolution — sparse but workable
- XRP_1h: ~5/35 bars resolved = ~14% resolution — sparse but workable
- Without additional live-log data accumulation, matched_ratio will remain at ~2-4% for 1h pairs

**pace_urgency_lo lever is dead for ETH_1h:**
- All 3 tested values (0.25, 0.30, 0.35) produce identical pair_cost=0.594
- The statistical power of 34-35 bars with 4 outcomes is insufficient to detect pace changes
- This lever should not be re-tested on ETH_1h until dataset grows (>50 bars, >10 outcomes)

**Collapse mechanism for XRP_1h:**
- Any constraint that limits cumulative unmatched spend below $3-5 per bar causes complete
  pair formation failure — pair formation requires accumulating unmatched inventory before matching
- onesided=2.0 (like pace=0.30) acts as a hard cap that prevents the required pre-matching spend
- fill_ticks is a fill simulator parameter (not a spending constraint) — should be safe to test

**Parameter categories: which levers remain untested:**
- Fill sim: fill_ticks (UNTESTED on both active pairs — NEXT PRIORITY for rotation 6)
- Fill sim: chase_threshold (untested — queued for rotation 7 if fill_ticks KEEPs)
- Fill sim: max_chase (untested — lower priority)
- Sell: sell_loss_start, sell_dump_start (untested but no sells firing — not relevant yet)
- Risk budget: risk_t_start, risk_t_end (untested — lower priority given pair_cost already meets target)
- Balance: max_side_fraction 0.55 (untested)

---

## trader_a Benchmark Comparison (after rotation 5 + diagnostic, iter 60)

| Pair | PairCost | Target | Gap | AvgProfit | MaxDD% | Status |
|------|----------|--------|-----|-----------|--------|--------|
| BTC_5m | 0.000 | < 0.85 | N/A | -$0.060/bar | 23.4% | FROZEN PERMANENT — fill mechanics (P≈5.6%) |
| BTC_15m | 0.000 | < 0.85 | N/A | -$0.019/bar | 12.4% | FROZEN — outcome sparsity + zero pairs |
| BTC_1h | 0.000 | < 0.85 | N/A | -$0.032/bar | 3.9% | FROZEN — extreme sparsity (2.9%) |
| ETH_5m | 0.000 | < 0.85 | N/A | -$0.091/bar | 28.7% | FROZEN — DD WARNING, fill mechanics (P≈5.8%) |
| ETH_15m | 0.000 | < 0.85 | N/A | +$0.158/bar | 7.1% | FROZEN — gate exhausted, strong signal wasted |
| ETH_1h | 0.594 | < 0.85 | -0.256 (BEATS) | +$0.080/bar | 7.6% | ACTIVE — fill_ticks=2 experiment queued |
| SOL_5m | 0.000 | < 0.85 | N/A | +$0.135/bar | 23.2% | FROZEN — fill mechanics (P≈4.2%) |
| SOL_15m | 0.567* | < 0.85 | N/A | -$0.270/bar | 19.8% | FROZEN — correct_side=45.5% < 50% |
| SOL_1h | 0.000 | < 0.85 | N/A | -$0.110/bar | 8.3% | FROZEN — outcome sparsity (8.6%) |
| XRP_5m | N/A | < 0.85 | N/A | N/A | N/A | FROZEN PERMANENT — fill_rate=15.6% floor |
| XRP_15m | 0.950 | < 0.85 | +0.100 (FAILS) | -$0.240/bar | 20.5% | FROZEN — correct_side=49.2% declining |
| XRP_1h | 0.812 | < 0.85 | -0.038 (BEATS) | -$0.140/bar | 9.8% | ACTIVE — fill_ticks=2 experiment queued |

*SOL_15m: artificially low pair_cost (near-zero pairs)

Best performers (active, pair_cost beats target):
- ETH_1h: pair_cost=0.594 — BENCHMARK ACHIEVED. profit=+$0.08/bar positive.
- XRP_1h: pair_cost=0.812 — BENCHMARK ACHIEVED. profit=-$0.14/bar negative, needs fix.

Pairs with strong signal quality but frozen by structural issues:
- ETH_15m: correct_side=71.2%, avg_profit=+$0.16/bar (unmatched) — highest latent potential
- BTC_1h: correct_side=70.0% — strong signal, blocked by extreme sparsity (2.9%)
- BTC_5m: correct_side=62.9% — blocked by fill mechanics (structural, unfixable without engineering)

---

## Blacklist Summary

### Per-pair blacklists

- **BTC_5m**: FROZEN PERMANENT. All parameter experiments blocked indefinitely.
  Fill mechanics are the structural barrier (not outcome sparsity, not gate).
- **BTC_15m**: FROZEN. gate=0.08/0.04/0.0 all fail; outcome sparsity dominant.
- **BTC_1h**: FROZEN. gate=0.08/0.04/0.0 all fail; extreme outcome sparsity (2.9%).
- **ETH_5m**: FROZEN. gate series exhausted; DD=28.7% near 30% kill threshold.
- **ETH_15m**: FROZEN. gate series exhausted; outcome sparsity (9.9%). Strong signal = most promising
  candidate to unfreeze IF outcome resolution engineering delivers more live-log data.
- **ETH_1h**: pace_urgency_lo 0.25 AND 0.30 (both inert — lever DEAD on thin dataset).
  onesided above 5, skip 0.40, risk_ceil 0.20, bar_budget 250/300, conviction_market_start (GLOBAL).
- **SOL_5m**: FROZEN. fill mechanics dominant (fill_rate=23.1%, P≈5.3%).
- **SOL_15m**: FROZEN. correct_side=45.5% both measurements < 50%.
- **SOL_1h**: FROZEN. gate series exhausted; outcome sparsity (8.6%).
- **XRP_5m**: FROZEN PERMANENT. fill_rate=15.6% structural floor.
- **XRP_15m**: FROZEN. correct_side declining (53.7%->50.0%->49.2%); gate exhausted.
- **XRP_1h**: skip 0.45/0.55, bar_budget 300, risk_ceil 0.20, pace_urgency_lo 0.30 (COLLAPSE),
  pace_urgency_lo 0.45 (D), max_onesided_cost 2.0 (COLLAPSE — $2 too tight for sparse window).

### Global Blacklist

- **conviction_market_start**: GLOBALLY BLACKLISTED. Fails across ALL tested pairs.
- **magnitude_gate=0.08/0.04/0.02/0.0**: Exhausted for all pairs. Gate parameter is irrelevant
  for any pair with outcome sparsity or fill mechanics bottleneck.
- **pace_urgency_lo < 0.35**: GLOBALLY BLACKLISTED below 0.35. COLLAPSE mechanism confirmed on
  multiple pairs. ETH_1h: lever dead entirely (iters 29/53 both identical). XRP_1h: floor at 0.35.
- **max_onesided_cost < 3.0**: BLACKLISTED. onesided=2.0 causes COLLAPSE on XRP_1h by hitting
  the $2 cap before pair formation can complete. Test minimum 3.5 before any tighter values.
- **Any experiment on frozen pairs**: BLOCKED until auditor lifts freeze or structural fix deployed.

### Structural Engineering Recommendations (for future audit/development)
1. **Outcome resolution rate**: Current 8-14% for 1h pairs is the binding long-term constraint.
   Engineering fix: ingest more live-log data OR implement OHLC-based outcome resolution.
   This would unfreeze ETH_15m and potentially BTC_1h/SOL_1h.
2. **Fill mechanics for 5m/15m pairs**: P(both sides fill in bar) is structurally low.
   Engineering fix: increase order persistence (fill_ticks), widen spread_offset, or use
   market orders for small sizes. The fill_ticks=2 experiment is the first test of this approach.
3. **Dataset growth**: ETH_1h/XRP_1h only have 34-35 bars. Statistical power is very low.
   Most parameter changes are undetectable. Dataset will grow naturally over time.
