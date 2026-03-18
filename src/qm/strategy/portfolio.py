"""Portfolio state tracking for concurrent positions.

Tracks open positions, available cash, realized PnL.
Shared by both paper and live executors — single instance, no duplication.
Serializable for crash recovery.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from qm.core.types import Asset, Outcome
from qm.monitoring.metrics import BANKROLL, DRAWDOWN_PCT, OPEN_POSITIONS, PNL_TOTAL
from qm.risk.bankroll import Bankroll

logger = logging.getLogger(__name__)


@dataclass
class Position:
    """A single open bet on Polymarket."""

    id: str
    asset: Asset
    side: Outcome
    entry_price: float  # price paid per share
    size_usd: float  # total USD committed
    shares: float  # size_usd / entry_price
    entry_time: datetime
    condition_id: str = ""  # Polymarket market identifier

    def pnl_if_correct(self) -> float:
        """PnL if this position wins (receives $1/share)."""
        return self.shares * (1 - self.entry_price)

    def pnl_if_wrong(self) -> float:
        """PnL if this position loses (shares go to zero)."""
        return -self.size_usd


class Portfolio:
    """Tracks all open positions and cash.

    Thread-safe for single-threaded async usage.
    Updated by TradingLoop on fills and resolutions.
    """

    def __init__(self, bankroll: Bankroll) -> None:
        self.bankroll = bankroll
        self._positions: dict[str, Position] = {}  # id → Position
        self._resolved: list[dict[str, Any]] = []  # history of resolved positions

    @property
    def open_positions(self) -> list[Position]:
        return list(self._positions.values())

    @property
    def open_position_count(self) -> int:
        return len(self._positions)

    @property
    def available_cash(self) -> float:
        committed = sum(p.size_usd for p in self._positions.values())
        return max(0.0, self.bankroll.current - committed)

    @property
    def total_value(self) -> float:
        return self.bankroll.current

    def asset_exposures(self) -> dict[Asset, float]:
        """Current USD exposure per asset."""
        exposures: dict[Asset, float] = {}
        for p in self._positions.values():
            exposures[p.asset] = exposures.get(p.asset, 0.0) + p.size_usd
        return exposures

    def positions_as_dicts(self) -> list[dict[str, Any]]:
        """Open positions as plain dicts (for risk checks)."""
        return [
            {
                "id": p.id,
                "asset": p.asset,
                "side": p.side.value,
                "size_usd": p.size_usd,
                "entry_price": p.entry_price,
                "condition_id": p.condition_id,
            }
            for p in self._positions.values()
        ]

    def on_fill(
        self,
        asset: Asset,
        side: Outcome,
        size_usd: float,
        fill_price: float,
        condition_id: str = "",
    ) -> Position:
        """Record a new position from a filled order."""
        pos_id = str(uuid.uuid4())[:8]
        shares = size_usd / fill_price if fill_price > 0 else 0.0

        position = Position(
            id=pos_id,
            asset=asset,
            side=side,
            entry_price=fill_price,
            size_usd=size_usd,
            shares=shares,
            entry_time=datetime.now(timezone.utc),
            condition_id=condition_id,
        )
        self._positions[pos_id] = position

        # Update metrics
        OPEN_POSITIONS.set(self.open_position_count)
        logger.info(
            "Position opened: %s %s %s $%.2f @ %.4f",
            pos_id, asset.value, side.value, size_usd, fill_price,
        )
        return position

    def on_resolution(self, condition_id: str, outcome: Outcome) -> float:
        """Resolve all positions matching a market condition.

        Args:
            condition_id: Polymarket condition ID that resolved.
            outcome: The actual outcome (UP or DOWN).

        Returns:
            Total PnL from resolved positions.
        """
        total_pnl = 0.0
        to_remove = []

        for pos_id, pos in self._positions.items():
            if pos.condition_id != condition_id:
                continue

            won = pos.side == outcome
            pnl = pos.pnl_if_correct() if won else pos.pnl_if_wrong()
            total_pnl += pnl

            self.bankroll.on_pnl(pnl)

            self._resolved.append({
                "id": pos_id,
                "asset": pos.asset.value,
                "side": pos.side.value,
                "entry_price": pos.entry_price,
                "size_usd": pos.size_usd,
                "outcome": outcome.value,
                "won": won,
                "pnl": pnl,
                "resolved_at": datetime.now(timezone.utc).isoformat(),
            })

            logger.info(
                "Position resolved: %s %s %s %s PnL=%.2f",
                pos_id, pos.asset.value, pos.side.value,
                "WIN" if won else "LOSS", pnl,
            )
            to_remove.append(pos_id)

        for pos_id in to_remove:
            del self._positions[pos_id]

        # Update metrics
        OPEN_POSITIONS.set(self.open_position_count)
        PNL_TOTAL.set(self.bankroll.total_realized_pnl)
        BANKROLL.set(self.bankroll.current)
        DRAWDOWN_PCT.set(self.bankroll.drawdown)

        return total_pnl

    def on_resolution_by_id(self, position_id: str, won: bool) -> float:
        """Resolve a single position by its ID (for paper trading)."""
        pos = self._positions.get(position_id)
        if pos is None:
            return 0.0

        pnl = pos.pnl_if_correct() if won else pos.pnl_if_wrong()
        self.bankroll.on_pnl(pnl)
        del self._positions[position_id]

        OPEN_POSITIONS.set(self.open_position_count)
        PNL_TOTAL.set(self.bankroll.total_realized_pnl)
        BANKROLL.set(self.bankroll.current)
        DRAWDOWN_PCT.set(self.bankroll.drawdown)

        return pnl

    def to_dict(self) -> dict[str, Any]:
        """Serialize for crash recovery."""
        return {
            "bankroll": self.bankroll.to_dict(),
            "positions": [
                {
                    "id": p.id,
                    "asset": p.asset.value,
                    "side": p.side.value,
                    "entry_price": p.entry_price,
                    "size_usd": p.size_usd,
                    "shares": p.shares,
                    "entry_time": p.entry_time.isoformat(),
                    "condition_id": p.condition_id,
                }
                for p in self._positions.values()
            ],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Portfolio:
        """Restore from serialized state."""
        bankroll = Bankroll.from_dict(data["bankroll"])
        portfolio = cls(bankroll=bankroll)
        for pd in data.get("positions", []):
            portfolio._positions[pd["id"]] = Position(
                id=pd["id"],
                asset=Asset(pd["asset"]),
                side=Outcome(pd["side"]),
                entry_price=pd["entry_price"],
                size_usd=pd["size_usd"],
                shares=pd["shares"],
                entry_time=datetime.fromisoformat(pd["entry_time"]),
                condition_id=pd.get("condition_id", ""),
            )
        return portfolio
