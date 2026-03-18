# ML/Quant Crypto Polymarket Prediction System — Implementation Plan

## Context

Build a production-grade ML system that predicts crypto price movements (BTC, ETH, XRP, SOL) on 5m/15m/1h timeframes to exploit edge on Polymarket prediction markets. This is a greenfield project — no existing code.

**Polymarket crypto market structure:**
- **5m/15m markets**: Binary Up/Down — "resolve to 'Up' if price at end of window >= price at beginning." Resolved via Chainlink Data Streams.
- **Monthly markets**: "Will BTC hit $X this month?" — resolved via Binance 1-minute candle highs.

**Core ML problem**: Predict calibrated P(Up) for a given window, compare against Polymarket market-implied P(Up), bet when edge exceeds costs.

**Hardware**: RTX 4090 24GB, 96GB RAM, i7-10700, 2TB NVMe + 8TB HDD. More than sufficient.

**Platform strategy**:
- **Development + backtesting**: Windows 11 (native) — research, feature engineering, model training, backtesting all run here
- **Production (inference + live trading)**: Ubuntu Linux — the deployed system runs on Linux for reliability, systemd service management, and lower overhead
- **WSL2 available** on the Windows machine for Linux-specific testing and Docker workloads
- **Code must be cross-platform**: use `pathlib.Path` everywhere (no hardcoded backslashes), avoid Windows-only APIs, test critical paths under WSL2 before production deployment
- **Docker containers** (TimescaleDB, Prometheus, Grafana) run via WSL2/Docker Desktop on Windows, natively on Linux production
- **[ADDED] Dependency lockfile**: use `uv` with `uv.lock` for reproducible cross-platform installs (uv resolves platform-specific wheels automatically)
- **[ADDED] CI gate**: run `pytest` + `ruff` + `mypy` under both Windows and WSL2/Linux before merging to main

---

## Project Structure

