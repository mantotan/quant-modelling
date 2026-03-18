"""Central risk manager: pre-trade and post-trade checks.

Chains all limit checks in order, returns first failure.
Receives a shared Portfolio and Bankroll — no global state.
"""

from __future__ import annotations

import logging
from typing import Any

from qm.core.types import Signal
from qm.monitoring.metrics import ORDERS_REJECTED
from qm.risk.bankroll import Bankroll
from qm.risk.circuit_breaker import CircuitBreaker
from qm.risk.limits import (
    check_asset_concentration,
    check_concurrent_limit,
    check_correlated_exposure,
    check_daily_loss,
    check_drawdown,
    check_single_bet_size,
)

logger = logging.getLogger(__name__)


class RiskManager:
    """Central risk manager with configurable limits.

    Usage:
        risk = RiskManager(bankroll, circuit_breaker, config)
        ok, reason = risk.pre_trade_check(signal, size, portfolio_state)
    """

    def __init__(
        self,
        bankroll: Bankroll,
        circuit_breaker: CircuitBreaker,
        max_concurrent_bets: int = 20,
        max_single_bet_pct: float = 0.05,
        max_daily_loss_pct: float = 0.10,
        max_drawdown_pct: float = 0.25,
        max_asset_concentration: float = 0.40,
        max_correlated_exposure: float = 0.60,
    ) -> None:
        self.bankroll = bankroll
        self.circuit_breaker = circuit_breaker
        self.max_concurrent_bets = max_concurrent_bets
        self.max_single_bet_pct = max_single_bet_pct
        self.max_daily_loss_pct = max_daily_loss_pct
        self.max_drawdown_pct = max_drawdown_pct
        self.max_asset_concentration = max_asset_concentration
        self.max_correlated_exposure = max_correlated_exposure

    def pre_trade_check(
        self,
        signal: Signal,
        size_usd: float,
        open_positions: list[dict[str, Any]],
        asset_exposures: dict[Any, float] | None = None,
        data_age_sec: float = 0.0,
        current_ece: float = 0.0,
    ) -> tuple[bool, str]:
        """Run all pre-trade risk checks. Returns (pass, reason).

        Checks are ordered by severity — circuit breaker first.
        On first failure, returns immediately.
        """
        total_value = self.bankroll.current

        # 1. Circuit breaker (highest priority)
        ok, reason = self.circuit_breaker.check(
            drawdown=self.bankroll.drawdown,
            daily_loss_pct=self.bankroll.daily_loss_pct,
            data_age_sec=data_age_sec,
            current_ece=current_ece,
        )
        if not ok:
            self._reject(signal, reason)
            return False, reason

        # 2. Concurrent limit
        ok, reason = check_concurrent_limit(len(open_positions), self.max_concurrent_bets)
        if not ok:
            self._reject(signal, reason)
            return False, reason

        # 3. Single bet size
        ok, reason = check_single_bet_size(size_usd, self.bankroll, self.max_single_bet_pct)
        if not ok:
            self._reject(signal, reason)
            return False, reason

        # 4. Daily loss
        ok, reason = check_daily_loss(self.bankroll, self.max_daily_loss_pct)
        if not ok:
            self._reject(signal, reason)
            return False, reason

        # 5. Drawdown
        ok, reason = check_drawdown(self.bankroll, self.max_drawdown_pct)
        if not ok:
            self._reject(signal, reason)
            return False, reason

        # 6. Asset concentration
        exposures = asset_exposures or {}
        ok, reason = check_asset_concentration(
            signal.asset, size_usd, exposures, total_value, self.max_asset_concentration,
        )
        if not ok:
            self._reject(signal, reason)
            return False, reason

        # 7. Correlated exposure
        ok, reason = check_correlated_exposure(
            signal, size_usd, open_positions, total_value, self.max_correlated_exposure,
        )
        if not ok:
            self._reject(signal, reason)
            return False, reason

        return True, "OK"

    def _reject(self, signal: Signal, reason: str) -> None:
        """Log and metric a rejection."""
        ORDERS_REJECTED.labels(
            asset=signal.asset.value,
            reason=reason.split(":")[0],
        ).inc()
        logger.info("Risk rejected: %s for %s", reason, signal.asset.value)
