# Phases 4-5 Implementation Plan (Revised)

## Context

Phases 1-3 are committed (`bca4dd1`): 4,387 lines of production code, 98 tests passing. Data infrastructure, feature engineering, backtesting engine, model training, calibration, and signal generation are complete.

**What remains:** Risk management, paper trading, live Polymarket execution, monitoring, scheduling, deployment, Rust fast path, and CLI commands. ~2,500-3,000 lines of new code.

**Key revision from review:** Monitoring/logging moved to Step 1 (wire in from day one). Paper and live engines share a single `TradingLoop` with pluggable executor (no duplication). Backtest report + acceptance gates added explicitly. Rust fast path acknowledged as post-paper-trading optimization.

---

## Build Order (revised, 9 steps)

```
Step 0: DATA DOWNLOAD (PARALLEL)   ← start immediately, runs in background while coding
Step 1: Monitoring + Logging       ← wire in first, never debug blind
Step 2: Risk Management            ← foundation for all execution
Step 3: Strategy + Portfolio       ← edge calc, filtering, portfolio state, audit
Step 4: Trading Loop + Paper       ← single loop, paper executor, backtest report
Step 5: Polymarket Execution       ← live executor, market scanner, order manager
Step 6: Scheduler + Runner + CLI   ← orchestration, startup/shutdown, commands
Step 7: Rust Fast Path             ← performance optimization (paper validates it)
Step 8: Deployment                 ← systemd, deploy script, Dockerfile
```

---

## Step 0: Bulk Data Download from Binance Vision (runs in background while we code)

**Why first:** Historical data for backtesting takes time. Start immediately, code against it in parallel.

**Why Binance Vision instead of ccxt REST:**
- Static file hosting — no API rate limits, can download in parallel
- Complete daily archives: one ZIP/CSV per day per symbol/timeframe
- Futures USDT-M data — better liquidity, tighter spreads, includes quote volume + taker data
- Speed: entire month downloads in seconds vs hours of paginated REST

**Source URL pattern:**
```
https://data.binance.vision/data/futures/um/daily/klines/{SYMBOL}/{INTERVAL}/{SYMBOL}-{INTERVAL}-{DATE}.zip
```
Example: `https://data.binance.vision/data/futures/um/daily/klines/BTCUSDT/5m/BTCUSDT-5m-2026-03-17.zip`

Also available as monthly archives (faster for bulk):
```
https://data.binance.vision/data/futures/um/monthly/klines/{SYMBOL}/{INTERVAL}/{SYMBOL}-{INTERVAL}-{YYYY-MM}.zip
```

**What to download:**
| Symbol | Timeframes | Type | History |
|--------|-----------|------|---------|
| BTCUSDT | 5m, 15m, 1h | Futures USDT-M | From 2019-09 (futures launch) |
| ETHUSDT | 5m, 15m, 1h | Futures USDT-M | From 2019-09 |
| SOLUSDT | 5m, 15m, 1h | Futures USDT-M | From 2020-09 (SOL futures launch) |
| XRPUSDT | 5m, 15m, 1h | Futures USDT-M | From 2020-01 |

**Raw CSV columns (12 fields per Binance Vision klines):**
```
open_time, open, high, low, close, volume, close_time,
quote_volume, trade_count, taker_buy_volume, taker_buy_quote_volume, ignore
```

**Data volume estimate:**
- 5m bars: ~105k/year × 6 years × 4 symbols = ~2.5M bars
- 15m + 1h: ~250k additional
- Total: ~2.8M bars → ~500MB Parquet (Snappy compressed)
- Raw ZIPs: ~2-3GB (downloaded then deleted after processing)

**Files to create:**
- `src/qm/data/historical/binance_vision.py` — Binance Vision bulk downloader
- `scripts/download_historical.py` — CLI script to run the download

**`binance_vision.py` design (adapted from crypto-watcher `BaseCollector` + `KlinesCollector`):**