```
c:\quant-modelling\
├── pyproject.toml                      # Dependencies, project metadata, tool configs
├── uv.lock                             # [ADDED] Locked dependencies for cross-platform reproducibility
├── Makefile                            # Common commands: test, lint, format, docker
├── docker-compose.yml                  # TimescaleDB, Redis, Prometheus, Grafana
├── docker-compose.prod.yml             # [ADDED] Production overrides (no ports exposed, restart policies)
├── alembic.ini                         # DB migration config
├── .env.example                        # Environment variable template (NO real secrets)
├── .gitignore                          # [ADDED] Must cover: .env, data/, *.pkl, *.parquet, __pycache__
├── .pre-commit-config.yaml             # ruff, mypy, pytest hooks
├── deploy/                             # [ADDED] Deployment artifacts
│   ├── qm.service                     # systemd service file for Linux production
│   ├── deploy.sh                      # rsync + restart script (Windows→Linux)
│   └── Dockerfile                     # Production container
│
├── conf/                               # Hydra configuration root
│   ├── config.yaml                     # Main config with defaults list
│   ├── env/                            # [ADDED] Environment overlays
│   │   ├── dev.yaml                   # Windows dev: local DB, debug logging, small bets
│   │   └── prod.yaml                  # Linux prod: prod DB URL, JSON logging, real limits
│   ├── exchanges/                      # binance.yaml, bybit.yaml
│   ├── polymarket/                     # clob.yaml, markets.yaml
│   ├── data/                           # timescaledb.yaml, duckdb.yaml, storage.yaml
│   ├── features/                       # registry.yaml, engineering.yaml
│   ├── model/                          # lightgbm.yaml, calibration.yaml, ensemble.yaml
│   ├── backtest/                       # engine.yaml, costs.yaml
│   ├── execution/                      # risk.yaml, sizing.yaml, paper.yaml
│   └── monitoring/                     # prometheus.yaml, alerting.yaml
│
├── migrations/versions/                # Alembic DB migrations (each MUST have downgrade())
│
├── src/qm/                             # Main package
│   ├── core/                           # Shared primitives
│   │   ├── types.py                    # Asset, Timeframe, MarketType, Side, Signal, Bar
│   │   ├── constants.py                # SUPPORTED_ASSETS, TIMEFRAMES
│   │   ├── clock.py                    # Wall-clock + simulated clock for backtest
│   │   ├── events.py                   # Typed event bus, pub/sub
│   │   ├── errors.py                   # Exception hierarchy
│   │   ├── protocols.py               # ExchangeConnector, FeatureCalculator, Trainer, Sizer, CVSplitter
│   │   └── secrets.py                 # [ADDED] Secret loader: env vars → keyring → .env fallback
│   │
│   ├── data/                           # PHASE 1
│   │   ├── connectors/                 # ccxt_ws.py, polymarket_ws.py, health.py
│   │   ├── ingestion/                  # manager.py, trade_handler.py, bar_builder.py, bar_aligner.py
│   │   ├── storage/                    # timescale.py, parquet.py, duckdb_store.py, schemas.py
│   │   ├── quality/                    # gap_detector.py, outlier_filter.py, reconciler.py
│   │   └── historical/                # backfill.py, polymarket_hist.py
│   │
│   ├── features/                       # PHASE 2
│   │   ├── registry.py                 # Feature registry: name, dtype, compute_fn, lookback
│   │   ├── base.py                     # FeatureCalculator base class
│   │   ├── pipeline.py                 # Feature computation DAG with dependency ordering
│   │   ├── store.py                    # DuckDB + Parquet feature store (batch: backtest/train)
│   │   ├── live_cache.py              # [ADDED] In-memory rolling feature window (live inference)
│   │   ├── selection.py                # Importance, correlation filter, stability
│   │   └── groups/                     # price, volatility, momentum, microstructure,
│   │                                   # volume, cross_asset, regime, time, polymarket
│   │
│   ├── backtest/                       # PHASE 2 (engine) + PHASE 4 (validation runs)
│   │   ├── engine.py                   # Dual-mode: fast vectorized + full event-driven
│   │   ├── clock.py                    # Simulated clock stepping through bar timestamps
│   │   ├── data_feed.py               # Historical bars + features reader
│   │   ├── portfolio.py               # Position/cash/PnL tracking during simulation
│   │   ├── cost_model.py              # Polymarket fees (currently ~0bps maker), spread, slippage
│   │   ├── order_simulator.py         # Simulates fills against historical books
│   │   ├── report.py                  # HTML/PDF backtest report generation
│   │   ├── validation/                # walk_forward.py, cpcv.py, purging.py, splitter.py
│   │   └── metrics/                   # performance.py, calibration.py, statistical.py
│   │
│   ├── model/                          # PHASE 3
│   │   ├── targets/                    # binary.py (Up/Down), threshold.py (monthly), labeler.py
│   │   ├── trainers/                   # lgbm_trainer.py, temporal_trainer.py, meta_trainer.py
│   │   ├── calibration/               # calibrator.py, isotonic.py, platt.py, validator.py
│   │   ├── ensemble/                  # stacker.py, blender.py, diversity.py
│   │   ├── registry.py                # Model versioning + artifact storage
│   │   ├── experiment.py              # Experiment tracking
│   │   └── signals.py                 # Model prob -> edge vs PM odds -> Signal
│   │
│   ├── strategy/                       # PHASE 4-5
│   │   ├── edge.py                     # Edge calculation: P_model - P_market - costs
│   │   ├── sizing/                     # kelly.py, fixed.py, meta_sized.py
│   │   ├── filter.py                  # Min edge, min confidence, max correlation
│   │   └── portfolio.py               # Portfolio-level allocation across concurrent bets
│   │
│   ├── execution/                      # PHASE 5
│   │   ├── polymarket/                # client.py, market_scanner.py, order_manager.py, position_tracker.py
│   │   ├── paper/                     # engine.py, recorder.py
│   │   ├── reconciliation.py         # Cross-check local vs Polymarket positions
│   │   └── audit.py                  # [ADDED] Immutable append-only trade audit log
│   │
│   ├── risk/                           # PHASE 5
│   │   ├── manager.py                 # Pre-trade + post-trade risk checks
│   │   ├── limits.py                  # Position limits, daily loss, drawdown circuit
│   │   ├── correlation.py            # Cross-bet correlation, concentration risk
│   │   ├── bankroll.py               # HWM tracking, Kelly readjustment
│   │   └── circuit_breaker.py        # Emergency shutdown: staleness, drift, PnL
│   │
│   ├── monitoring/                     # Grows across all phases
│   │   ├── metrics.py                 # Prometheus counters/gauges/histograms
│   │   ├── alerting.py               # Drift, drawdown, feed-down alerts
│   │   ├── logging.py                # Structured logging (structlog)
│   │   └── dashboards/               # Grafana JSON: trading, model, data
│   │
│   ├── scheduler/                      # runner.py, jobs.py, lifecycle.py
│   └── cli/commands/                   # ingest, backfill, features, train, backtest, paper, live
│
├── crates/                             # [ADDED] Rust fast-path extensions
│   └── qm-fast/                       # PyO3/maturin module → `import qm_fast`
│       ├── Cargo.toml
│       ├── pyproject.toml             # maturin build config
│       └── src/                       # features/, orderbook/, signing/
│
├── tests/                              # unit/, integration/, backtest/, benchmark/
├── notebooks/                          # Research notebooks (01-06)
├── scripts/                            # setup_timescaledb.sh, download_historical.py
└── data/                               # gitignored: raw/, features/, models/, reports/
```

---

## Phase 1: Data Infrastructure (Weeks 1-3)

### Week 1: Core + Exchange Connectors + Bar Construction
**Files**: `src/qm/core/*`, `src/qm/data/connectors/ccxt_ws.py`, `src/qm/data/ingestion/bar_builder.py`, `src/qm/data/ingestion/bar_aligner.py`

- Core types: `Asset`, `Timeframe`, `MarketType`, `Bar`, `Signal`, `PolymarketOrder`
- Core protocols: `ExchangeConnector`, `FeatureCalculator`, `Trainer`, `CVSplitter`, `Sizer`
- **[ADDED] `src/qm/core/secrets.py`** — Secret loading hierarchy: (1) environment variables, (2) system keyring via `keyring` library, (3) `.env` file fallback. NEVER log secret values. Secrets needed: `POLYMARKET_PRIVATE_KEY`, `POLYMARKET_API_KEY`, `BINANCE_API_KEY`, `BINANCE_API_SECRET`, `BYBIT_API_KEY`, `BYBIT_API_SECRET`, `TIMESCALEDB_URL`
- ccxt Pro websocket connector: `watch_trades()` for BTC/ETH/XRP/SOL on Binance + Bybit
  - Build OHLCV from raw trades (not exchange bars) for accuracy
  - Auto-reconnect with exponential backoff (max 60s), health monitoring with heartbeat timeout
  - **[ADDED]** On disconnect mid-bar: flush partial bar as incomplete, mark gap, emit `DataGap` event. BarBuilder must handle re-sync on reconnect (request REST snapshot to fill gap)
