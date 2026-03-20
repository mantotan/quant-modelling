"""Append-only JSONL logger for paper trade events.

Captures every input needed for backtest replay:
model predictions, real market odds, features, fills, resolutions.
Fire-and-forget — failures are logged but never block trading.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class PaperTradeLogger:
    """Writes paper trade events to daily-rotated JSONL files.

    Output: data/paper_trades/{asset}_{tf}/trades_{YYYY-MM-DD}.jsonl
    One JSON line per event (prediction or resolution).
    """

    def __init__(self, base_dir: Path, asset: str, timeframe: str) -> None:
        self._dir = base_dir / f"{asset}_{timeframe}"
        self._dir.mkdir(parents=True, exist_ok=True)
        self._asset = asset
        self._timeframe = timeframe
        self._current_date: date | None = None
        self._fh: Any = None

    def log_prediction(
        self,
        *,
        bar_id: int,
        elapsed_pct: float,
        model_prob: float,
        market_prob: float,
        market_spread: float,
        condition_id: str,
        features: list[float],
        signal_edge: float,
        signal_side: str,
        size_usd: float,
        fill_price: float,
        fill_status: str,
    ) -> None:
        self._write({
            "type": "prediction",
            "ts": datetime.now(UTC).isoformat(),
            "bar_id": bar_id,
            "elapsed_pct": round(elapsed_pct, 4),
            "asset": self._asset,
            "timeframe": self._timeframe,
            "condition_id": condition_id,
            "model_prob": round(model_prob, 6),
            "market_prob": round(market_prob, 6),
            "market_spread": round(market_spread, 6),
            "features": [round(f, 6) for f in features],
            "signal_edge": round(signal_edge, 6),
            "signal_side": signal_side,
            "size_usd": round(size_usd, 4),
            "fill_price": round(fill_price, 6),
            "fill_status": fill_status,
        })

    def log_resolution(
        self,
        *,
        condition_id: str,
        outcome: str,
        pnl: float,
        was_correct: bool,
        position_id: str = "",
    ) -> None:
        event: dict = {
            "type": "resolution",
            "ts": datetime.now(UTC).isoformat(),
            "condition_id": condition_id,
            "outcome": outcome,
            "pnl": round(pnl, 4),
            "was_correct": was_correct,
        }
        if position_id:
            event["position_id"] = position_id
        self._write(event)

    def _write(self, event: dict) -> None:
        """Append one JSON line. Rotates file daily."""
        try:
            today = date.today()
            if today != self._current_date:
                self._rotate(today)
            assert self._fh is not None
            self._fh.write(json.dumps(event, separators=(",", ":")) + "\n")
            self._fh.flush()
        except Exception:
            logger.exception("PaperTradeLogger write failed")

    def _rotate(self, today: date) -> None:
        if self._fh is not None:
            self._fh.close()
        path = self._dir / f"trades_{today.isoformat()}.jsonl"
        self._fh = open(path, "a", encoding="utf-8")  # noqa: SIM115
        self._current_date = today
        logger.info("Paper trade log: %s", path)

    def close(self) -> None:
        if self._fh is not None:
            self._fh.close()
            self._fh = None