```python
class BinanceVisionDownloader:
    """Download bulk historical klines from data.binance.vision.

    Downloads monthly ZIPs for older data, daily ZIPs for recent data.
    Extracts CSV, validates, converts to Polars DataFrame, saves as Parquet.
    """

    BASE_URL = "https://data.binance.vision/data/futures/um"

    async def download_symbol(self, symbol, timeframe, start_date, end_date):
        """Download all data for one symbol/timeframe combo."""
        # 1. Use monthly archives for complete months (much faster)
        # 2. Use daily archives for partial current month
        # 3. Skip already-downloaded date partitions (idempotent)

    async def _download_monthly(self, symbol, timeframe, year_month) -> Path:
        """Download monthly ZIP, return local path."""
        url = f"{self.BASE_URL}/monthly/klines/{symbol}/{timeframe}/{symbol}-{timeframe}-{year_month}.zip"
        # aiohttp GET → save to temp dir → return path

    async def _download_daily(self, symbol, timeframe, date) -> Path:
        """Download daily ZIP for recent/partial months."""
        url = f"{self.BASE_URL}/daily/klines/{symbol}/{timeframe}/{symbol}-{timeframe}-{date}.zip"

    def _extract_and_parse(self, zip_path) -> pl.DataFrame:
        """Extract CSV from ZIP, parse to Polars DataFrame."""
        # ZIP contains single CSV file
        # Parse 12 columns, rename to our schema
        # Validate: high >= low, open/close between low-high
        # Convert open_time from ms epoch to datetime

    def _save_to_parquet(self, df, symbol, timeframe):
        """Save to Hive-partitioned Parquet via existing ParquetStore."""
```

**Data validation (adapted from crypto-watcher `DataProcessor`):**
1. Duplicate removal by timestamp
2. OHLC relationship checks: high >= low, open/close within [low, high]
3. Volume >= 0, trade_count >= 0
4. Monotonic timestamps
5. Gap detection after full download
6. Completeness score per symbol/timeframe

**Improvements over crypto-watcher approach:**
- Use `aiohttp` for parallel downloads (download multiple months concurrently, 4 at a time)
- Use Polars instead of Pandas for parsing (5-10x faster CSV parsing)
- Store in our existing Hive-partitioned Parquet format (compatible with existing `ParquetStore`)
- No ClickHouse dependency — Parquet + DuckDB is simpler and sufficient
- Checksum verification: Binance Vision provides `.zip.CHECKSUM` files — verify integrity

**Download strategy:**
1. Try monthly archives first (1 file per month vs 28-31 daily files)
2. For current incomplete month: fall back to daily archives
3. If monthly archive 404s (too recent): fall back to daily
4. Parallel: download up to 4 months concurrently per symbol
5. Sequential across symbols (to be a good citizen)

**Execution:**
1. Write the downloader module and script
2. Start download in background terminal: `python scripts/download_historical.py`
3. Expected time: 15-30 minutes (parallel monthly downloads, not hours of REST)
4. Continue coding Steps 1-8 while download runs

**Storage layout (matches existing ParquetStore):**
```
data/raw/ohlcv/
├── asset=BTC/
│   ├── timeframe=5m/
│   │   ├── date=2024-01-15/data.parquet
│   │   ├── date=2024-01-16/data.parquet
│   │   └── ...
│   ├── timeframe=15m/
│   └── timeframe=1h/
├── asset=ETH/
├── asset=SOL/
└── asset=XRP/
```

**Post-download validation script:**
```bash
python scripts/validate_data.py --assets BTC,ETH,SOL,XRP --timeframes 5m,15m,1h
# Output: completeness scores, gap counts, date ranges per symbol
```

### Data Reconciliation (non-negotiable for production quant)

**Why this matters:** If the data is wrong, the model is wrong, and you lose money. Binance Vision archives are generally reliable but not infallible — corrupt ZIPs, missing days during maintenance, exchange API outages that produced bad candles, timezone misalignment. One bad day of training data can silently bias the model.