- Bar construction aligned to Polymarket window boundaries (ET timezone, every 5m on clock)
  - **[ADDED]** DST transition handling: use `zoneinfo.ZoneInfo("America/New_York")` which handles DST automatically. Add explicit test cases for March/November DST transitions
  - **[ADDED]** NTP enforcement: on startup, check system clock against `time.google.com`. Warn if drift > 500ms, abort if drift > 2s. Use `ntplib` library

### Week 2: Storage + Polymarket Connector
**Files**: `src/qm/data/storage/*`, `src/qm/data/connectors/polymarket_ws.py`, `docker-compose.yml`, `migrations/`

- TimescaleDB: `trades` hypertable (1h chunks), `ohlcv` hypertable (1d chunks), `polymarket_snapshots`
  - **[ADDED]** Data retention policies: raw trades TTL = 7 days (continuous aggregate to OHLCV then drop), OHLCV retained indefinitely, Polymarket snapshots TTL = 90 days
  - **[ADDED]** TimescaleDB compression: enable native compression on chunks older than 1 day (10-20x space reduction)
  - **[ADDED]** Disk monitoring: alert at 80% NVMe usage, auto-archive cold parquet to HDD (E: drive) at 85%
- Parquet: Hive-style partitioning `data/raw/ohlcv/asset=BTC/timeframe=5m/date=YYYY-MM-DD/`
- Polymarket CLOB websocket: real-time odds, spread, volume for active crypto prediction markets
- **[ADDED]** Docker security: `docker-compose.yml` must NOT bind TimescaleDB to 0.0.0.0 — use `127.0.0.1:5432` only. Grafana behind auth. Prometheus no external access

### Week 3: Data Quality + Historical Backfill
**Files**: `src/qm/data/quality/*`, `src/qm/data/historical/*`, `scripts/download_historical.py`

- Gap detection, outlier filtering (>5 sigma single-exchange spikes), completeness scoring
- Historical backfill: ccxt `fetch_ohlcv()` for 2+ years, Polymarket `/prices-history`
  - **[ADDED]** Backfill is idempotent: use upsert (ON CONFLICT DO NOTHING) so re-runs are safe
  - **[ADDED]** Rate limit awareness: Binance 1200 req/min, Bybit 120 req/5s. Implement adaptive backoff
- Reconciliation: periodic REST snapshots to validate websocket state
- **[ADDED]** Polymarket historical data caveat: 5m crypto markets are relatively new. Expect 6-12 months of history max. For longer backtest periods, use exchange OHLCV data with synthetic Polymarket odds (assume market-implied = 50% ± noise) to validate the model's directional accuracy independent of PM-specific features

---

## Phase 2: Feature Engineering + Backtesting Engine + Fast Path (Weeks 4-8)

### Week 4: Feature Registry + Core Feature Groups (Research Path)
**Files**: `src/qm/features/registry.py`, `src/qm/features/base.py`, `src/qm/features/pipeline.py`, `src/qm/features/groups/{price,volatility,momentum}.py`

- Feature registry: single source of truth — name, dtype, compute_fn, lookback, dependencies
- Topological sort for dependency-aware computation ordering
- All computation via Polars expressions for speed
- Price features: returns (1/5/12), log returns, VWAP deviation, gap, bar position
- Volatility: realized, Parkinson, Garman-Klass, vol-of-vol
- Momentum: RSI, MACD, ROC, Stochastic

### Week 5: Advanced Features + Feature Store
**Files**: `src/qm/features/groups/{microstructure,volume,cross_asset,regime,time,polymarket}.py`, `src/qm/features/store.py`, `src/qm/features/selection.py`

- Microstructure: orderbook imbalance, trade flow toxicity (VPIN), spread dynamics
- Cross-asset: BTC-ETH correlation, lead-lag, beta to BTC
- Regime: HMM state, volatility regime, trend strength
- **Polymarket-specific**: implied prob, spread, volume, prob momentum, odds-price divergence
- Feature store: DuckDB for fast reads, Parquet for persistence
  - **[ADDED]** Point-in-time enforcement: feature store `read()` method takes a `as_of` timestamp parameter. All queries filter `WHERE time <= as_of`. Cross-asset features must use the latest available data per asset AT that timestamp, not the latest row across all assets (which could be from the future for a slow-updating asset)
- Selection: remove >50% missing, <0.01 target correlation, >0.95 pairwise correlation

### Week 6: Backtesting Engine Core
**Files**: `src/qm/backtest/engine.py`, `src/qm/backtest/clock.py`, `src/qm/backtest/portfolio.py`, `src/qm/backtest/cost_model.py`, `src/qm/backtest/order_simulator.py`

**Dual-mode engine** — this is a critical design decision:
1. **`evaluate_model_fast()`** — vectorized PnL, no order simulation. Used during Optuna HPO in Phase 3 training loop. Must be fast (thousands of evaluations).
2. **`run_full_simulation()`** — event-driven with order fills, spread, portfolio tracking. Used for final OOS validation in Phase 4. Must be realistic.

- Cost model: Polymarket fee schedule + empirical spread model
  - **[ADDED]** Liquidity-aware slippage: cost model must use historical orderbook depth, not fixed spread. For a $100 bet, walk the book to compute actual fill price. Cap bet size at 10% of available depth on the side you're trading to avoid adverse price impact
- Portfolio: tracks positions, cash, PnL, open/resolved bets

