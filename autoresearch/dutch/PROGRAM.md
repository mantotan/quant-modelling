# Dutch Accumulation Autoresearch

## Objective

Autonomously optimize DutchConfig parameters for bilateral accumulation of Polymarket binary UP/DOWN tokens. Target: replicate the performance of trader trader_a ((redacted)).

## Key Metrics (targets from trader_a analysis)

| Metric | Target | Description |
|--------|--------|-------------|
| avg_pair_cost | < 0.85 | Average cost per matched pair (< 1.0 = profit) |
| correct_side_pct | > 0.55 | Fraction of bars where unmatched side wins |
| matched_ratio | > 0.30 | min(UP,DN) / max(UP,DN) shares |
| fill_rate | > 0.50 | Filled orders / placed orders |
| sell_ratio | 0.10-0.40 | Sell events / buy events (capital recycling) |

## Architecture

Single dispatch loop (`/loop 20m dutch-dispatch`) with 4 roles:
- **Monitor**: Check PM2 health + anomaly detection (runs ~hourly)
- **Researcher**: ONE parameter change → wait 8 bars → evaluate KEEP/DISCARD
- **Strategist**: Every ~5 iterations, analyze KEEP rates, write priority queue
- **Auditor**: Every ~20 iterations, deep analysis, issue directives

## Tunable Parameters (V7)

See `knobs.json` for all parameters. Key categories:
- Pair cost (cheap_threshold, max_marginal_pair_cost)
- Pacing (pace_urgency_lo/hi, max_per_prediction, bar_budget, order_size)
- Risk budget (risk_floor, risk_ceil, risk_t_start, risk_t_end, risk_exponent)
- Conviction (conviction_market_start, conviction_market_full)
- Unmatched cap (min_unmatched_shares, unmatched_ratio)
- Balance (max_side_fraction)
- Sell (sell_loss_start, sell_dump_start, sell_max_fraction, sell_min_shares, rebalance_warmup)
- Fill simulator (fill_ticks, sweep_threshold, chase_threshold, max_chase, spread_offset, cancel_distance)

## Fill Simulator V3 (2026-03-21)

Maker-only simulation matching production `post_only=True` behavior:
- **Buy orders**: placed at bid (maker) or at ask-0.01 (aggressive tiers). Never at/above ask.
- **Sell orders**: placed at ask (maker on sell side). Fill when bid >= ask.
- **fill_ticks=10** (~5s): ask must stay at/below limit for 10 consecutive book updates.
- **Sweep detection**: price passes through limit by >= 1c → instant fill on tick 1.
- **Zero-depth rejection**: no depth at limit price → order stays pending.
- **Chase**: below ask only, max 2 chases, cancel at >= 5c drift.
- **Sell depth**: checks `book.bids` (not asks) for sell-side liquidity.

## Data Sources

- Bar summaries: `data/dutch_paper/BTC_{tf}/bars_*.jsonl`
- Events: `data/dutch_paper/BTC_{tf}/events_*.jsonl`
- Tick snapshots: `data/dutch_paper/BTC_{tf}/ticks_*.jsonl` (for future replay)
- PM2 logs: `data/dutch_{tf}.err.log`, `data/dutch_{tf}.out.log`

## Phase 2 (FUTURE): Backtest Replay

Replay recorded tick JSONL through the engine with different knobs for rapid offline iteration.
