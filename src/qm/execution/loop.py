"""Core trading loop shared by paper and live execution.

Single decision loop, pluggable executor. Eliminates duplication
between paper and live paths.

Flow per bar:
  bar_completed → generate_signal → size_bet → risk_check → execute → audit
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Protocol

from qm.core.types import Asset, Bar, MarketType, Outcome, PolymarketMarket, Signal
from qm.execution.audit import AuditWriter
from qm.model.calibration.calibrator import IsotonicCalibrator
from qm.model.signals import SignalGenerator
from qm.monitoring.metrics import (
    BET_SIZE_USD,
    EDGE_OBSERVED,
    INFERENCE_LATENCY_NS,
    ORDERS_PLACED,
    SIGNALS_GENERATED,
)
from qm.risk.manager import RiskManager
from qm.strategy.filter import TradeFilter
from qm.strategy.portfolio import Portfolio
from qm.strategy.sizing.kelly import KellySizer

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class Fill:
    """Result of an order execution (paper or live)."""

    price: float
    size_usd: float
    status: str  # "filled", "rejected", "timeout"
    order_id: str = ""


class Executor(Protocol):
    """Interface for paper and live executors."""

    async def execute(self, signal: Signal, size_usd: float, market: PolymarketMarket | None) -> Fill: ...


class TradingLoop:
    """Core decision loop. Same logic for paper and live.

    The executor is the only thing that differs:
    - PaperExecutor: instant simulated fill
    - LiveExecutor: places real Polymarket order
    """

    def __init__(
        self,
        signal_generator: SignalGenerator,
        calibrator: IsotonicCalibrator | None,
        risk_manager: RiskManager,
        trade_filter: TradeFilter,
        sizer: KellySizer,
        portfolio: Portfolio,
        executor: Executor,
        audit: AuditWriter,
        predictor: Any = None,  # CompiledPredictor or LightGBM model
    ) -> None:
        self._signal_gen = signal_generator
        self._calibrator = calibrator
        self._risk = risk_manager
        self._filter = trade_filter
        self._sizer = sizer
        self._portfolio = portfolio
        self._executor = executor
        self._audit = audit
        self._predictor = predictor
        self._running = True

    async def on_bar_completed(
        self,
        bar: Bar,
        market: PolymarketMarket | None = None,
        market_prob_up: float = 0.5,
        market_spread: float = 0.02,
    ) -> Fill | None:
        """Process a completed bar: signal → size → filter → execute.

        Args:
            bar: The completed OHLCV bar.
            market: Polymarket market info (None during backtest).
            market_prob_up: Current Polymarket implied P(Up).
            market_spread: Current Polymarket spread.

        Returns:
            Fill if order was executed, None otherwise.
        """
        if not self._running:
            return None

        # 1. Generate signal
        t0 = time.perf_counter_ns()
        signal = self._signal_gen.generate(
            timestamp=bar.timestamp,
            asset=bar.asset,
            market_type=MarketType.FIVE_MIN,  # TODO: derive from bar.timeframe
            model_prob_up=market_prob_up,  # placeholder — real path uses model
            market_prob_up=market_prob_up,
            market_spread=market_spread,
        )

        if signal is None:
            return None

        SIGNALS_GENERATED.labels(
            asset=signal.asset.value,
            market_type=signal.market_type.value,
            side=signal.recommended_side.value,
        ).inc()
        EDGE_OBSERVED.observe(signal.edge)
        await self._audit.log_signal(signal)

        elapsed_ns = time.perf_counter_ns() - t0
        INFERENCE_LATENCY_NS.observe(elapsed_ns)

        # 2. Size the bet
        buy_price = market_prob_up if signal.recommended_side == Outcome.UP else (1 - market_prob_up)
        size_usd = self._sizer.size(signal.edge, buy_price, self._portfolio.available_cash)

        if size_usd <= 0:
            return None

        BET_SIZE_USD.observe(size_usd)

        # 3. Filter (includes risk checks)
        now = datetime.now(timezone.utc)
        ok, reason = self._filter.filter(
            signal=signal,
            size_usd=size_usd,
            portfolio=self._portfolio,
            market=market,
            now=now,
        )
        await self._audit.log_risk_check(signal, ok, reason)

        if not ok:
            return None

        # 4. Execute
        fill = await self._executor.execute(signal, size_usd, market)

        if fill.status == "filled":
            # Record position
            condition_id = market.condition_id if market else ""
            self._portfolio.on_fill(
                asset=signal.asset,
                side=signal.recommended_side,
                size_usd=fill.size_usd,
                fill_price=fill.price,
                condition_id=condition_id,
            )
            ORDERS_PLACED.labels(
                asset=signal.asset.value,
                outcome=signal.recommended_side.value,
            ).inc()
            await self._audit.log_fill(
                asset=signal.asset.value,
                side=signal.recommended_side.value,
                size=fill.size_usd,
                fill_price=fill.price,
            )

        return fill

    async def on_market_resolution(
        self, condition_id: str, outcome: Outcome
    ) -> float:
        """Handle market resolution. Returns total PnL from resolved positions."""
        pnl = self._portfolio.on_resolution(condition_id, outcome)

        # Track consecutive wins/losses for circuit breaker
        won = pnl > 0
        self._risk.circuit_breaker.record_trade_result(won)

        await self._audit.log_resolution(condition_id, outcome.value, pnl)
        return pnl

    def stop(self) -> None:
        """Stop accepting new trades."""
        self._running = False
