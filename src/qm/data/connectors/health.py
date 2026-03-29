"""Connection health monitor for all data connectors."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from qm.core.events import DataGap, EventBus
from qm.core.types import Asset, Timeframe
from qm.data.connectors.base import BaseConnector

logger = logging.getLogger(__name__)


class HealthMonitor:
    """Periodically checks health of all registered connectors.

    Emits DataGap events when a connector is unhealthy.
    """

    def __init__(
        self,
        connectors: list[BaseConnector],
        event_bus: EventBus,
        check_interval: float = 10.0,
    ) -> None:
        self._connectors = connectors
        self._event_bus = event_bus
        self._check_interval = check_interval
        self._running = False
        self._task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        self._running = True
        self._task = asyncio.create_task(self._monitor_loop(), name="health-monitor")

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _monitor_loop(self) -> None:
        while self._running:
            for connector in self._connectors:
                if not connector.is_healthy():
                    logger.warning(
                        "Connector unhealthy",
                        extra={"connector": connector.name},
                    )
                    await self._event_bus.publish(
                        DataGap(
                            asset=Asset.BTC,  # generic — specific asset tracked per symbol
                            timeframe=Timeframe.M5,
                            expected_time=datetime.now(timezone.utc),
                            reason=f"Connector {connector.name} unhealthy",
                        )
                    )

            await asyncio.sleep(self._check_interval)

    def status(self) -> dict[str, bool]:
        """Get current health status of all connectors."""
        return {c.name: c.is_healthy() for c in self._connectors}
