"""Strategy engine protocol — common interface for all trading strategies.

All strategy engines (Dutch, Directional, etc.) satisfy this protocol,
enabling a unified backtest loop and live trading infrastructure.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from qm.strategy.dutch.engine import DutchBarSummary, DutchOrder


@runtime_checkable
class StrategyEngine(Protocol):
    """Protocol that all strategy engines must satisfy.

    The engine is pure logic — no I/O, no async. It receives book
    snapshots and returns order decisions. The fill simulator and
    monitor handle the rest.
    """

    @property
    def flip_killed(self) -> bool:
        """Whether the engine has entered flip-kill mode (stop buying)."""
        ...

    def on_tick(
        self,
        time_pct: float,
        cal_prob: float,
        book_up: object,
        book_dn: object,
    ) -> list[DutchOrder]:
        """Process one tick, return list of orders to place."""
        ...

    def on_fill(
        self,
        order: DutchOrder,
        fill_price: float,
        filled_shares: float,
    ) -> None:
        """Handle a fill event from the simulator."""
        ...

    def on_order_cancelled(self, order: DutchOrder) -> None:
        """Handle a cancelled order."""
        ...

    def resolve(self, outcome: str) -> DutchBarSummary:
        """Finalize bar and build summary (before outcome is known)."""
        ...

    def reset(self) -> None:
        """Reset state for a new bar."""
        ...

    def set_bar_info(
        self,
        bar_id: int,
        condition_id: str,
        window_start: str,
        window_end: str,
    ) -> None:
        """Set metadata for the current bar."""
        ...
