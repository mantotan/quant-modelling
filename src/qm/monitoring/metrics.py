"""Prometheus metrics definitions — single source of truth.

All metrics are defined here. Other modules import and use them directly.
Start the metrics server via `start_metrics_server(port)`.
"""

from __future__ import annotations

from prometheus_client import Counter, Gauge, Histogram, start_http_server

# ── Trading metrics ─────────────────────────────────────────────────

SIGNALS_GENERATED = Counter(
    "qm_signals_total",
    "Total signals generated",
    ["asset", "market_type", "side"],
)

ORDERS_PLACED = Counter(
    "qm_orders_placed_total",
    "Total orders placed",
    ["asset", "outcome"],
)

ORDERS_REJECTED = Counter(
    "qm_orders_rejected_total",
    "Orders rejected by risk checks",
    ["asset", "reason"],
)

BET_SIZE_USD = Histogram(
    "qm_bet_size_usd",
    "Bet sizes in USDC",
    buckets=[5, 10, 25, 50, 100, 200, 500],
)

EDGE_OBSERVED = Histogram(
    "qm_edge_observed",
    "Observed edge at signal time",
    buckets=[0.01, 0.02, 0.05, 0.10, 0.15, 0.20, 0.30],
)

PNL_TOTAL = Gauge("qm_pnl_total_usd", "Total cumulative PnL in USDC")
PNL_DAILY = Gauge("qm_pnl_daily_usd", "Daily PnL in USDC")
DRAWDOWN_PCT = Gauge("qm_drawdown_pct", "Current drawdown from HWM")
BANKROLL = Gauge("qm_bankroll_usd", "Current bankroll in USDC")
OPEN_POSITIONS = Gauge("qm_open_positions", "Number of open positions")

# ── Model metrics ───────────────────────────────────────────────────

MODEL_ACCURACY = Gauge(
    "qm_model_accuracy",
    "Rolling model accuracy",
    ["asset", "window"],
)

CALIBRATION_ECE = Gauge(
    "qm_calibration_ece",
    "Expected calibration error",
    ["asset"],
)

BRIER_SCORE = Gauge(
    "qm_brier_score",
    "Rolling Brier score",
    ["asset"],
)

# ── Drift monitoring metrics ──────────────────────────────────────────

DRIFT_BRIER_ROLLING = Gauge(
    "qm_drift_brier_rolling",
    "Rolling 30-day Brier score for drift detection",
    ["asset"],
)

DRIFT_THRESHOLD = Gauge(
    "qm_drift_threshold",
    "Brier drift threshold (1.2x validation floor)",
    ["asset"],
)

DRIFT_PREDICTIONS_COUNT = Gauge(
    "qm_drift_predictions_count",
    "Number of predictions in rolling window",
    ["asset"],
)

DRIFT_DAYS_SINCE_RETRAIN = Gauge(
    "qm_drift_days_since_retrain",
    "Days since last model retrain",
    ["asset"],
)

RETRAIN_TRIGGERS = Counter(
    "qm_retrain_triggers_total",
    "Retrain triggers fired",
    ["asset", "reason"],
)

# ── Data metrics ────────────────────────────────────────────────────

FEED_LATENCY_MS = Histogram(
    "qm_feed_latency_ms",
    "Exchange feed latency in milliseconds",
    ["exchange", "asset"],
    buckets=[10, 50, 100, 250, 500, 1000, 5000],
)

FEED_HEALTH = Gauge(
    "qm_feed_healthy",
    "Feed health (1=healthy, 0=unhealthy)",
    ["exchange"],
)

DATA_GAPS = Counter(
    "qm_data_gaps_total",
    "Missing bar count",
    ["asset", "timeframe"],
)

# ── Performance metrics ─────────────────────────────────────────────

FAST_PATH_FALLBACK = Counter(
    "qm_fast_path_fallback_total",
    "Python fallback invocations (Rust path failed)",
    ["component"],
)

