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

## Tunable Parameters

See `knobs.json` for all parameters. Key categories:
- Pricing (cheap_threshold, max_pair_cost, max_hedge_ask)
- Pacing (pace_urgency, max_per_prediction, bar_budget, order_size)
- Balance (max_side_fraction, min_share_match, rebalance_warmup)
- Sell logic (sell_loss_threshold, sell_max_fraction, sell_min_shares)
- Fill simulator (fill_ticks, chase_threshold, max_chase)

## Data Sources

- Bar summaries: `data/dutch_paper/BTC_{tf}/bars_*.jsonl`
- Events: `data/dutch_paper/BTC_{tf}/events_*.jsonl`
- Tick snapshots: `data/dutch_paper/BTC_{tf}/ticks_*.jsonl` (for future replay)
- PM2 logs: `data/dutch_{tf}.err.log`, `data/dutch_{tf}.out.log`

## Phase 2 (FUTURE): Backtest Replay

Replay recorded tick JSONL through the engine with different knobs for rapid offline iteration.
