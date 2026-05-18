# Architecture

ML system predicting crypto price movements (BTC / ETH / SOL / XRP) on
5m / 15m / 1h timeframes to exploit edge on Polymarket binary
prediction markets.

## Models

| Name | Code Name | What It Does | When It Runs |
|---|---|---|---|
| **Sentinel** | `sentinel` | Bar-level: predicts NEXT bar direction from completed bars | Once per bar completion |
| **Pulse**    | `pulse`    | Late-bar: predicts CURRENT bar outcome from t=0.80 snapshot | Once at 80% of bar elapsed |

Each model is trained per (asset × timeframe) tuple → **12 independent models**
in production. Sentinel + Pulse for the same bar are then fused at the
signal-generation layer.

- Scripts: `scripts/train_sentinel.py`, `scripts/train_pulse.py`
- Model dirs: `data/models/sentinel/{ASSET}_{TF}/`, `data/models/pulse/{ASSET}_{TF}/`

## ML pipeline

- **Data**: Polars + DuckDB + Hive-partitioned Parquet (`data/raw/ohlcv/asset=X/timeframe=Y/date=Z/`).
  1.9 M bars across 4 assets × 3 timeframes, 2022-2026, from Binance Vision
  futures USDT-M, validated with a 5-layer reconciliation.
- **Features**: 37 bar-level features (Sentinel) + 23 intra-bar features (Pulse).
  Computed via Polars expressions for speed.
- **Training**: LightGBM + Optuna HPO. GPU-aware (CUDA auto-detect, fallback to CPU).
- **Calibration**: Isotonic + time-aware bucket calibrator on out-of-sample predictions.
- **Inference**: treelite-compiled LightGBM models for low-latency live scoring.
- **Backtest**: Dual-mode engine — vectorized for HPO sweeps, event-driven for validation.
- **Validation**: Walk-forward with purge+embargo + CPCV with PBO (probability of backtest overfit).
- **Risk**: Fractional Kelly (0.25x), correlation limits across timeframes per asset,
  per-strategy daily-loss circuit breaker.

## Multi-timeframe decision

Each Polymarket contract (5m / 15m / 1h) is a separate market with separate odds.
Cross-timeframe signal combination would merge 3 independent bets into 1 — wrong.
Instead:

