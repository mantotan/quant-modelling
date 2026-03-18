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
