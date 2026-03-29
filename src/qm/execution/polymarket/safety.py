"""Live trading safety guard — circuit breaker and risk limits.

Prevents runaway losses by enforcing:
- Per-order size cap
- Daily loss kill switch
- Concurrent order limit
- Per-pair position limit
- Loss streak cooldown
- Persistent state (survives process restarts)
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class LiveSafetyConfig:
    """Configuration for live trading safety limits."""

    max_order_usd: float = 2.0             # Hard cap per order
    max_daily_loss_usd: float = 50.0       # Kill switch if daily loss exceeds
    max_concurrent_orders: int = 10        # Across all pairs
    max_position_per_pair: float = 20.0    # Max USD exposure per pair
    min_usdc_balance: float = 50.0         # Stop if wallet drops below
    cooldown_after_loss_streak: int = 5    # Pause after N consecutive losses
    cooldown_bars: int = 3                 # Resume after N bars of cooldown


class LiveSafetyGuard:
    """Circuit breaker and risk limits for live trading.

    Usage:
        guard = LiveSafetyGuard(LiveSafetyConfig())
        allowed, reason = guard.can_trade("ETH_5m", 2.0)
        if allowed:
            # place order
            guard.record_fill("ETH_5m", 2.0)
        # after bar resolution:
        guard.record_pnl(-3.50)
    """

    def __init__(self, config: LiveSafetyConfig) -> None:
        self._config = config
        self._daily_pnl: float = 0.0
        self._daily_volume: float = 0.0
        self._consecutive_losses: int = 0
        self._cooldown_remaining: int = 0
        self._pair_exposure: dict[str, float] = {}
        self._open_orders: int = 0
        self._killed: bool = False
        self._kill_reason: str = ""
        self._bars_resolved: int = 0

    def can_trade(self, pair: str, order_usd: float) -> tuple[bool, str]:
        """Check all safety conditions before placing an order.

        Returns (allowed, reason).
        """
        if self._killed:
            return False, f"KILLED: {self._kill_reason}"

        if self._daily_pnl < -self._config.max_daily_loss_usd:
            self._killed = True
            self._kill_reason = (
                f"daily loss ${abs(self._daily_pnl):.2f} "
                f"> max ${self._config.max_daily_loss_usd:.2f}"
            )
            logger.error("SAFETY KILL: %s", self._kill_reason)
            return False, self._kill_reason

        if order_usd > self._config.max_order_usd:
            return False, (
                f"order ${order_usd:.2f} > max ${self._config.max_order_usd:.2f}"
            )

        if self._open_orders >= self._config.max_concurrent_orders:
            return False, f"too many open orders ({self._open_orders})"

        pair_exp = self._pair_exposure.get(pair, 0.0)
        if pair_exp + order_usd > self._config.max_position_per_pair:
            return False, (
                f"{pair} exposure ${pair_exp:.2f} + ${order_usd:.2f} "
                f"> max ${self._config.max_position_per_pair:.2f}"
            )

        if self._cooldown_remaining > 0:
            return False, (
                f"loss streak cooldown ({self._cooldown_remaining} bars remaining)"
            )

        return True, "ok"

    def record_fill(self, pair: str, usd: float) -> None:
        """Record a filled order."""
        self._pair_exposure[pair] = self._pair_exposure.get(pair, 0.0) + usd
        self._open_orders += 1
        self._daily_volume += usd

    def record_order_done(self) -> None:
        """Record that an order completed (filled, cancelled, or expired)."""
        self._open_orders = max(0, self._open_orders - 1)

    def record_pnl(self, pnl: float) -> None:
        """Record bar-level PnL result."""
        self._daily_pnl += pnl
        self._bars_resolved += 1

        if pnl < 0:
            self._consecutive_losses += 1
            if self._consecutive_losses >= self._config.cooldown_after_loss_streak:
                self._cooldown_remaining = self._config.cooldown_bars
                logger.warning(
                    "SAFETY: %d consecutive losses, cooling down for %d bars",
                    self._consecutive_losses, self._cooldown_remaining,
                )
        else:
            self._consecutive_losses = 0

        if self._cooldown_remaining > 0:
            self._cooldown_remaining -= 1

    def record_bar_end(self, pair: str) -> None:
        """Reset per-pair exposure and open orders on bar completion."""
        self._pair_exposure.pop(pair, None)
        self._open_orders = 0  # All orders cancelled at bar end

    def reset_daily(self) -> None:
        """Reset daily counters (call at midnight UTC)."""
        logger.info(
            "SAFETY: daily reset (PnL=$%.2f, volume=$%.2f, bars=%d)",
            self._daily_pnl, self._daily_volume, self._bars_resolved,
        )
        self._daily_pnl = 0.0
        self._daily_volume = 0.0
        self._bars_resolved = 0
        # Don't reset killed state — manual intervention required

    @property
    def is_killed(self) -> bool:
        return self._killed

    @property
    def daily_pnl(self) -> float:
        return self._daily_pnl

    @property
    def summary(self) -> dict:
        return {
            "daily_pnl": round(self._daily_pnl, 2),
            "daily_volume": round(self._daily_volume, 2),
            "bars_resolved": self._bars_resolved,
            "consecutive_losses": self._consecutive_losses,
            "cooldown_remaining": self._cooldown_remaining,
            "open_orders": self._open_orders,
            "killed": self._killed,
            "kill_reason": self._kill_reason,
        }

    def save_state(self, path: Path) -> None:
        """Persist safety state to JSON (survives process restart)."""
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "w") as f:
                json.dump(self.summary, f, indent=2)
        except Exception as e:
            logger.warning("Failed to save safety state: %s", e)

    def load_state(self, path: Path) -> None:
        """Restore safety state from JSON."""
        if not path.exists():
            return
        try:
            with open(path) as f:
                state = json.load(f)
            self._daily_pnl = state.get("daily_pnl", 0.0)
            self._daily_volume = state.get("daily_volume", 0.0)
            self._bars_resolved = state.get("bars_resolved", 0)
            self._consecutive_losses = state.get("consecutive_losses", 0)
            self._cooldown_remaining = state.get("cooldown_remaining", 0)
            self._killed = state.get("killed", False)
            self._kill_reason = state.get("kill_reason", "")
            self._open_orders = 0  # Always reset on startup — stale count blocks trading
            if self._killed:
                logger.warning("SAFETY: restored KILLED state: %s", self._kill_reason)
            else:
                logger.info(
                    "SAFETY: restored state (PnL=$%.2f, %d bars)",
                    self._daily_pnl, self._bars_resolved,
                )
        except Exception as e:
            logger.warning("Failed to load safety state: %s", e)