**File to create:** `src/qm/data/quality/reconciler.py`

**5 layers of reconciliation:**

**Layer 1: ZIP integrity**
- Every Binance Vision ZIP has a companion `.CHECKSUM` file (SHA256)
- Download checksum, verify before extracting
- On mismatch: re-download once, then flag as corrupt and skip the day

**Layer 2: Internal consistency (per-bar)**
- `high >= low` (always)
- `high >= max(open, close)` and `low <= min(open, close)`
- `volume >= 0`, `quote_volume >= 0`, `trade_count >= 0`
- `open_time < close_time` and `close_time - open_time == timeframe`
- Flag violations, don't silently drop — log them and count per day

**Layer 3: Cross-timeframe reconciliation**
- 5m bars should aggregate to match 15m bars:
  - `15m_open == first_5m_open_in_window`
  - `15m_high == max(three 5m highs)`
  - `15m_low == min(three 5m lows)`
  - `15m_close == last_5m_close_in_window`
  - `15m_volume ≈ sum(three 5m volumes)` (within 0.1% tolerance for rounding)
- Same logic: 15m → 1h (four 15m bars)
- **This catches timezone alignment bugs** — if our 15m bars are shifted by 1 minute relative to Binance's, the cross-timeframe check will fail

**Layer 4: Temporal continuity**
- No missing bars (gap detection via existing `gap_detector.py`)
- No duplicate timestamps
- Timestamps strictly monotonic increasing
- Expected bar count per day: 5m=288, 15m=96, 1h=24
- Missing bars during exchange maintenance: flag and record, but don't fail
  - Binance has ~2-4 maintenance windows per year, typically 30-60 min
  - These gaps are real, not data errors — mark them in a `known_gaps` table

**Layer 5: Cross-source spot check (optional, live validation)**
- For the most recent 7 days: compare Binance Vision data against live ccxt `fetch_ohlcv()` REST
- Should match exactly (Binance Vision is derived from the same source)
- Any divergence > 0.01% on close price → flag the entire day for investigation
- This catches: Binance Vision publishing errors, our parsing bugs, timezone issues

**Reconciliation output:**
```python
@dataclass
class ReconciliationReport:
    symbol: str
    timeframe: str
    date_range: tuple[str, str]      # "2020-01-01" to "2026-03-18"
    total_bars: int
    expected_bars: int
    completeness: float              # 0.0 - 1.0
    gaps: list[Gap]                  # missing bar timestamps
    known_maintenance_gaps: int      # expected gaps (exchange maintenance)
    integrity_violations: int        # OHLC relationship failures
    cross_tf_mismatches: int         # 5m→15m→1h aggregation failures
    cross_source_divergences: int    # vs live REST (if checked)
    status: str                      # "PASS", "WARN", "FAIL"
```

**Acceptance criteria for data quality:**
| Check | Threshold | Action if failed |
|-------|-----------|-----------------|
| Completeness | > 99.5% | WARN if 99-99.5%, FAIL if <99% |
| Integrity violations | 0 | FAIL — bad bars must be removed |
| Cross-TF mismatches | 0 | FAIL — alignment bug |
| Cross-source divergence | < 0.01% | WARN, investigate |
| Checksum failures | 0 after retry | FAIL — re-download day |

**When to run reconciliation:**
1. After initial bulk download (full reconciliation)
2. After each daily incremental update (Layer 1-4 on new day only)
3. Weekly: full cross-source spot check on last 7 days
4. Before any model training: verify data quality of training date range

---

## Step 1: Monitoring + Logging

**Why first:** Every subsequent step instruments itself against these. Without this, risk checks, paper trades, and execution happen without visibility.

**Files to create:**
- `src/qm/monitoring/metrics.py` — Prometheus counters, gauges, histograms
- `src/qm/monitoring/logging.py` — structlog config with secret redaction
- `src/qm/monitoring/alerting.py` — Alert dispatch (Slack webhook)

