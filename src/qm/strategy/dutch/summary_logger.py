"""Per-bar summary logger for dutch accumulation paper trading.

Writes structured JSONL output designed for AI review:
  - One line per bar with full decision trace
  - Daily rotation (same pattern as PaperTradeLogger)
  - Fire-and-forget: failures logged but never block trading
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path

from qm.strategy.dutch.engine import DutchBarSummary

logger = logging.getLogger(__name__)


class DutchSummaryLogger:
    """Append-only JSONL logger for dutch bar summaries."""

    def __init__(
        self,
        base_dir: Path,
        asset: str = "BTC",
        timeframe: str = "15m",
    ) -> None:
        self._dir = base_dir / f"{asset}_{timeframe}"
        self._dir.mkdir(parents=True, exist_ok=True)
        self._asset = asset
        self._timeframe = timeframe
        self._bar_file = None
        self._bar_date: str = ""
        self._tick_file = None
        self._tick_date: str = ""
        self._event_file = None
        self._event_date: str = ""

    def log_bar(self, summary: DutchBarSummary) -> None:
        """Append a bar summary to the daily JSONL file."""
        try:
            today = datetime.now(UTC).strftime("%Y-%m-%d")
            if today != self._bar_date:
                self._rotate_bar_file(today)

            line = json.dumps(summary.to_dict(), default=str)
            self._bar_file.write(line + "\n")
            self._bar_file.flush()
        except Exception as e:
            logger.warning("Failed to log dutch bar summary: %s", e)

    def log_tick(self, bar_id: int, tick_data: dict) -> None:
        """Append a per-tick snapshot to the daily tick log."""
        try:
            today = datetime.now(UTC).strftime("%Y-%m-%d")
            if today != self._tick_date:
                self._rotate_tick_file(today)

            record = {"bar_id": bar_id, "ts": datetime.now(UTC).isoformat(), **tick_data}
            self._tick_file.write(json.dumps(record, default=str) + "\n")
            self._tick_file.flush()
        except Exception as e:
            logger.warning("Failed to log dutch tick: %s", e)

    def log_event(self, event: dict) -> None:
        """Log a single action event. Compact: ~10-50 events per bar."""
        try:
            today = datetime.now(UTC).strftime("%Y-%m-%d")
            if today != self._event_date:
                self._rotate_event_file(today)

            event["ts"] = datetime.now(UTC).isoformat()
            self._event_file.write(json.dumps(event, default=str) + "\n")
            self._event_file.flush()
        except Exception as e:
            logger.warning("Failed to log dutch event: %s", e)

    def _rotate_event_file(self, date_str: str) -> None:
        if self._event_file is not None:
            self._event_file.close()
        path = self._dir / f"events_{date_str}.jsonl"
        self._event_file = open(path, "a")  # noqa: SIM115
        self._event_date = date_str
        logger.info("Dutch event log: %s", path)

    def _rotate_bar_file(self, date_str: str) -> None:
        if self._bar_file is not None:
            self._bar_file.close()
        path = self._dir / f"bars_{date_str}.jsonl"
        self._bar_file = open(path, "a")  # noqa: SIM115
        self._bar_date = date_str
        logger.info("Dutch bar log: %s", path)

    def _rotate_tick_file(self, date_str: str) -> None:
        if self._tick_file is not None:
            self._tick_file.close()
        path = self._dir / f"ticks_{date_str}.jsonl"
        self._tick_file = open(path, "a")  # noqa: SIM115
        self._tick_date = date_str
        logger.info("Dutch tick log: %s", path)

    def close(self) -> None:
        if self._bar_file is not None:
            self._bar_file.close()
            self._bar_file = None
        if self._tick_file is not None:
            self._tick_file.close()
            self._tick_file = None
        if self._event_file is not None:
            self._event_file.close()
            self._event_file = None