### Week 7: Walk-Forward, CPCV, Statistical Metrics
**Files**: `src/qm/backtest/validation/{walk_forward,cpcv,purging,splitter}.py`, `src/qm/backtest/metrics/{performance,calibration,statistical}.py`

- Walk-forward: anchored + sliding window, purge period (1h at 5m bars), embargo
- CPCV: C(10,2) = 45 paths, probability of backtest overfitting (PBO)
- Metrics: Sharpe, Sortino, Calmar, max DD, win rate, Brier score, ECE, reliability diagram
- Statistical: deflated Sharpe ratio (multiple testing correction), minimum backtest length

### Week 8: Rust Fast Path (`crates/qm-fast/`)
**Files**: `crates/qm-fast/src/{lib.rs, features/, orderbook/, signing/}`

Build the Rust extension module that powers the live inference hot path:

1. **Rolling feature engine** (`features/rolling.rs`)
   - Pre-allocated ring buffer holds last N bars per asset per timeframe
   - Each feature is an incremental computation: on new bar, update only the delta (O(1) per feature)
   - Example: rolling mean = `(old_sum - dropped_bar + new_bar) / window_size`, no recomputation
   - Expose to Python via `qm_fast.update_bar(asset, bar_data)` and `qm_fast.get_features(asset) → numpy`
   - Zero-copy numpy export via PyO3's numpy integration

2. **Orderbook manager** (`orderbook/l2_book.rs`)
   - Maintain sorted L2 orderbook per asset from websocket deltas
   - `qm_fast.apply_book_delta(asset, bids, asks)` — apply incremental update
   - `qm_fast.get_book_state(asset) → (best_bid, best_ask, mid, spread, depth_at_size)`
   - Price impact calculator: `qm_fast.price_impact(asset, side, size) → fill_price`

3. **EIP-712 order signer** (`signing/eip712.rs`)
   - Uses `alloy` crate for EIP-712 typed data hashing + secp256k1 signing
   - `qm_fast.sign_order(token_id, price, size, side, nonce, expiration) → signed_order_json`
   - Private key loaded once at startup into Rust memory (never exposed back to Python)

4. **CI parity tests** (`tests/`)
   - For every Rust function, a Python reference implementation exists
   - CI runs both on identical inputs, asserts `|rust_output - python_output| < 1e-9`
   - Parity test failure = CI failure = cannot merge

5. **Benchmark suite** (`tests/benchmark/`)
   - Criterion benchmarks for all hot-path functions
   - Track p50/p95/p99 across commits
   - Alert on >10% regression

---

## Phase 3: Model Training + Signal Generation (Weeks 9-12)

### Week 9: Target Construction + LightGBM Trainer
**Files**: `src/qm/model/targets/{binary,threshold,labeler}.py`, `src/qm/model/trainers/lgbm_trainer.py`

- **Binary target**: `y = 1 if close[t+horizon] >= open[t]` — mirrors Polymarket resolution exactly
- **Threshold target**: `y = 1 if max(high[t:t+window]) >= threshold` — for monthly markets
- LightGBM trainer with Optuna HPO:
  - **Objective function = BacktestEngine.evaluate_model_fast()** — walk-forward evaluation IS the training metric
  - Optimize for Brier score (calibration quality), secondary: Sharpe of simulated PnL
  - HPO search space: n_estimators, learning_rate, max_depth, num_leaves, regularization
  - RTX 4090 + 96GB allows parallel Optuna trials

### Week 10: Probability Calibration
**Files**: `src/qm/model/calibration/{calibrator,isotonic,platt,validator}.py`

- **Expanding window isotonic regression** — fitted on OOS walk-forward predictions only (prevents leakage)
- Online recalibration: accumulate live predictions, refit every 500 bets or when ECE > 0.07
- Validation: ECE, Brier score, Brier decomposition (reliability + resolution + uncertainty), reliability diagrams
- Clip calibrated outputs to [0.01, 0.99] — never output 0 or 1

### Week 11: Ensemble + Model Registry + treelite Compilation
**Files**: `src/qm/model/ensemble/{stacker,blender,diversity}.py`, `src/qm/model/registry.py`, `src/qm/model/compiler.py`

- Stacking ensemble: multiple LightGBM configs as base → logistic regression meta-learner → isotonic calibration
- All fitting via walk-forward (base OOS predictions → meta-learner OOS → final calibration)
- Diversity metrics: correlation between base models, Q-statistic
- Model registry: versioned artifacts (model.txt + calibrator.pkl + config + metrics)
- **treelite compilation step** (`src/qm/model/compiler.py`):
  - After training finishes: `treelite.frontend.load_lightgbm_model(model.txt)` → compile to shared lib
  - Output: `model.so` (Linux) / `model.dll` (Windows) saved alongside model.txt in registry
  - Validation: run 1000 predictions through both LightGBM Python and treelite, assert max absolute diff < 1e-6
  - If compilation fails: log warning, fall back to LightGBM Python predict at runtime. Never block deployment.

### Week 12: Signal Generation
**Files**: `src/qm/model/signals.py`, `src/qm/strategy/edge.py`

- Edge calculation: `effective_edge = (cal_prob - pm_mid) - pm_spread/2`
- Signal filtering: min edge 5 cents, after spread adjustment
- For binary markets: `edge_up = cal_prob - pm_mid_up`, `edge_down = -edge_up` (symmetric)
- Signal includes: timestamp, asset, market_type, model_prob, market_prob, edge, recommended_side

---

