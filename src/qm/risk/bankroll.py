"""Bankroll tracking with high-water mark and daily PnL.

Tracks the running state of the trading account.
Daily PnL resets at midnight ET (Polymarket's reference timezone).
State is serializable for crash recovery.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, datetime
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

POLYMARKET_TZ = ZoneInfo("America/New_York")


@dataclass
class Bankroll:
    """Tracks bankroll, high-water mark, and daily PnL."""

    initial: float
    current: float = 0.0
    high_water_mark: float = 0.0
    daily_pnl: float = 0.0
    total_realized_pnl: float = 0.0
    _current_day: date = field(default_factory=lambda: datetime.now(POLYMARKET_TZ).date())

    def __post_init__(self) -> None:
        if self.current == 0.0:
            self.current = self.initial
        if self.high_water_mark == 0.0:
            self.high_water_mark = self.initial

    def on_pnl(self, pnl: float) -> None:
        """Record a realized PnL from a resolved position."""
        self._check_day_rollover()
        self.current += pnl
        self.daily_pnl += pnl
        self.total_realized_pnl += pnl

        if self.current > self.high_water_mark:
            self.high_water_mark = self.current

    @property
    def drawdown(self) -> float:
        """Current drawdown from HWM as a fraction [0, 1]."""
        if self.high_water_mark <= 0:
            return 0.0
        return max(0.0, (self.high_water_mark - self.current) / self.high_water_mark)

    @property
    def daily_loss_pct(self) -> float:
        """Today's loss as fraction of starting bankroll. Positive = loss."""
        if self.initial <= 0:
            return 0.0
        return max(0.0, -self.daily_pnl / self.initial)

    def _check_day_rollover(self) -> None:
        """Reset daily PnL at midnight ET."""
        today = datetime.now(POLYMARKET_TZ).date()
        if today != self._current_day:
            logger.info(
                "Day rollover: daily_pnl=%.2f, bankroll=%.2f",
                self.daily_pnl, self.current,
            )
            self.daily_pnl = 0.0
            self._current_day = today

    def to_dict(self) -> dict:
        """Serialize for crash recovery."""
        return {
            "initial": self.initial,
            "current": self.current,
            "high_water_mark": self.high_water_mark,
            "daily_pnl": self.daily_pnl,
            "total_realized_pnl": self.total_realized_pnl,
            "current_day": self._current_day.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict) -> Bankroll:
        """Restore from serialized state."""
        b = cls(
            initial=data["initial"],
            current=data["current"],
            high_water_mark=data["high_water_mark"],
        )
        b.daily_pnl = data.get("daily_pnl", 0.0)
        b.total_realized_pnl = data.get("total_realized_pnl", 0.0)
        b._current_day = date.fromisoformat(data.get("current_day", date.today().isoformat()))
        return b
