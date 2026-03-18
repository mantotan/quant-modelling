"""Alert dispatch to Slack webhook with deduplication.

Alerts are deduped within a time window to prevent spam.
"""

from __future__ import annotations

import logging
import time
from typing import Any

import aiohttp

logger = logging.getLogger(__name__)

# Alert severity levels
CRITICAL = "critical"
WARNING = "warning"
INFO = "info"

# Dedup window in seconds (same title within this window = skip)
_DEDUP_WINDOW = 300  # 5 minutes


class AlertManager:
    """Sends alerts to Slack webhook with deduplication.

    Args:
        webhook_url: Slack incoming webhook URL. If None, alerts are logged only.
        dedup_window: Seconds to suppress duplicate alerts with the same title.
    """

    def __init__(
        self,
        webhook_url: str | None = None,
        dedup_window: int = _DEDUP_WINDOW,
    ) -> None:
        self._webhook_url = webhook_url
        self._dedup_window = dedup_window
        self._recent_alerts: dict[str, float] = {}  # title → last_sent_time

    async def send(
        self,
        severity: str,
        title: str,
        message: str,
        fields: dict[str, Any] | None = None,
    ) -> bool:
        """Send an alert. Returns True if actually sent (not deduped).

        Args:
            severity: One of CRITICAL, WARNING, INFO.
            title: Short alert title (used for dedup key).
            message: Detailed alert body.
            fields: Optional key-value pairs for context.
        """
        # Dedup check
        now = time.monotonic()
        if title in self._recent_alerts:
            last_sent = self._recent_alerts[title]
            if now - last_sent < self._dedup_window:
                logger.debug("Alert deduped: %s", title)
                return False

        self._recent_alerts[title] = now

        # Clean old entries
        self._recent_alerts = {
            k: v for k, v in self._recent_alerts.items()
            if now - v < self._dedup_window * 2
        }

        # Always log
        log_level = logging.CRITICAL if severity == CRITICAL else (
            logging.WARNING if severity == WARNING else logging.INFO
        )
        logger.log(log_level, "ALERT [%s] %s: %s", severity.upper(), title, message)

        # Send to Slack if configured
        if self._webhook_url:
            try:
                await self._send_slack(severity, title, message, fields)
            except Exception:
                logger.exception("Failed to send Slack alert")

        return True

    async def _send_slack(
        self,
        severity: str,
        title: str,
        message: str,
        fields: dict[str, Any] | None = None,
    ) -> None:
        """Send alert to Slack incoming webhook."""
        color = {"critical": "#FF0000", "warning": "#FFA500", "info": "#0000FF"}.get(
            severity, "#808080"
        )

        attachment: dict[str, Any] = {
            "color": color,
            "title": f"[{severity.upper()}] {title}",
            "text": message,
            "ts": int(time.time()),
        }

        if fields:
            attachment["fields"] = [
                {"title": k, "value": str(v), "short": True}
                for k, v in fields.items()
            ]

        payload = {"attachments": [attachment]}

        async with aiohttp.ClientSession() as session:
            async with session.post(self._webhook_url, json=payload) as resp:
                if resp.status != 200:
                    logger.warning("Slack webhook returned %d", resp.status)