## Phase 4: Full Backtest Validation + Paper Trading (Weeks 13-15)

### Week 13: Comprehensive OOS Validation
**Files**: `src/qm/backtest/report.py`, `src/qm/cli/commands/backtest.py`

Run `BacktestEngine.run_full_simulation()` on strictly held-out data. **Acceptance criteria (must pass ALL):**

| Metric | Threshold | Why |
|--------|-----------|-----|
| PBO | < 0.40 | Less than 40% chance strategy is overfit |
| Deflated Sharpe | > 0.0 | Significant after multiple testing correction |
| OOS Brier score | < 0.25 | Better than uninformed prior |
| OOS ECE | < 0.05 | Calibration error under 5pp |
| Net PnL | > 0 after costs | Profitable including Polymarket fees + spread |
| Max drawdown | < 30% bankroll | Survivable worst case |

Also: regime breakdown (performance by vol regime, time-of-day, asset)

### Weeks 14-15: Paper Trading
**Files**: `src/qm/execution/paper/{engine,recorder}.py`, `src/qm/cli/commands/paper.py`

- Full live pipeline with simulated execution — real data, real model, fake fills
- Pessimistic fill assumption: always cross the spread
- **Minimum 2 weeks** before live transition
- Acceptance: PnL within 2 sigma of backtest, calibration holds, no risk limit breaches
- **Fast path validation during paper trading**: run both Rust and Python paths in parallel, compare outputs. Log any divergence. This is the real-world integration test for the fast path before money is on the line.
- **Latency profiling**: measure every hot-path component under real load. Verify p99 < 5ms local compute. Identify any unexpected GC pauses or contention.

---

## Phase 5: Live Execution + Risk Management (Weeks 16-20)

### Week 16: Polymarket Execution Client
**Files**: `src/qm/execution/polymarket/{client,market_scanner,order_manager,position_tracker}.py`

- py-clob-client wrapper with retry, rate limiting, structured logging
  - **[ADDED]** Structured logging MUST redact private keys and API keys. Use a `SecretFilter` log processor that replaces any value matching known secret patterns with `***REDACTED***`
- Market scanner: continuously discovers new 5m/15m crypto markets as they're created
  - **[ADDED]** Time budget: for 5m markets, scanner must discover market at least 3 minutes before window closes to have time for feature computation + signal generation + order placement. Skip markets discovered with <2 minutes remaining
  - **[ADDED]** Liquidity filter: skip markets with total orderbook depth < $500 on either side (not worth the adverse selection risk)
- Order manager: **must maintain heartbeat** (Polymarket cancels orders if heartbeat stops)
  - **[ADDED]** Heartbeat supervisor: separate asyncio task with its own error handling. If heartbeat fails 3x consecutively, trigger circuit breaker and cancel all open orders via REST fallback
- Position tracker: syncs local state against Polymarket API
  - **[ADDED]** On startup: always reconcile local DB state against Polymarket API positions before placing any new orders. Resolve discrepancies by trusting Polymarket API as source of truth
- **[ADDED]** Audit log (`src/qm/execution/audit.py`): Every signal, risk check result, order placed/filled/rejected, and resolution outcome is written to an append-only `audit_log` table in TimescaleDB. Columns: `timestamp, event_type, asset, market_type, signal_id, details_json`. This is the single source of truth for post-mortem analysis. Never delete or update rows.
- **[ADDED]** Polygon blockchain handling:
  - Use reliable RPC endpoint (Alchemy/QuickNode, not public RPCs). Configure fallback RPC
  - Nonce management: track nonce locally, re-fetch from chain if transaction reverts
  - Gas price: use Polygon gas oracle, set max gas price cap (e.g., 500 gwei). Skip trade if gas > expected profit
  - Transaction monitoring: poll for confirmation, timeout after 30s, retry with higher gas if stuck

### Week 17: Risk Management
**Files**: `src/qm/risk/{manager,limits,correlation,bankroll,circuit_breaker}.py`, `src/qm/strategy/sizing/kelly.py`

**Kelly sizing:**
- Fractional Kelly (0.25x) — quarter Kelly for conservative growth with estimation uncertainty
- `kelly_f = edge / (1 - market_price)`, then `bet = kelly_f * fraction * bankroll`
- Caps: max 5% bankroll per bet, max $500 per bet, min $5

**Risk limits:**
- Max 20 concurrent bets
- Max 40% concentration in single asset
- Max 60% correlated directional exposure (BTC-ETH correlation ~0.85)
- Daily loss stop at 10%, circuit breaker at 25% drawdown from HWM
- Circuit breaker also triggers on: data staleness >300s, ECE drift >0.10, 20 consecutive losses

### Week 18: Monitoring + Observability
**Files**: `src/qm/monitoring/*`, Grafana dashboards

- Prometheus metrics: signals, orders, bet sizes, edge observed, PnL, drawdown, accuracy, ECE, Brier, feed latency, data gaps
- Grafana dashboards: trading (PnL/positions/fills), model (calibration/drift/accuracy), data (feed health/latency)
- Structured logging via structlog
- Alerts: model drift, drawdown threshold, feed down

### Week 19: Main Runner + CLI + Integration
**Files**: `src/qm/scheduler/*`, `src/qm/cli/*`

- SystemRunner: orchestrates all subsystems with graceful startup/shutdown
  - **[ADDED]** Graceful shutdown: on SIGTERM/SIGINT, (1) stop placing new orders, (2) wait for pending order confirmations (max 60s), (3) save portfolio state to DB, (4) close websockets, (5) flush logs. On restart, reconcile from saved state + Polymarket API
