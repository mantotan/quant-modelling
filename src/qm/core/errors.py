"""Custom exception hierarchy."""


class QMError(Exception):
    """Base exception for all qm errors."""


# Data layer
class DataError(QMError):
    """Base for data-related errors."""


class ConnectorError(DataError):
    """Exchange or Polymarket connection failure."""


class DataGapError(DataError):
    """Missing bars or stale feed detected."""


class BackfillError(DataError):
    """Historical data backfill failure."""


# Model layer
class ModelError(QMError):
    """Base for model-related errors."""


class TrainingError(ModelError):
    """Model training failure."""


class CalibrationError(ModelError):
    """Calibration failure or drift detected."""


class InferenceError(ModelError):
    """Model inference failure."""


# Execution layer
class ExecutionError(QMError):
    """Base for execution-related errors."""


class OrderError(ExecutionError):
    """Order placement or management failure."""


class RiskLimitBreached(ExecutionError):
    """Pre-trade risk check failed."""


class CircuitBreakerTripped(ExecutionError):
    """Emergency shutdown triggered."""


# Fast path
class FastPathError(QMError):
    """Rust fast path failure — will trigger Python fallback."""
