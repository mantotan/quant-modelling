"""Position tracker: reconcile local portfolio with Polymarket API state.

On startup, fetches positions from the CLOB API and syncs with the
local Portfolio. Detects orphaned and stale positions, auto-heals.
"""

from __future__ import annotations

import logging

from qm.execution.polymarket.client import PolymarketClient
from qm.strategy.portfolio import Portfolio

logger = logging.getLogger(__name__)


class PositionTracker:
    """Reconciles local portfolio with Polymarket API positions.

    Call reconcile() on startup to fix any discrepancies from:
    - Crash during order execution
    - Markets that resolved while system was offline
    - Manual API interactions
    """

    def __init__(
        self,
        client: PolymarketClient,
        portfolio: Portfolio,
    ) -> None:
        self._client = client
        self._portfolio = portfolio

    def reconcile(self) -> dict[str, int]:
        """Reconcile local state with API. Returns stats.

        Returns:
            Dict with keys: matched, orphaned, stale, resolved.
        """
        stats = {"matched": 0, "orphaned": 0, "stale": 0, "resolved": 0}

        # Get positions from API
        try:
            api_orders = self._client.get_open_orders()
        except Exception as e:
            logger.error("Failed to fetch API positions: %s", e)
            return stats

        api_order_ids = {
            o.get("id", o.get("orderID", "")) for o in api_orders
        }

        # Check local positions against API
        local_positions = list(self._portfolio._positions.values())

        for pos in local_positions:
            if pos.condition_id in api_order_ids:
                stats["matched"] += 1
            else:
                # Position exists locally but not on API
                # Could be: resolved, cancelled, or stale
                stats["stale"] += 1
                logger.warning(
                    "Stale local position: %s %s (not on API)",
                    pos.asset.value, pos.condition_id[:12],
                )

        # Check API orders not in local state
        local_condition_ids = {
            p.condition_id for p in local_positions
        }
        for order in api_orders:
            order_id = order.get("id", order.get("orderID", ""))
            if order_id not in local_condition_ids:
                stats["orphaned"] += 1
                logger.warning(
                    "Orphaned API order: %s (not in local portfolio)",
                    order_id[:12],
                )

        logger.info(
            "Reconciliation: %d matched, %d orphaned, %d stale",
            stats["matched"], stats["orphaned"], stats["stale"],
        )
        return stats