- CLI modes: `qm ingest`, `qm backfill`, `qm features`, `qm train`, `qm backtest`, `qm paper`, `qm live`
- Scheduled jobs: recalibration (6h), data quality check (30m), model drift check (1h)
  - **[ADDED]** Model retraining: triggered when (a) rolling 7-day ECE > 0.08, OR (b) rolling 7-day accuracy < 48%, OR (c) manually via `qm retrain`. Retraining runs full Phase 3 pipeline, deploys only if new model passes Phase 4 acceptance criteria. Old model stays active until new model is validated

### Week 20: Deployment Pipeline
**Files**: `deploy/qm.service`, `deploy/deploy.sh`, `deploy/Dockerfile`

- **systemd service** (`deploy/qm.service`): auto-restart on failure (max 3 retries in 5min), `Restart=on-failure`, `WatchdogSec=300` (5min health check). Environment file points to `/etc/qm/.env`
- **Deployment script** (`deploy/deploy.sh`): rsync code from Windows (via WSL2 or SSH) to Linux prod → install deps via `uv sync` → run migrations → restart service. Zero-downtime: stop accepting new bets, wait for current window to resolve, swap, restart
- **Rollback**: keep last 3 deployments. Rollback = symlink swap + service restart. Model rollback = point registry to previous version
- **[ADDED] Backup strategy**: TimescaleDB `pg_dump` daily to E: drive (HDD). Model artifacts are versioned in `data/models/` and backed up with the DB dump. Parquet files on NVMe are the ephemeral cache; HDD archive is the durable copy

---

## Tech Stack

| Layer | Tool | Why |
|-------|------|-----|
| Language | Python 3.11+ + Rust | Python for research/strategy, Rust for live hot path |
| Package manager | uv | Fast, cross-platform lockfile, resolves platform-specific wheels |
| Rust build | maturin + PyO3 | Compiles Rust → Python wheel. `#![forbid(unsafe_code)]` |
| Compiled inference | treelite | Compiles LightGBM trees → native C → .so/.dll. <0.5ms predict |
| Data manipulation | Polars | 10-50x faster than Pandas, zero-copy DuckDB integration |
| ML | LightGBM → PyTorch | GBM first (proven on tabular), DL only if justified |
| Time-series DB | TimescaleDB | Production-grade, continuous aggregates, compression |
| Analytics | DuckDB | In-process, zero infra, Parquet predicate pushdown |
| Exchange feeds | ccxt Pro + websockets | Unified API, battle-tested |
| Polymarket | py-clob-client | Official Python SDK |
| Blockchain RPC | Alchemy / QuickNode | Reliable Polygon RPC with fallback |
| Order signing | Rust alloy (via qm-fast) | EIP-712 signing in <1ms vs Python's ~30ms |
| HPO | Optuna | TPE sampler, pruning, parallel trials |
| Config | Hydra | Hierarchical config, experiment overrides |
| Secrets | keyring + python-dotenv | [ADDED] OS keyring for prod, .env for dev |
| Scheduling | APScheduler | In-process cron |
| Monitoring | Prometheus + Grafana | Industry standard |
| Logging | structlog | Structured, JSON output |
| Testing | pytest + pytest-asyncio | [ADDED] Async test support for WS connectors |
| Deployment | systemd + rsync | [ADDED] Simple, reliable, easy rollback |

---

## Production Inference: Fastest Possible, Never Breaks

**Design principle**: Every millisecond counts AND a crash mid-trade costs more than any latency gain. The architecture uses a **dual-path design**: Rust fast path for speed, Python fallback for reliability. If the fast path fails, the system seamlessly degrades to the Python path — never skips a trade, never enters an inconsistent state.

### Two Separate Code Paths

```
┌─────────────────────────────────────────────────────────────┐
│                   RESEARCH PATH (Python)                     │
│  Training, backtesting, feature exploration, notebooks       │
│  Priority: accuracy, flexibility, debuggability              │
│  Speed: acceptable (seconds per prediction is fine)          │
│  Stack: Polars, DuckDB, LightGBM Python API, scikit-learn   │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│               LIVE FAST PATH (Rust + compiled)               │
│  Production inference, signal generation, order execution    │
│  Priority: speed first, reliability always                   │
│  Speed: <5ms local compute (bar→signal), <300ms to order     │
│  Stack: qm-fast (Rust/PyO3), treelite, pre-allocated bufs   │
│                                                              │
│  ┌─────────────────────────────────────────────────────┐    │
│  │          PYTHON FALLBACK (automatic)                 │    │
│  │  If Rust path panics or returns error,               │    │
│  │  Python path runs same logic in ~25ms.               │    │
│  │  Latency penalty: ~20ms. Trade still happens.        │    │
│  └─────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────┘
```

### Rust Extension: `qm-fast` (`crates/qm-fast/`)

Built with **maturin + PyO3**. Compiled to a Python wheel, imported as `import qm_fast`.

**What goes in Rust (and why):**

| Component | Why Rust | Python fallback |
|-----------|----------|-----------------|
| Rolling feature engine | Incremental O(1) updates per bar. Pre-allocated ring buffers. No GC pauses, no DataFrame overhead. | Polars computation (~50-200ms) |
| Orderbook manager | Maintain real-time L2 books for 4 assets. Apply WS deltas in <1us. Instant price-impact calc. | Python dict-based book (~5ms) |
| EIP-712 order signer | Python `eth_account` is ~20-50ms. Rust `alloy` does it in <1ms. | Python eth_account (~30ms) |
| Feature buf → numpy | Zero-copy from Rust ring buffer to numpy array via PyO3. No serialization. | Polars .to_numpy() (~2ms) |

