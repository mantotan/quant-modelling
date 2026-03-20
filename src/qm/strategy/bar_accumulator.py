"""Per-bar prediction accumulator for one-bet-per-bar trading.

Eliminates the side-flipping problem where the model bets DOWN at t=0.30
then UP at t=0.80 on the same bar. Accumulates predictions within a bar
and selects the single best trade.

Two modes:
- best_edge: wait for all predictions, execute the one with max |edge|
- first_confident: execute immediately when edge exceeds threshold
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Literal

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class TradeDecision:
    """Selected trade from accumulated intra-bar predictions."""

    bar_id: int
    time_pct: float
    model_prob: float
    side: str  # "UP" or "DOWN"
    edge: float


class BarEdgeAccumulator:
    """Accumulates intra-bar predictions, executes the best one per bar.

    Prevents multiple trades and side-flipping within the same bar.
    Once a bar has a committed trade, further predictions for that bar
    are logged but ignored.
    """

    def __init__(
        self,
        strategy: Literal["best_edge", "first_confident"] = "first_confident",
        confidence_threshold: float = 0.05,
    ) -> None:
        self._strategy = strategy
        self._confidence_threshold = confidence_threshold
        # bar_id → best prediction seen so far
        self._pending: dict[int, TradeDecision] = {}
        # bar_id → already committed (traded)
        self._committed: set[int] = set()

    def on_prediction(
        self,
        bar_id: int,
        time_pct: float,
        model_prob: float,
        market_prob: float,
        spread: float,
    ) -> TradeDecision | None:
        """Feed a prediction. Returns TradeDecision if ready to execute.

        For first_confident: returns immediately when edge > threshold.
        For best_edge: stores prediction, returns None (wait for on_bar_end).
        """
        if bar_id in self._committed:
            return None

        # Compute edge and side
        half_spread = spread / 2
        edge_up = model_prob - market_prob - half_spread
        edge_down = (1 - model_prob) - (1 - market_prob) - half_spread

        if edge_up > edge_down:
            side = "UP"
            edge = edge_up
        else:
            side = "DOWN"
            edge = edge_down

        if edge <= 0:
            return None

        decision = TradeDecision(
            bar_id=bar_id,
            time_pct=time_pct,
            model_prob=model_prob,
            side=side,
            edge=edge,
        )

        if self._strategy == "first_confident":
            if edge >= self._confidence_threshold:
                self._committed.add(bar_id)
                self._pending.pop(bar_id, None)
                logger.debug(
                    "first_confident: bar %d trade %s edge=%.4f at t=%.2f",
                    bar_id, side, edge, time_pct,
                )
                return decision
            # Below threshold — store as candidate but don't execute
            best = self._pending.get(bar_id)
            if best is None or edge > best.edge:
                self._pending[bar_id] = decision
            return None

        # best_edge mode: always store, never execute immediately
        best = self._pending.get(bar_id)
        if best is None or edge > best.edge:
            self._pending[bar_id] = decision
        return None

    def on_bar_end(self, bar_id: int) -> TradeDecision | None:
        """Bar ended. Returns the best stored prediction if not yet committed.

        For best_edge: this is when the trade actually fires.
        For first_confident: this fires the best sub-threshold prediction
        as a fallback (if no prediction exceeded the confidence threshold).
        """
        if bar_id in self._committed:
            self._pending.pop(bar_id, None)
            return None

        decision = self._pending.pop(bar_id, None)
        if decision is not None:
            self._committed.add(bar_id)
            logger.debug(
                "on_bar_end: bar %d trade %s edge=%.4f at t=%.2f",
                bar_id, decision.side, decision.edge, decision.time_pct,
            )
        return decision

    def cleanup_old_bars(self, current_bar_id: int, max_age: int = 5) -> None:
        """Remove state for bars older than max_age bars ago."""
        cutoff = current_bar_id - max_age * 300  # 300s per 5m bar
        old_pending = [b for b in self._pending if b < cutoff]
        for b in old_pending:
            del self._pending[b]
        old_committed = {b for b in self._committed if b < cutoff}
        self._committed -= old_committed

    @property
    def strategy(self) -> str:
        return self._strategy

    @property
    def confidence_threshold(self) -> float:
        return self._confidence_threshold

    @property
    def pending_bars(self) -> int:
        return len(self._pending)