**`metrics.py` — all Prometheus metrics in one place:**
```python
# Trading
SIGNALS_GENERATED = Counter('qm_signals_total', 'Signals generated', ['asset', 'market_type', 'side'])
ORDERS_PLACED = Counter('qm_orders_placed_total', 'Orders placed', ['asset', 'outcome'])
ORDERS_REJECTED = Counter('qm_orders_rejected_total', 'Orders rejected by risk', ['asset', 'reason'])
BET_SIZE_USD = Histogram('qm_bet_size_usd', 'Bet sizes', buckets=[5, 10, 25, 50, 100, 200, 500])
EDGE_OBSERVED = Histogram('qm_edge_observed', 'Edge at signal time', buckets=[0.01, 0.02, 0.05, 0.10, 0.20])
PNL_TOTAL = Gauge('qm_pnl_total_usd', 'Total cumulative PnL')
PNL_DAILY = Gauge('qm_pnl_daily_usd', 'Today PnL')
DRAWDOWN_PCT = Gauge('qm_drawdown_pct', 'Drawdown from HWM')
BANKROLL = Gauge('qm_bankroll_usd', 'Current bankroll')

# Model
MODEL_ACCURACY = Gauge('qm_model_accuracy', 'Rolling accuracy', ['asset', 'window'])
CALIBRATION_ECE = Gauge('qm_calibration_ece', 'Expected calibration error', ['asset'])
BRIER_SCORE = Gauge('qm_brier_score', 'Rolling Brier score', ['asset'])

# Data
FEED_LATENCY = Histogram('qm_feed_latency_ms', 'Feed latency', ['exchange', 'asset'],
                         buckets=[10, 50, 100, 250, 500, 1000, 5000])
FEED_HEALTH = Gauge('qm_feed_healthy', 'Feed status', ['exchange'])
DATA_GAPS = Counter('qm_data_gaps_total', 'Missing bars', ['asset', 'timeframe'])

# Performance
FAST_PATH_FALLBACK = Counter('qm_fast_path_fallback_total', 'Python fallbacks', ['component'])
INFERENCE_LATENCY_NS = Histogram('qm_inference_latency_ns', 'Inference time',
                                  buckets=[500_000, 1_000_000, 2_000_000, 5_000_000, 10_000_000])
```

**`logging.py` — structlog with secret redaction:**
- `SecretFilter` processor: replaces values matching `(?i)(key|secret|password|token|private).*[=:]\s*\S+` with `***REDACTED***`
- Dev: `ConsoleRenderer` (human-readable)
- Prod: `JSONRenderer` (machine-parseable)
- Bound context: `env`, `hostname`, `pid`

**`alerting.py`:**
- `async def send_alert(severity, title, message)` — dispatches to Slack webhook
- Circuit breaker trip → CRITICAL alert
- Drawdown > 15% → WARNING
- Feed down > 5 min → WARNING
- ECE drift > 0.08 → WARNING
- Idempotent: deduplicates alerts within a 5-minute window (same title → skip)

**Tests:** `tests/unit/monitoring/test_logging.py` (verify secret redaction)

---

## Step 2: Risk Management

**Files to create:**
- `src/qm/risk/manager.py` — Central risk manager: pre-trade + post-trade
- `src/qm/risk/limits.py` — Individual limit checks
- `src/qm/risk/correlation.py` — Cross-asset correlation monitoring
- `src/qm/risk/bankroll.py` — Bankroll tracking, high-water mark, daily PnL reset
- `src/qm/risk/circuit_breaker.py` — Emergency shutdown with manual reset

**Key design:**

`RiskManager.__init__(portfolio, config, event_bus)` — receives shared `Portfolio` instance, not global state.