**What stays in Python (and why):**

| Component | Why Python | Speed impact |
|-----------|-----------|--------------|
| Model inference | treelite/LightGBM are already C/C++. Python is just the call wrapper. | ~0ms overhead |
| Calibration | Isotonic regression = binary search on small array. | <0.1ms |
| Risk checks | Simple comparisons and arithmetic. Not worth FFI overhead. | <0.1ms |
| Strategy logic | Must be readable, auditable, frequently changed. Rust recompile would slow iteration. | <0.1ms |
| Monitoring/logging | I/O-bound, async. Language irrelevant. | 0ms (async, non-blocking) |
| All training/backtest | Accuracy and flexibility matter more than speed here. | N/A |

### Compiled Model Inference: treelite

LightGBM's Python `predict()` has overhead (~3-5ms) from data marshaling. **treelite** compiles the trained tree ensemble to optimized C code, then to a shared library:

```
Training (Python):  LightGBM.fit() → model.txt
Compilation:        treelite.compile(model.txt) → model.so (Linux) / model.dll (Windows)
Live inference:     treelite.predict(features_array) → 0.3-0.5ms
```

- Compiled once after training, loaded at startup, stays in memory
- Cross-platform: .so on Linux prod, .dll on Windows dev
- Battle-tested at multiple quant firms
- **Fallback**: if treelite model fails to load, fall back to LightGBM Python predict (~3-5ms). Trade still happens.

### Latency Budget (Live Fast Path)

```
Event: bar completes at T=0
───────────────────────────────────────────────────────────
T+0.0ms   Rust rolling features already updated (incremental on each trade)
T+0.1ms   Feature buffer → numpy array (zero-copy via PyO3)
T+0.5ms   treelite inference (compiled C tree model)
T+0.6ms   Isotonic calibration lookup (binary search, Python)
T+0.7ms   Edge calc + risk checks (Python arithmetic)
T+1.0ms   Rust EIP-712 order signing
T+1.5ms   ─── LOCAL COMPUTE DONE ─── (~1.5ms fast path)
T+2.0ms   HTTP POST to Polymarket CLOB (pre-warmed persistent connection)
T+200ms   Order acknowledged by CLOB
T+2000ms  Polygon tx confirmed
───────────────────────────────────────────────────────────
          Fast path local:     ~1.5ms
          Python fallback:     ~25ms
          Network (irreducible): ~200-2000ms
```

### Reliability Guarantees (Non-Negotiable)

**Rule: "no trade" beats "bad trade", "slow trade" beats "no trade".**

1. **Every Rust FFI call wrapped with automatic Python fallback**
   ```python
   def compute_features(self, asset: Asset) -> np.ndarray:
       try:
           return qm_fast.get_features(asset.value)  # ~0.1ms
       except Exception as e:
           logger.warning("fast_path_fallback", component="features", error=str(e))
           FAST_PATH_FALLBACK.labels(component="features").inc()
           return self._python_fallback.compute(asset)  # ~100ms, still works
   ```

2. **Rust module: `#![forbid(unsafe_code)]`** — all memory-safe. No undefined behavior risk. PyO3 handles all FFI boundary safety.

3. **State is always reconstructable** — Rust feature engine state can be rebuilt from last N bars in TimescaleDB. On crash → restart: load last 100 bars → replay through engine → state restored in <1s. No data loss.

4. **Startup health check** — known-input/known-output test on Rust module before accepting any trades. Fail → start in Python-only mode + alert operator.

5. **Audit writes are async** — append-only audit log writes happen AFTER order submission, never blocking the hot path. If audit write fails, order is already placed — audit catches up on retry.

6. **Fallback monitoring** — Prometheus counter tracks Python fallback invocations. If >5 fallbacks in 1 hour → circuit breaker halts trading + alerts. Indicates Rust module instability that needs investigation.

7. **CI correctness guarantee** — test suite runs both Rust and Python paths on identical inputs, asserts outputs match within float tolerance (1e-9). If they diverge, CI fails. You can never ship a Rust module that disagrees with the Python reference.

### Project Structure Addition: `crates/`

```
crates/
└── qm-fast/
    ├── Cargo.toml                  # Rust dependencies: pyo3, alloy, etc.
    ├── pyproject.toml              # maturin build config
    ├── src/
    │   ├── lib.rs                  # PyO3 module entry, #![forbid(unsafe_code)]
    │   ├── features/
    │   │   ├── mod.rs
    │   │   ├── ring_buffer.rs      # Pre-allocated ring buffer for bar history
    │   │   ├── rolling.rs          # Incremental feature computations
    │   │   └── export.rs           # Zero-copy numpy export
    │   ├── orderbook/
    │   │   ├── mod.rs
    │   │   ├── l2_book.rs          # L2 orderbook with delta application
    │   │   └── impact.rs           # Price impact / slippage calculator
    │   └── signing/
    │       ├── mod.rs
    │       └── eip712.rs           # Polymarket order signing via alloy
    └── tests/
        ├── test_features.rs        # Rust-side unit tests
        └── test_signing.rs
```

### Benchmarking Infrastructure

**You cannot optimize what you cannot measure.**

