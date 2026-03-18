"""Secret loading with fallback hierarchy: env vars → keyring → .env file.

NEVER log secret values. This module is the only place secrets are accessed.
"""

from __future__ import annotations

import logging
import os
from functools import lru_cache

logger = logging.getLogger(__name__)

# Secrets that must exist for production
REQUIRED_SECRETS = [
    "POLYMARKET_PRIVATE_KEY",
    "POLYMARKET_API_KEY",
    "TIMESCALEDB_URL",
]

# Secrets needed for exchange data (read-only)
EXCHANGE_SECRETS = [
    "BINANCE_API_KEY",
    "BINANCE_API_SECRET",
    "BYBIT_API_KEY",
    "BYBIT_API_SECRET",
]


@lru_cache(maxsize=1)
def _load_dotenv_once() -> None:
    """Load .env file once at startup."""
    try:
        from dotenv import load_dotenv

        load_dotenv()
        logger.info("Loaded .env file")
    except ImportError:
        logger.debug("python-dotenv not installed, skipping .env")
    except Exception:
        logger.debug("No .env file found")


def get_secret(name: str, required: bool = True) -> str | None:
    """Load a secret value. Tries env var first, then keyring, then .env file.

    Args:
        name: The secret name (e.g., 'POLYMARKET_PRIVATE_KEY')
        required: If True, raises ValueError when secret is not found

    Returns:
        The secret value, or None if not found and not required.
    """
    # Ensure .env is loaded before checking env vars
    _load_dotenv_once()

    # 1. Environment variable (highest priority)
    value = os.environ.get(name)
    if value is not None:
        return value

    # 2. System keyring
    try:
        import keyring

        value = keyring.get_password("qm", name)
        if value is not None:
            return value
    except Exception:
        pass  # keyring not available or not configured

    if required:
        msg = (
            f"Secret '{name}' not found. Set it as an environment variable, "
            f"store it in system keyring under service 'qm', "
            f"or add it to .env file."
        )
        raise ValueError(msg)

    return None


def validate_required_secrets(production: bool = False) -> list[str]:
    """Check that required secrets are available. Returns list of missing ones."""
    missing = []
    secrets_to_check = REQUIRED_SECRETS if production else ["TIMESCALEDB_URL"]
    for name in secrets_to_check:
        if get_secret(name, required=False) is None:
            missing.append(name)
    return missing
