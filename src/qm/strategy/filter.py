"""Trade filter chain: decides if a signal is worth executing.

Checks: min edge, time budget, liquidity, risk manager.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

from qm.core.types import PolymarketMarket, Signal
from qm.risk.manager import RiskManager
from qm.strategy.portfolio import Portfolio

logger = logging.getLogger(__name__)


class TradeFilter:
    """Filters signals through multiple criteria before execution.

    Args:
        risk_manager: Risk manager for pre-trade checks.
        min_edge: Minimum edge to trade (after spread).
        min_time_remaining_sec: Skip if market closes in less than this.
        min_liquidity_usd: Skip if orderbook depth < this on either side.
    """

    def __init__(
        self,
        risk_manager: RiskManager,
        min_edge: float = 0.05,
        min_time_remaining_sec: float = 120.0,
        min_liquidity_usd: float = 500.0,
    ) -> None:
        self._risk = risk_manager
        self.min_edge = min_edge
        self.min_time_remaining_sec = min_time_remaining_sec
        self.min_liquidity_usd = min_liquidity_usd

    def filter(
        self,
        signal: Signal,
        size_usd: float,
        portfolio: Portfolio,
        market: PolymarketMarket | None = None,
        now: datetime | None = None,
        data_age_sec: float = 0.0,
        current_ece: float = 0.0,
    ) -> tuple[bool, str]:
        """Run all trade filters. Returns (pass, reason).

        Args:
            signal: The generated signal.
            size_usd: Proposed bet size from Kelly sizer.
            portfolio: Current portfolio state.
            market: Polymarket market info (for time budget + liquidity).
            now: Current time (for time budget check).
            data_age_sec: Seconds since last data update.
            current_ece: Current model calibration error.
        """
        # 1. Minimum edge
        if signal.edge < self.min_edge:
            return False, f"edge_too_low: {signal.edge:.4f} < {self.min_edge}"

        # 2. Time budget (skip if market closes soon)
        if market and now:
            remaining = (market.window_end - now).total_seconds()
            if remaining < self.min_time_remaining_sec:
                return False, f"time_budget: {remaining:.0f}s < {self.min_time_remaining_sec:.0f}s"

        # 3. Liquidity (skip thin markets)
        if market and market.volume < self.min_liquidity_usd:
            return False, f"low_liquidity: ${market.volume:.0f} < ${self.min_liquidity_usd:.0f}"

        # 4. Risk manager (delegates to all risk checks)
        ok, reason = self._risk.pre_trade_check(
            signal=signal,
            size_usd=size_usd,
            open_positions=portfolio.positions_as_dicts(),
            asset_exposures=portfolio.asset_exposures(),
            data_age_sec=data_age_sec,
            current_ece=current_ece,
        )
        if not ok:
            return False, reason

        return True, "OK"