- `src/qm/monitoring/latency.py` — wraps every hot-path step with `time.perf_counter_ns()`, pushes to Prometheus histogram
- Per-component histograms: `feature_compute_ns`, `model_inference_ns`, `calibration_ns`, `risk_check_ns`, `order_sign_ns`, `api_submit_ns`
- CI benchmark suite (`tests/benchmark/`): runs hot path 10,000 iterations, reports p50/p95/p99/max. CI **fails if p99 regresses >20%** vs committed baseline
- Grafana latency dashboard: real-time percentile tracking per component
- Weekly automated latency report: identifies regressions before they compound

---

## Key Architectural Decisions

1. **Build OHLCV from raw trades** — exchange bars have subtle alignment/aggregation issues
2. **Polars over Pandas** — 5-30x faster for our feature computation volumes
3. **DuckDB as feature store** — simpler than Feast for single-machine, in-process analytics
4. **LightGBM first** — beats DL on tabular data, trains in seconds, interpretable
5. **Isotonic calibration** — handles non-sigmoid miscalibration in GBM outputs
6. **Dual-mode backtest engine** — fast vectorized for HPO, realistic event-driven for validation
7. **0.25x Kelly** — quarter Kelly balances growth vs drawdown with estimation uncertainty
8. **CPCV + walk-forward** — WF for training speed, CPCV for statistical rigor in validation
9. **Hydra env overlays** — `conf/env/dev.yaml` vs `conf/env/prod.yaml` for clean separation of Windows dev and Linux prod configs
10. **Append-only audit log** — every trading decision is immutably recorded for regulatory and debugging purposes
11. **uv for dependency management** — cross-platform lockfile resolves the Windows-vs-Linux binary wheel problem
12. **Dual-path: Rust fast + Python fallback** — every Rust call auto-degrades to Python on failure. 1.5ms fast path, 25ms fallback. Trade always happens.
13. **treelite compiled inference** — LightGBM tree ensemble compiled to native C code. 0.3-0.5ms vs 3-5ms Python API. No runtime dependency on LightGBM in prod.
14. **`#![forbid(unsafe_code)]` in Rust** — speed without memory safety risk. All unsafe operations handled by PyO3 boundary.
15. **CI parity tests** — Rust and Python paths must produce identical outputs on identical inputs. Divergence = CI failure. No silent correctness drift.

---

## [ADDED] Testing Strategy

### Framework: pytest + pytest-asyncio
- **Unit tests** (`tests/unit/`): Pure logic — bar builder, feature computation, Kelly sizing, CPCV splits, calibration math. No external dependencies. Target: 90%+ coverage on core logic.
- **Integration tests** (`tests/integration/`): Require Docker (TimescaleDB). Use `pytest-docker` fixtures to spin up/teardown. Test: data pipeline end-to-end, feature store read/write, model registry save/load.
- **Exchange mocking**: Use `aioresponses` + recorded WS fixtures (saved JSON) for ccxt connector tests. Never hit real exchange APIs in CI.
- **Polymarket mocking**: Record real API responses to JSON fixtures. Test order flow, market discovery, resolution handling against fixtures.
- **Backtest smoke tests** (`tests/backtest/`): Run small-data backtests to verify metrics computation. Verify random strategy produces ~0 Sharpe. Verify known-signal strategy produces expected PnL.
- **Cross-platform CI**: Run `pytest` on both Windows (native) and WSL2 (Linux). Use GitHub Actions matrix or local `make test-all`.

---

## Verification Plan

### Per-Phase Testing
1. **Phase 1**: Run `qm ingest` for 1 hour, verify bars in TimescaleDB match exchange REST data. Verify DST-edge timestamps. Verify gap detection fires on simulated disconnect.
2. **Phase 2**: Compute features on synthetic data, verify no NaN leakage; run backtest on random strategy, verify metrics are ~0 Sharpe. Verify CPCV produces expected number of splits.
3. **Phase 3**: Train model, verify OOS accuracy > random (50%); verify calibration curve is close to diagonal. Verify Optuna uses backtest engine as objective.
4. **Phase 4**: Run full backtest, verify all acceptance criteria; paper trade 2 weeks. Verify paper PnL tracking matches manual calculation.
5. **Phase 5**: Run live with min bet size ($5), verify fill reconciliation matches Polymarket API. Verify circuit breaker triggers on simulated conditions. **[ADDED]** Verify graceful shutdown preserves state and restart reconciles correctly.

### End-to-End Smoke Test
```bash
# 1. Start infra
docker compose up -d  # [ADDED] modern docker compose (no hyphen)

# 2. Backfill 3 months of data
python -m qm backfill --assets BTC,ETH --timeframes 5m,15m --months 3

# 3. Compute features
python -m qm features --assets BTC,ETH --timeframes 5m

# 4. Train model
python -m qm train --config conf/model/lightgbm.yaml --n-trials 50

# 5. Run backtest
python -m qm backtest --model latest --start 2026-01-01 --end 2026-03-01

# 6. Paper trade
python -m qm paper --model latest --duration 14d

# 7. Go live (min size)
python -m qm live --model latest --max-bet-usd 5
```

### [ADDED] Incident Response
When circuit breaker trips:
1. System automatically: stops new orders, cancels open orders, logs full state snapshot
2. Alert sent via configured channel (Slack webhook / email)
3. Operator investigates: check Grafana dashboards (model drift? data gap? market regime shift?)
4. Resolution: either (a) reset circuit breaker via `qm reset-circuit-breaker` after root cause fixed, or (b) trigger model retraining via `qm retrain`
5. Post-mortem: log the incident, update risk parameters if needed