INFERENCE_LATENCY_NS = Histogram(
    "qm_inference_latency_ns",
    "Model inference latency in nanoseconds",
    buckets=[
        100_000,      # 0.1ms
        500_000,      # 0.5ms
        1_000_000,    # 1ms
        2_000_000,    # 2ms
        5_000_000,    # 5ms
        10_000_000,   # 10ms
        50_000_000,   # 50ms
    ],
)

# ── Pulse (intra-bar) metrics ──────────────────────────────────────

PULSE_PREDICTIONS = Counter(
    "qm_pulse_predictions_total",
    "Pulse tick predictions",
    ["asset"],
)

PULSE_LATENCY_NS = Histogram(
    "qm_pulse_latency_ns",
    "Pulse prediction latency in nanoseconds",
    buckets=[50_000, 100_000, 250_000, 500_000, 1_000_000, 5_000_000],
)

PULSE_EDGE = Histogram(
    "qm_pulse_edge",
    "Pulse edge distribution",
    ["asset"],
    buckets=[0.005, 0.01, 0.02, 0.03, 0.05, 0.10, 0.15],
)

PULSE_TRADES = Counter(
    "qm_pulse_trades_total",
    "Pulse trades executed",
    ["asset", "side"],
)

PULSE_ELAPSED_AT_TRADE = Histogram(
    "qm_pulse_elapsed_pct",
    "Elapsed pct when Pulse trade placed",
    buckets=[0.01, 0.05, 0.10, 0.20, 0.30, 0.50, 0.70, 0.90],
)

PULSE_ROI_PER_TRADE = Histogram(
    "qm_pulse_roi_per_trade",
    "ROI per Pulse trade",
    buckets=[-0.10, -0.05, -0.02, 0.0, 0.02, 0.05, 0.10, 0.20],
)

# ── Polymarket recorder metrics ────────────────────────────────────

POLYMARKET_SNAPSHOTS_RECORDED = Counter(
    "qm_polymarket_snapshots_total",
    "Polymarket odds snapshots recorded",
    ["asset"],
)

POLYMARKET_RECORDER_ERRORS = Counter(
    "qm_polymarket_recorder_errors_total",
    "Polymarket recorder errors",
    ["error_type"],
)

POLYMARKET_ACTIVE_MARKETS = Gauge(
    "qm_polymarket_active_markets",
    "Number of active Polymarket markets being tracked",
)

# ── Ensemble metrics ──────────────────────────────────────────────

ENSEMBLE_PREDICTIONS = Counter(
    "qm_ensemble_predictions_total",
    "Ensemble predictions generated",
    ["asset", "strategy"],
)

ENSEMBLE_DISAGREEMENT = Histogram(
    "qm_ensemble_disagreement",
    "|sentinel_prob - pulse_prob| distribution",
    ["asset"],
    buckets=[0.02, 0.05, 0.10, 0.15, 0.20, 0.30, 0.40],
)

ENSEMBLE_STRATEGY_SELECTED = Counter(
    "qm_ensemble_strategy_selected_total",
    "Which ensemble strategy was used",
    ["strategy"],
)

ENSEMBLE_TRADES_FILTERED_DISAGREEMENT = Counter(
    "qm_ensemble_filtered_disagreement_total",
    "Trades rejected due to model disagreement",
    ["asset"],
)

FEATURE_COMPUTE_NS = Histogram(
    "qm_feature_compute_ns",
    "Feature computation latency in nanoseconds",
    buckets=[
        100_000, 500_000, 1_000_000, 5_000_000, 10_000_000, 50_000_000, 200_000_000,
    ],
)

# ── Circuit breaker ─────────────────────────────────────────────────

CIRCUIT_BREAKER_TRIPS = Counter(
    "qm_circuit_breaker_trips_total",
    "Circuit breaker trip count",
    ["reason"],
)

CIRCUIT_BREAKER_STATE = Gauge(
    "qm_circuit_breaker_active",
    "Circuit breaker state (1=tripped, 0=normal)",
)


def start_metrics_server(port: int = 8000) -> None:
    """Start the Prometheus metrics HTTP server."""
    start_http_server(port)
