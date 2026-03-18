"""Append-only audit log writer.

Every trading decision is recorded immutably:
signals, risk checks, orders, fills, resolutions, state snapshots.
Async, non-blocking — writes happen AFTER the decision, never on the hot path.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)


class AuditWriter:
    """Writes audit events to TimescaleDB audit_log table.

    All methods are fire-and-forget: failures are logged but never block trading.
    """

    def __init__(self, db_writer: Any | None = None) -> None:
        """Args: db_writer — TimescaleWriter instance, or None for log-only mode."""
        self._writer = db_writer
        self._buffer: list[dict[str, Any]] = []

    async def log_signal(self, signal: Any) -> None:
        await self._write("signal", {
            "asset": signal.asset.value,
            "market_type": signal.market_type.value,
            "model_prob": signal.model_prob_up,
            "market_prob": signal.market_prob_up,
            "edge": signal.edge,
            "side": signal.recommended_side.value,
        })

    async def log_risk_check(
        self, signal: Any, passed: bool, reason: str
    ) -> None:
        await self._write("risk_check", {
            "asset": signal.asset.value,
            "passed": passed,
            "reason": reason,
        })

    async def log_order(
        self, asset: str, side: str, size: float, price: float, order_id: str = ""
    ) -> None:
        await self._write("order", {
            "asset": asset,
            "side": side,
            "size_usd": size,
            "price": price,
            "order_id": order_id,
        })

    async def log_fill(
        self, asset: str, side: str, size: float, fill_price: float, position_id: str = ""
    ) -> None:
        await self._write("fill", {
            "asset": asset,
            "side": side,
            "size_usd": size,
            "fill_price": fill_price,
            "position_id": position_id,
        })

    async def log_resolution(
        self, condition_id: str, outcome: str, pnl: float
    ) -> None:
        await self._write("resolution", {
            "condition_id": condition_id,
            "outcome": outcome,
            "pnl": pnl,
        })

    async def log_state_snapshot(self, portfolio_dict: dict[str, Any]) -> None:
        await self._write("state_snapshot", portfolio_dict)

    async def log_circuit_breaker(self, reason: str) -> None:
        await self._write("circuit_breaker_trip", {"reason": reason})

    async def _write(self, event_type: str, details: dict[str, Any]) -> None:
        """Write to DB if available, always log."""
        ts = datetime.now(timezone.utc)
        asset = details.get("asset")
        market_type = details.get("market_type")

        if self._writer:
            try:
                await self._writer.write_audit(
                    event_type=event_type,
                    asset=asset,
                    market_type=market_type,
                    details=json.dumps(details, default=str),
                    time=ts,
                )
            except Exception:
                logger.exception("Audit write failed for %s", event_type)
                # Buffer for retry (bounded)
                if len(self._buffer) < 1000:
                    self._buffer.append({
                        "time": ts, "event_type": event_type, "details": details
                    })

    async def flush_buffer(self) -> int:
        """Retry buffered writes. Returns count flushed."""
        if not self._buffer or not self._writer:
            return 0

        flushed = 0
        remaining = []
        for entry in self._buffer:
            try:
                await self._writer.write_audit(
                    event_type=entry["event_type"],
                    details=json.dumps(entry["details"], default=str),
                    time=entry["time"],
                )
                flushed += 1
            except Exception:
                remaining.append(entry)

        self._buffer = remaining
        if flushed:
            logger.info("Flushed %d buffered audit entries", flushed)
        return flushed
