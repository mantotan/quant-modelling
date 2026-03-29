"""Trade investigation logger — detailed order-level JSONL for post-mortem analysis.

Every live order gets a full record with: CLOB order ID, book state at order time,
API latency, model prediction, and whether paper trading would have filled.
Enables replaying any losing trade to understand exactly what happened.
"""

from __future__ import annotations

import atexit
import json
import logging
from datetime import UTC, datetime
from pathlib import Path

logger = logging.getLogger(__name__)


class TradeLogger:
    """Detailed order-level JSONL logger for live trade investigation.

    Output: data/divergence_live/{PAIR}/trades_{DATE}.jsonl
    """

    def __init__(self, base_dir: Path, asset: str, timeframe: str) -> None:
        self._dir = base_dir / f"{asset}_{timeframe}"
        self._dir.mkdir(parents=True, exist_ok=True)
        self._current_date: str = ""
        self._file = None
        atexit.register(self.close)

    def _get_file(self):
        today = datetime.now(UTC).strftime("%Y-%m-%d")
        if today != self._current_date:
            if self._file:
                self._file.close()
            self._current_date = today
            path = self._dir / f"trades_{today}.jsonl"
            self._file = open(path, "a")  # noqa: SIM115
        return self._file

    def _write(self, record: dict) -> None:
        try:
            f = self._get_file()
            record["ts"] = datetime.now(UTC).isoformat()
            f.write(json.dumps(record, default=str) + "\n")
            f.flush()
        except Exception as e:
            logger.debug("Trade log write failed: %s", e)

    def log_order_placed(
        self,
        *,
        bar_id: int,
        clob_order_id: str,
        side: str,
        action: str,
        limit_price: float,
        shares: float,
        dollars: float,
        edge: float,
        cal_prob: float,
        book_bid: float,
        book_ask: float,
        book_depth: float,
        time_pct: float,
        api_latency_ms: float,
        paper_would_fill: bool | None = None,
    ) -> None:
        self._write({
            "type": "order_placed",
            "bar_id": bar_id,
            "clob_order_id": clob_order_id,
            "side": side,
            "action": action,
            "limit_price": round(limit_price, 4),
            "shares": round(shares, 4),
            "dollars": round(dollars, 4),
            "edge": round(edge, 4),
            "cal_prob": round(cal_prob, 4),
            "book_bid": round(book_bid, 4),
            "book_ask": round(book_ask, 4),
            "book_depth": round(book_depth, 1),
            "time_pct": round(time_pct, 4),
            "api_latency_ms": round(api_latency_ms, 1),
            "paper_would_fill": paper_would_fill,
        })

    def log_order_filled(
        self,
        *,
        bar_id: int,
        clob_order_id: str,
        fill_price: float,
        filled_shares: float,
        fill_latency_ms: float = 0,
    ) -> None:
        self._write({
            "type": "order_filled",
            "bar_id": bar_id,
            "clob_order_id": clob_order_id,
            "fill_price": round(fill_price, 4),
            "filled_shares": round(filled_shares, 4),
            "fill_latency_ms": round(fill_latency_ms, 1),
        })

    def log_order_cancelled(
        self,
        *,
        bar_id: int,
        clob_order_id: str,
        reason: str,
    ) -> None:
        self._write({
            "type": "order_cancelled",
            "bar_id": bar_id,
            "clob_order_id": clob_order_id,
            "reason": reason,
        })

    def log_bar_summary(
        self,
        *,
        bar_id: int,
        pair: str,
        outcome: str,
        paper_pnl: float,
        live_pnl: float,
        paper_fills: int,
        live_fills: int,
        live_cost: float,
        safety_status: dict | None = None,
    ) -> None:
        self._write({
            "type": "bar_summary",
            "bar_id": bar_id,
            "pair": pair,
            "outcome": outcome,
            "paper_pnl": round(paper_pnl, 4),
            "live_pnl": round(live_pnl, 4),
            "paper_fills": paper_fills,
            "live_fills": live_fills,
            "live_cost": round(live_cost, 4),
            "parity_ratio": round(live_pnl / paper_pnl, 3) if paper_pnl != 0 else 0,
            "safety": safety_status,
        })

    def log_safety_event(
        self,
        *,
        bar_id: int,
        event: str,
        details: str,
    ) -> None:
        self._write({
            "type": "safety_event",
            "bar_id": bar_id,
            "event": event,
            "details": details,
        })

    def close(self) -> None:
        if self._file:
            self._file.close()
            self._file = None
