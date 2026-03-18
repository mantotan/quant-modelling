"""Configurable HPO objective function.

Allows the autoresearch loop to switch between different objective
functions for Optuna HPO, rather than always minimising Brier score.

Supported primaries:
- ``"brier"``  — minimise Brier score (calibration quality)
- ``"sharpe"`` — maximise Sharpe ratio (risk-adjusted PnL)

Penalties can be stacked to create composite objectives:
- Brier penalty: penalise when Brier exceeds a threshold
- Trade count penalty: penalise when n_trades falls below a minimum
- Drawdown penalty: penalise when max_dd exceeds a threshold

Usage:
    config = ObjectiveConfig(primary="sharpe", brier_threshold=0.25)
    value = compute_objective(metrics, config)
    # Optuna always minimises, so sharpe is negated internally.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ObjectiveConfig:
    """Configuration for the HPO objective function.

    Attributes:
        primary: Which metric to optimise. ``"brier"`` (minimise) or
            ``"sharpe"`` (maximise, negated for Optuna).
        brier_threshold: Brier score threshold above which a penalty
            is applied. Set to 1.0 to disable.
        brier_penalty_weight: Multiplier for the Brier penalty term.
        min_trades: Minimum number of trades required. Fewer trades
            incur a penalty.
        trade_penalty_weight: Multiplier for the trade count penalty.
        max_drawdown_threshold: Drawdown threshold above which a
            penalty is applied. Set to 1.0 to disable.
        drawdown_penalty_weight: Multiplier for the drawdown penalty.
    """

    primary: str = "brier"
    brier_threshold: float = 0.25
    brier_penalty_weight: float = 10.0
    min_trades: int = 50
    trade_penalty_weight: float = 5.0
    max_drawdown_threshold: float = 0.30
    drawdown_penalty_weight: float = 5.0

    def __post_init__(self) -> None:
        if self.primary not in ("brier", "sharpe"):
            msg = f"Unknown primary objective: {self.primary!r}. Use 'brier' or 'sharpe'."
            raise ValueError(msg)


def compute_objective(
    metrics: dict[str, float],
    config: ObjectiveConfig | None = None,
) -> float:
    """Compute a scalar objective value from backtest metrics.

    The returned value is designed for **minimisation** by Optuna.
    Lower is better.

    Args:
        metrics: Dict from ``BacktestEngine.evaluate_model_fast()``.
            Expected keys: ``brier``, ``sharpe``, ``n_trades``, ``max_dd``.
        config: Objective configuration. Defaults to Brier-primary.

    Returns:
        Scalar objective value (lower is better).
    """
    if config is None:
        config = ObjectiveConfig()

    brier = metrics.get("brier", 1.0)
    sharpe = metrics.get("sharpe", 0.0)
    n_trades = metrics.get("n_trades", 0)
    max_dd = metrics.get("max_dd", 0.0)

    # Primary metric (sharpe negated so Optuna can minimise)
    base = brier if config.primary == "brier" else -sharpe

    # Penalty: Brier exceeds threshold
    penalty = 0.0
    if brier > config.brier_threshold:
        penalty += (brier - config.brier_threshold) * config.brier_penalty_weight

    # Penalty: insufficient trades
    if n_trades < config.min_trades:
        shortfall = (config.min_trades - n_trades) / max(config.min_trades, 1)
        penalty += shortfall * config.trade_penalty_weight

    # Penalty: excessive drawdown
    if max_dd > config.max_drawdown_threshold:
        penalty += (
            (max_dd - config.max_drawdown_threshold)
            * config.drawdown_penalty_weight
        )

    total = base + penalty

    logger.debug(
        "Objective: primary=%s base=%.4f penalty=%.4f total=%.4f "
        "(brier=%.4f sharpe=%.4f trades=%d dd=%.4f)",
        config.primary, base, penalty, total,
        brier, sharpe, n_trades, max_dd,
    )

    return total
