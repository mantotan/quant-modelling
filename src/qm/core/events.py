"""Typed event bus for decoupled pub/sub between components."""

from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable, Coroutine

from qm.core.types import Asset, Bar, PartialBar, Timeframe

logger = logging.getLogger(__name__)

# Event types
EventHandler = Callable[..., Coroutine[Any, Any, None]]


@dataclass(frozen=True, slots=True)
class BarCompleted:
    bar: Bar


@dataclass(frozen=True, slots=True)
class DataGap:
    asset: Asset
    timeframe: Timeframe
    expected_time: datetime
    reason: str


@dataclass(frozen=True, slots=True)
class SignalGenerated:
    signal: object  # Signal type — avoids circular import


@dataclass(frozen=True, slots=True)
class OrderPlaced:
    order_id: str
    asset: Asset
    side: str
    size: float
    price: float


@dataclass(frozen=True, slots=True)
class PartialBarUpdated:
    partial_bar: PartialBar


@dataclass(frozen=True, slots=True)
class CircuitBreakerTrip:
    reason: str
    timestamp: datetime


# Simple typed event bus
class EventBus:
    """Async event bus. Components publish events, subscribers react."""

    def __init__(self) -> None:
        self._handlers: dict[type, list[EventHandler]] = defaultdict(list)
        self._background_tasks: set[asyncio.Task[None]] = set()

    def subscribe(self, event_type: type, handler: EventHandler) -> None:
        self._handlers[event_type].append(handler)

    async def publish(self, event: object) -> None:
        handlers = self._handlers.get(type(event), [])
        for handler in handlers:
            try:
                await handler(event)
            except Exception:
                logger.exception(
                    "Event handler failed",
                    extra={"event_type": type(event).__name__},
                )

    def publish_nowait(self, event: object) -> None:
        """Fire-and-forget publish for non-critical events.

        Task is stored to prevent GC before completion.
        """
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            logger.warning("No running event loop, dropping event %s", type(event).__name__)
            return
        task = loop.create_task(self.publish(event))
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)
