"""Edge calculation: model probability vs market price after costs.

Stateless, pure function — used by both backtest and live paths.
"""

from __future__ import annotations

from qm.core.types import Outcome


def compute_edge(
    model_prob_up: float,
    market_prob_up: float,
    spread: float,
) -> tuple[float, Outcome]:
    """Compute trading edge and best side.

    For binary Polymarket markets:
    - edge_up = model_prob - market_prob - half_spread
    - edge_down = (1-model_prob) - (1-market_prob) - half_spread

    Args:
        model_prob_up: Calibrated P(Up) from model.
        market_prob_up: Polymarket mid price for Up outcome.
        spread: Polymarket bid-ask spread.

    Returns:
        (edge, side) where edge > 0 means we have an advantage.
    """
    half_spread = spread / 2
    edge_up = model_prob_up - market_prob_up - half_spread
    edge_down = (1 - model_prob_up) - (1 - market_prob_up) - half_spread

    if edge_up >= edge_down:
        return edge_up, Outcome.UP
    return edge_down, Outcome.DOWN
