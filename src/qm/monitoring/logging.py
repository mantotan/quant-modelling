"""Structured logging configuration with secret redaction.

Dev mode: human-readable console output
Prod mode: JSON output for machine parsing
All modes: secrets are redacted from log output.
"""

from __future__ import annotations

import logging
import re
import sys

import structlog


# Pattern that matches common secret formats in log messages
_SECRET_PATTERN = re.compile(
    r"(?i)"
    r"("
    r"(?:api[_-]?key|api[_-]?secret|private[_-]?key|password|token|secret|bearer)"
    r")"
    r"(\s*[=:]\s*)"
    r"(\S+)",
)

# Also match raw hex strings that look like private keys (64 hex chars)
_HEX_KEY_PATTERN = re.compile(r"\b(0x)?[0-9a-fA-F]{64}\b")


def _redact_secrets(_, __, event_dict: dict) -> dict:
    """structlog processor that redacts secrets from log messages."""
    msg = event_dict.get("event", "")
    if isinstance(msg, str):
        msg = _SECRET_PATTERN.sub(r"\1\2***REDACTED***", msg)
        msg = _HEX_KEY_PATTERN.sub("***REDACTED_KEY***", msg)
        event_dict["event"] = msg

    # Also check extra fields
    for key in list(event_dict.keys()):
        if key in ("event", "timestamp", "level", "logger"):
            continue
        val = event_dict[key]
        if isinstance(val, str):
            val = _SECRET_PATTERN.sub(r"\1\2***REDACTED***", val)
            val = _HEX_KEY_PATTERN.sub("***REDACTED_KEY***", val)
            event_dict[key] = val

    return event_dict


def setup_logging(
    env: str = "dev",
    log_level: str = "INFO",
) -> None:
    """Configure structured logging for the application.

    Args:
        env: "dev" for console output, "prod" for JSON output.
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR).
    """
    shared_processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        _redact_secrets,
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    if env == "prod":
        renderer: structlog.types.Processor = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer(colors=True)

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(getattr(logging, log_level.upper(), logging.INFO))

    # Reduce noise from third-party libraries
    logging.getLogger("asyncio").setLevel(logging.WARNING)
    logging.getLogger("aiohttp").setLevel(logging.WARNING)
    logging.getLogger("ccxt").setLevel(logging.WARNING)