- Deploy 12 models independently (one per Polymarket contract).
- Correlation-aware risk management across timeframes (don't oversize same-asset exposure).
- Portfolio-level position limits per asset across all timeframes.

## Autonomous research loop

The `autoresearch/` directory contains an autonomous ML research system that
runs HPO experiments without manual supervision. Roles:

| Agent | Defined in | Responsibility |
|---|---|---|
| `sentinel-dispatch`         | `.claude/agents/sentinel-dispatch.md`    | Orchestrates one research iteration |
| `sentinel-researcher`       | `.claude/agents/sentinel-researcher.md`  | Edits `knobs.json`, runs one experiment, evaluates KEEP/DISCARD |
| `sentinel-strategist`       | `.claude/agents/sentinel-strategist.md`  | Maintains a priority queue + blacklist in `strategy.md` |
| `sentinel-auditor`          | `.claude/agents/sentinel-auditor.md`     | Blocks low-information features; issues RESET / SWITCH / ESCALATE / WIDEN directives |
| `sentinel-analyst`          | `.claude/agents/sentinel-analyst.md`     | Deep statistical analysis of accumulated experiment results |
| `sentinel-builder`          | `.claude/agents/sentinel-builder.md`     | Builds new infrastructure when research phase calls for it |
| `sentinel-reconciler`       | `.claude/agents/sentinel-reconciler.md`  | Compares paper vs live behaviour, opens fixes when divergence is real |
| `dutch-*`                   | `.claude/agents/dutch-*.md`              | Parallel agent loop tuning the Dutch accumulation strategy |

State lives in flat files inside `autoresearch/`: `knobs.json`, `results.tsv`,
`strategy.md`, `audit.md`, `phase.json`, `dispatch_state.json`. Each agent
reads the current state, runs one bounded action, writes new state. This is
deliberately simple — no message bus, no shared Python process, no Celery —
to make it auditable and crash-resistant.

## Production layer

- **Live trading**: `scripts/trade.py` (paper / dry-run / live modes).
- **Multi-asset live monitor**: `scripts/monitor_pulse.py` with Dutch
  accumulation paper trading (`--dutch --asset {BTC,ETH,SOL,XRP}`).
- **Risk gating**: Fractional-Kelly position sizing, daily-loss kill switch,
  per-asset correlation cap, `MIN_ORDER_USD` enforcement.
- **Deployment**: Docker image via GHCR + GitHub Actions self-hosted runner
  (`deploy/trade.service` for systemd, `docker-compose.live.yml` for compose).

## Conventions

- `pathlib.Path` everywhere (cross-platform — codebase runs on both Windows and Linux).
- Polars over Pandas (Rust-backed, 10-50x faster for our feature pipeline).
- All feature computation via Polars expressions; never row-by-row.
- `structlog` with secret redaction.
- Prometheus metrics in `src/qm/monitoring/metrics.py`.
- `keyring`-backed secrets in `src/qm/core/secrets.py` (env var → keyring → `.env` fallback).
- Tests in `tests/unit/` and `tests/integration/`; `tests/benchmark/` for perf regressions.

## Acceptance criteria (must pass before going live)

| Metric | Threshold |
|---|---|
| PBO (probability of backtest overfit) | < 0.40 |
| Deflated Sharpe | > 0.0 |
| OOS Brier score | < 0.25 |
| OOS Expected Calibration Error | < 0.05 |
| Net PnL after costs (paper) | > 0 |
| Max drawdown | < 30% |

## Key files

| Module | Purpose |
|---|---|
| `src/qm/core/types.py`                         | All domain types: Bar, PartialBar, Signal, Asset, etc. |
| `src/qm/core/secrets.py`                       | env → keyring → .env secret loader |
| `src/qm/features/pipeline.py`                  | Sentinel 37-feature pipeline |
| `src/qm/features/intrabar.py`                  | Pulse 23-feature intra-bar calculator |
| `src/qm/backtest/engine.py`                    | Sentinel dual-mode backtest engine |
| `src/qm/backtest/intrabar_backtest.py`         | Pulse intra-bar backtester |
| `src/qm/backtest/market_sim.py`                | Black-Scholes market-odds simulator |
| `src/qm/model/trainers/lgbm_trainer.py`        | LightGBM + Optuna trainer (Sentinel) |
| `src/qm/model/trainers/pulse_trainer.py`       | Pulse walk-forward trainer |
| `src/qm/model/targets/intrabar.py`             | Intra-bar target generation (OHLC path sim) |
| `src/qm/model/calibration/calibrator.py`       | Isotonic + time-aware bucket calibration |
| `src/qm/model/signals.py`                      | Signal generation (edge calculation) |
| `src/qm/strategy/dutch/engine.py`              | Dutch accumulation engine (V7.3) |
| `src/qm/strategy/dutch/fill_simulator.py`      | Limit-order fill simulator (consecutive-tick model) |
| `src/qm/execution/polymarket/`                 | Polymarket CLOB client + EIP-712 signing + relayer integration |
| `scripts/download_historical.py`               | Binance Vision bulk downloader |
| `scripts/train_sentinel.py`, `train_pulse.py`  | End-to-end training entry points |
| `scripts/trade.py`                             | Unified trading script (paper / dry-run / live) |
| `scripts/monitor_pulse.py`                     | Multi-asset Pulse monitor + Dutch accumulation paper trading |
| `PLAN.md`                                      | Implementation plan (extended notes) |
| `docs/PULSE_MODEL_PLAN.md`                     | Pulse intra-bar model design doc |