`RiskManager.pre_trade_check(signal, size) → (bool, reason)`:
- Chain: circuit_breaker → concurrent_limit → single_bet_size → daily_loss → drawdown → asset_concentration → correlated_exposure
- Circuit breaker checked FIRST (if tripped, instant reject without running other checks)
- Every rejection increments `ORDERS_REJECTED` Prometheus counter with reason label

`CircuitBreaker` triggers:
| Condition | Threshold | Action |
|-----------|-----------|--------|
| Drawdown from HWM | > 30% | Trip |
| Daily loss | > 15% | Trip |
| Data staleness | > 300s | Trip |
| ECE drift | > 0.10 | Trip |
| Consecutive losses | > 20 | Trip |

- Tripped state persisted to DB (`audit_log` with event_type='circuit_breaker_trip')
- Manual reset: `qm reset-circuit-breaker` checks DB, clears flag
- On trip: publishes `CircuitBreakerTrip` event → alerting sends Slack

`Bankroll`:
- Tracks `initial_bankroll`, `current_bankroll`, `high_water_mark`, `daily_pnl`
- `daily_pnl` resets at midnight ET (Polymarket's reference timezone)
- [ADDED] `save_state(writer)` / `load_state(writer)` — persist to `audit_log` table for crash recovery
- HWM only updated upward (never decreases)

**Config:** `conf/execution/risk.yaml` (as in original plan)

**Asset correlations:** Hardcoded initially, loaded from config. Updated dynamically in future.
```python
ASSET_CORRELATIONS = {
    (Asset.BTC, Asset.ETH): 0.85,
    (Asset.BTC, Asset.SOL): 0.75,
    (Asset.BTC, Asset.XRP): 0.65,
    (Asset.ETH, Asset.SOL): 0.80,
    (Asset.ETH, Asset.XRP): 0.60,
    (Asset.SOL, Asset.XRP): 0.55,
}
```

**Tests:** `tests/unit/risk/test_limits.py`, `tests/unit/risk/test_circuit_breaker.py`, `tests/unit/risk/test_bankroll.py`

---

## Step 3: Strategy + Portfolio + Audit

**Files to create:**
- `src/qm/strategy/edge.py` — Edge calculation with cost adjustment
- `src/qm/strategy/filter.py` — Trade filter chain
- `src/qm/strategy/portfolio.py` — Portfolio state: positions, cash, PnL
- `src/qm/execution/audit.py` — Append-only audit log writer

**`Portfolio`:**
- Tracks: `open_positions: list[Position]`, `available_cash`, `total_value`, `realized_pnl`
- `Position` dataclass: `signal_id, asset, side, entry_price, size_usd, entry_time, market_condition_id`
- `on_fill(signal, size, fill_price)` — adds position, deducts cash
- `on_resolution(condition_id, outcome)` — resolves position, computes PnL, updates cash
- [ADDED] `to_dict() / from_dict()` — serializable for crash recovery via audit log
- Updated by both paper and live executors (single instance, no duplication)

**`EdgeCalculator`:**
- `compute(model_prob, market_prob, spread) → (edge, side)` — stateless, pure function
- Already partially in `SignalGenerator` — extract and reuse, no duplication

**`TradeFilter`:**
- `filter(signal, portfolio, market) → (bool, reason)` — chain of checks:
  1. Min edge (from risk config)
  2. Time budget: skip if <2 min until window close
  3. Liquidity: skip if orderbook depth < $500
  4. Risk manager pre-trade check (delegates to Step 2)

**`AuditWriter`:**
- Wraps `TimescaleWriter.write_audit()` (already exists)
- Methods: `log_signal()`, `log_risk_check()`, `log_order()`, `log_fill()`, `log_resolution()`, `log_state_snapshot()`
- All async, non-blocking
- [ADDED] `log_state_snapshot(portfolio)` — called on shutdown and periodically (every 5 min) for crash recovery

**Reuses:**
- `KellySizer` from `src/qm/strategy/sizing/kelly.py`
- `Signal`, `PolymarketMarket` from `src/qm/core/types.py`
- `TimescaleWriter` from `src/qm/data/storage/timescale.py`

**Tests:** `tests/unit/strategy/test_portfolio.py`, `tests/unit/strategy/test_filter.py`

---

## Step 4: Trading Loop + Paper Engine + Backtest Report

**Files to create:**
- `src/qm/execution/loop.py` — [ADDED] Single trading loop, shared by paper and live
- `src/qm/execution/paper/engine.py` — Paper executor (simulated fills)
- `src/qm/execution/paper/recorder.py` — Paper trade recording + analysis
- `src/qm/backtest/report.py` — [ADDED] Backtest report generation + acceptance gates

**[ADDED] `TradingLoop` — single decision loop, two executors:**
```python
class TradingLoop:
    """Core decision loop shared by paper and live execution.

    Eliminates duplication between paper and live paths.
    The executor is pluggable: PaperExecutor or LiveExecutor.
    """
    def __init__(self, signal_generator, risk_manager, sizer,
                 portfolio, executor, audit_writer, event_bus): ...

    async def on_bar_completed(self, event: BarCompleted):
        # 1. Generate signal
        signal = self.signal_generator.generate(...)
        if signal is None: return
        self.audit_writer.log_signal(signal)

        # 2. Size the bet
        size = self.sizer.size(signal.edge, market_price, portfolio.available_cash)
        if size == 0: return

        # 3. Risk check
        ok, reason = self.risk_manager.pre_trade_check(signal, size)
        self.audit_writer.log_risk_check(signal, ok, reason)
        if not ok: return

        # 4. Execute (paper or live — polymorphic)
        fill = await self.executor.execute(signal, size)
        self.audit_writer.log_fill(fill)
        self.portfolio.on_fill(signal, size, fill.price)

    async def on_market_resolution(self, condition_id, outcome):
        self.portfolio.on_resolution(condition_id, outcome)
        self.audit_writer.log_resolution(...)
```

**`PaperExecutor`:**
- `execute(signal, size) → Fill` — simulates fill at `market_price + spread/2` (pessimistic)
- No network calls, instant return
- Records all fills for analysis

**[ADDED] `BacktestReport`:**
- `generate(backtest_result) → dict` — computes all acceptance criteria
- `check_acceptance(metrics) → (bool, list[str])` — returns pass/fail + list of failed criteria
- Acceptance criteria from plan: PBO < 0.40, deflated Sharpe > 0.0, Brier < 0.25, ECE < 0.05, PnL > 0, max DD < 30%
- Outputs HTML report to `data/reports/`

**[ADDED] Parallel fast-path validation:**
- During paper trading, if Rust module available: run Python path alongside, compare outputs
- Log divergence as WARNING, increment `FAST_PATH_FALLBACK` if Rust disagrees
- This happens in Step 7 when Rust is built — paper engine has a hook for it

**Tests:** `tests/unit/execution/test_trading_loop.py`, `tests/unit/execution/test_paper_engine.py`

---

## Step 5: Polymarket Live Execution

**Files to create:**
- `src/qm/execution/polymarket/client.py` — py-clob-client wrapper
- `src/qm/execution/polymarket/market_scanner.py` — Discover active markets
- `src/qm/execution/polymarket/order_manager.py` — Order lifecycle + heartbeat
- `src/qm/execution/polymarket/position_tracker.py` — Position sync
- `src/qm/execution/polymarket/live_executor.py` — [ADDED] `LiveExecutor` implementing same interface as `PaperExecutor`
- `src/qm/execution/reconciliation.py` — Startup reconciliation

**`LiveExecutor`:**
- Same interface as `PaperExecutor`: `execute(signal, size) → Fill`
- Calls `PolymarketClient.place_limit_order()` → waits for fill confirmation
- On failure: returns `Fill(status='rejected')`, logs to audit, increments metric

**`PolymarketClient`:**
- Wraps `py-clob-client` with retry (3x, exponential backoff), rate limiting
- [ADDED] All methods wrapped in `try/except` with structured logging
- Secret redaction via `SecretFilter` from monitoring/logging.py
- Methods: `place_limit_order()`, `cancel_order()`, `get_positions()`, `get_active_markets()`

**`MarketScanner`:**
- Polls Gamma API every 15s
- Filters: target assets, target market types, time budget (>2 min remaining), liquidity (>$500 depth)
- In-memory cache of active markets (avoids API call at decision time)
- [ADDED] Emits `MarketDiscovered` event for the trading loop to subscribe to

**`OrderManager`:**
- Heartbeat supervisor: separate asyncio task, 10s interval
- Heartbeat fail 3x → circuit breaker + cancel all via REST fallback
- Order timeout: cancel unfilled after 60s
- [ADDED] Tracks all open order IDs for reconciliation

**`PositionTracker`:**
- On startup: calls `get_positions()`, compares to local `Portfolio`
- Discrepancies: trust Polymarket API, adjust local state, log WARNING
- Monitors market resolutions via websocket or polling

**Blockchain handling:**
- RPC from config (POLYGON_RPC_URL + fallback)
- Nonce: local tracking, re-fetch from chain on revert
- Gas cap: skip trade if gas > expected profit
- Tx monitoring: poll confirmation, 30s timeout, retry +20% gas if stuck

**Tests:** `tests/unit/execution/test_market_scanner.py` (mocked API), `tests/unit/execution/test_live_executor.py` (mocked client)

---

## Step 6: Scheduler + Runner + CLI

**Files to create:**
- `src/qm/scheduler/runner.py` — Main system orchestrator
- `src/qm/scheduler/jobs.py` — Periodic jobs
- `src/qm/scheduler/lifecycle.py` — Startup/shutdown coordination
- `src/qm/cli/commands/ingest.py`
- `src/qm/cli/commands/backfill.py`
- `src/qm/cli/commands/features.py`
- `src/qm/cli/commands/train.py`
- `src/qm/cli/commands/backtest.py`
- `src/qm/cli/commands/paper.py`
- `src/qm/cli/commands/live.py`
- `src/qm/cli/commands/report.py`

**`SystemRunner` modes:** `ingest`, `paper`, `live`

**Startup sequence:**
1. Load config (Hydra)
2. Init structured logging (Step 1)
3. Validate secrets (fail fast if missing)
4. Check NTP clock sync (abort if drift > 2s)
5. Connect TimescaleDB + init schema
6. [ADDED] Load portfolio state from audit_log (crash recovery)
7. Start data ingestion (exchange WS)
8. Load model + calibrator from registry
9. [ADDED] Init Rust fast path if available (else Python-only + warn)
10. Start Prometheus metrics server (port 8000)
11. Start TradingLoop with appropriate executor (paper or live)
12. [ADDED] If live: run PositionTracker reconciliation before first trade
13. Start scheduled jobs

**Graceful shutdown (SIGTERM/SIGINT):**
1. Stop TradingLoop (no new trades)
2. If live: wait for pending order confirmations (max 60s)
3. Save portfolio snapshot via AuditWriter
4. Close websockets
5. Close TimescaleDB pool
6. Flush logs
7. Exit 0

**Scheduled jobs:**
- Online recalibration: every 6h, or when rolling ECE > 0.08
- Data quality check: every 30m
- Model drift check: every 1h
- [ADDED] Portfolio state snapshot: every 5 min (crash recovery)
- Model retraining trigger: when 7-day ECE > 0.08 OR 7-day accuracy < 48%

**CLI commands:** Each is a thin wrapper: parse args → load config → call subsystem. `cli/main.py` (already exists) dispatches to these.

---

## Step 7: Rust Fast Path (`crates/qm-fast/`)

**Files to create:**
- `crates/qm-fast/Cargo.toml`
- `crates/qm-fast/pyproject.toml` (maturin)
- `crates/qm-fast/src/lib.rs` — `#![forbid(unsafe_code)]`
- `crates/qm-fast/src/features/{mod,ring_buffer,rolling,export}.rs`
- `crates/qm-fast/src/orderbook/{mod,l2_book,impact}.rs`
- `crates/qm-fast/src/signing/{mod,eip712}.rs`
- `crates/qm-fast/tests/{test_features,test_signing}.rs`
- `src/qm/features/live_cache.py` — Python wrapper with fallback

**Python integration:**
```python
# src/qm/features/live_cache.py
class LiveFeatureCache:
    def compute(self, asset, bar):
        try:
            return qm_fast.get_features(asset.value)
        except Exception:
            FAST_PATH_FALLBACK.labels(component="features").inc()
            return self._python_fallback.compute(asset)
```

**CI parity tests:** `tests/benchmark/test_parity.py`
- Run Rust + Python on identical 10,000-bar input
- Assert `max(|rust - python|) < 1e-9`
- CI failure if divergence detected

**[ADDED] Paper trading fast-path validation:**
- After Rust is built, re-run paper trading with both paths active
- Compare feature outputs, signal decisions, bet sizes
- Log any divergence

**Requires:** `rustc` + `cargo` installed. Not a blocker — system runs Python-only without it.

---

## Step 8: Deployment

**Files to create:**
- `deploy/qm.service` — systemd unit
- `deploy/deploy.sh` — Deployment script
- `deploy/Dockerfile` — Production container
- `docker-compose.prod.yml` — Prod overrides

**systemd service:**
```ini
[Unit]
Description=QM Polymarket Trading System
After=network.target postgresql.service

[Service]
Type=simple
User=qm
WorkingDirectory=/opt/qm
ExecStart=/opt/qm/.venv/bin/python -m qm live
Restart=on-failure
RestartSec=10
WatchdogSec=300
EnvironmentFile=/etc/qm/.env

[Install]
WantedBy=multi-user.target
```

**`deploy.sh` flow:**
1. rsync code to prod (exclude .venv, data/, .git)
2. `uv sync --no-dev` (prod deps only)
3. `maturin develop --release` (if Rust available)
4. `alembic upgrade head`
5. `systemctl restart qm`
6. Health check: poll `localhost:8000/metrics` for 30s
7. On failure: `systemctl stop qm && ln -sfn $PREV /opt/qm && systemctl start qm`

**[ADDED] `docker-compose.prod.yml`:**
- No port exposure to 0.0.0.0 (all 127.0.0.1)
- `restart: always` for all services
- Resource limits for TimescaleDB
- Grafana admin password from env

---

## Verification Plan

### Per-step tests:
1. **Monitoring**: Secret redaction test, metrics server serves `/metrics`
2. **Risk**: Unit tests for each limit, circuit breaker trip/reset, bankroll HWM
3. **Strategy/Portfolio**: Fill → position created → resolution → PnL computed
4. **Trading Loop**: Synthetic bars → signal → risk check → paper fill → audit logged
5. **Polymarket**: Mocked API fixtures for market discovery, order placement, resolution
6. **Scheduler**: Startup sequence completes, SIGTERM triggers graceful shutdown
7. **Rust**: `cargo test` + parity tests + p99 < 5ms benchmark
8. **Deployment**: `deploy.sh --dry-run` on WSL2

### End-to-end smoke test:
```bash
docker compose up -d
python -m qm backfill --assets BTC --timeframes 5m --months 1
python -m qm features --assets BTC --timeframes 5m
python -m qm train --n-trials 10
python -m qm backtest --model latest    # runs acceptance gates
python -m qm paper --model latest --duration 1h
```

### Acceptance criteria (Phase 4):
| Metric | Threshold |
|--------|-----------|
| PBO | < 0.40 |
| Deflated Sharpe | > 0.0 |
| OOS Brier | < 0.25 |
| OOS ECE | < 0.05 |
| Net PnL after costs | > 0 |
| Max drawdown | < 30% |
