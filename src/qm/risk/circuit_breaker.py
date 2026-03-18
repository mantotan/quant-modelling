"""Circuit breaker: emergency shutdown on critical conditions.

When tripped, all trading stops. Requires manual reset.
Trip events are persisted to audit log and sent as alerts.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from qm.core.events import CircuitBreakerTrip, EventBus
from qm.monitoring.metrics import CIRCUIT_BREAKER_STATE, CIRCUIT_BREAKER_TRIPS

logger = logging.getLogger(__name__)


class CircuitBreaker:
    """Emergency shutdown conditions.

    Checks multiple conditions. If any triggers, trading halts immediately.
    State is sticky — once tripped, stays tripped until manual reset.
    """

    def __init__(
        self,
        max_drawdown: float = 0.30,
        max_daily_loss: float = 0.15,
        data_stale_sec: float = 300.0,
        drift_ece: float = 0.10,
        consecutive_losses: int = 20,
        event_bus: EventBus | None = None,
    ) -> None:
        self.max_drawdown = max_drawdown
        self.max_daily_loss = max_daily_loss
        self.data_stale_sec = data_stale_sec
        self.drift_ece = drift_ece
        self.max_consecutive_losses = consecutive_losses
        self._event_bus = event_bus
        self._tripped = False
        self._trip_reason = ""
        self._trip_time: datetime | None = None
        self._consecutive_losses = 0

    @property
    def is_tripped(self) -> bool:
        return self._tripped

    @property
    def trip_reason(self) -> str:
        return self._trip_reason

    def check(
        self,
        drawdown: float = 0.0,
        daily_loss_pct: float = 0.0,
        data_age_sec: float = 0.0,
        current_ece: float = 0.0,
    ) -> tuple[bool, str]:
        """Check all circuit breaker conditions.

        Returns (safe_to_trade, reason_if_not).
        """
        if self._tripped:
            return False, f"circuit_breaker_tripped: {self._trip_reason}"

        # Check each condition
        if drawdown >= self.max_drawdown:
            return self._trip(f"drawdown {drawdown:.1%} >= {self.max_drawdown:.1%}")

        if daily_loss_pct >= self.max_daily_loss:
            return self._trip(f"daily_loss {daily_loss_pct:.1%} >= {self.max_daily_loss:.1%}")

        if data_age_sec >= self.data_stale_sec:
            return self._trip(f"data_stale {data_age_sec:.0f}s >= {self.data_stale_sec:.0f}s")

        if current_ece >= self.drift_ece:
            return self._trip(f"ece_drift {current_ece:.3f} >= {self.drift_ece:.3f}")

        if self._consecutive_losses >= self.max_consecutive_losses:
            return self._trip(f"consecutive_losses {self._consecutive_losses} >= {self.max_consecutive_losses}")

        return True, ""

    def record_trade_result(self, won: bool) -> None:
        """Track consecutive losses for circuit breaker."""
        if won:
            self._consecutive_losses = 0
        else:
            self._consecutive_losses += 1

    def _trip(self, reason: str) -> tuple[bool, str]:
        """Trip the circuit breaker."""
        self._tripped = True
        self._trip_reason = reason
        self._trip_time = datetime.now(timezone.utc)

        logger.critical("CIRCUIT BREAKER TRIPPED: %s", reason)
        CIRCUIT_BREAKER_TRIPS.labels(reason=reason.split()[0]).inc()
        CIRCUIT_BREAKER_STATE.set(1)

        # Publish event
        if self._event_bus:
            self._event_bus.publish_nowait(
                CircuitBreakerTrip(reason=reason, timestamp=self._trip_time)
            )

        return False, f"circuit_breaker_tripped: {reason}"

    def reset(self) -> None:
        """Manual reset after investigation."""
        if self._tripped:
            logger.warning(
                "Circuit breaker reset (was tripped: %s at %s)",
                self._trip_reason, self._trip_time,
            )
        self._tripped = False
        self._trip_reason = ""
        self._trip_time = None
        self._consecutive_losses = 0
        CIRCUIT_BREAKER_STATE.set(0)

    def to_dict(self) -> dict[str, Any]:
        return {
            "tripped": self._tripped,
            "reason": self._trip_reason,
            "trip_time": self._trip_time.isoformat() if self._trip_time else None,
            "consecutive_losses": self._consecutive_losses,
        }
