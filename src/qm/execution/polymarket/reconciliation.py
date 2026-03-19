"""Startup reconciliation: restore state after crash or restart.

Loads persisted Portfolio JSON, reconciles with Polymarket API,
detects markets that resolved while system was offline.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from qm.core.types import Outcome
from qm.execution.polymarket.market_scanner import MarketScanner
from qm.execution.polymarket.position_tracker import PositionTracker
from qm.risk.bankroll import Bankroll
from qm.strategy.portfolio import Portfolio

logger = logging.getLogger(__name__)


async def reconcile_on_startup(
    state_file: Path,
    portfolio: Portfolio,
    tracker: PositionTracker | None = None,
    scanner: MarketScanner | None = None,
) -> dict[str, int]:
    """Full startup reconciliation sequence.

    1. Load persisted Portfolio state from JSON
    2. Reconcile with Polymarket API (if tracker provided)
    3. Resolve any markets that settled while offline

    Args:
        state_file: Path to portfolio state JSON.
        portfolio: Portfolio to restore into.
        tracker: Position tracker for API reconciliation.
        scanner: Market scanner for resolution detection.

    Returns:
        Stats dict: loaded, reconciled, resolved.
    """
    stats = {"loaded": 0, "reconciled": 0, "resolved": 0}

    # 1. Load persisted state
    if state_file.exists():
        try:
            with open(state_file) as f:
                state = json.load(f)

            # Restore bankroll
            if "bankroll" in state:
                br = Bankroll.from_dict(state["bankroll"])
                portfolio.bankroll.current = br.current
                portfolio.bankroll.high_water_mark = br.high_water_mark
                portfolio.bankroll.total_realized_pnl = br.total_realized_pnl
                stats["loaded"] = 1
                logger.info(
                    "Restored bankroll: $%.2f (HWM $%.2f)",
                    br.current, br.high_water_mark,
                )
        except Exception as e:
            logger.warning("Failed to load state from %s: %s", state_file, e)
    else:
        logger.info("No state file at %s — starting fresh", state_file)

    # 2. Reconcile with API
    if tracker is not None:
        try:
            recon_stats = tracker.reconcile()
            stats["reconciled"] = recon_stats.get("matched", 0)
        except Exception as e:
            logger.warning("API reconciliation failed: %s", e)

    # 3. Check for offline resolutions
    if scanner is not None:
        positions = list(portfolio._positions.values())
        for pos in positions:
            try:
                market_info = await scanner.get_market_status(
                    pos.condition_id,
                )
                if market_info and market_info.get("resolved", False):
                    outcome_str = market_info.get("outcome", "")
                    if outcome_str.lower() in ("up", "yes"):
                        outcome = Outcome.UP
                    else:
                        outcome = Outcome.DOWN

                    pnl = portfolio.on_resolution(pos.condition_id, outcome)
                    stats["resolved"] += 1
                    logger.info(
                        "Offline resolution: %s %s → %s (PnL $%.2f)",
                        pos.asset.value, pos.condition_id[:12],
                        outcome.value, pnl,
                    )
            except Exception as e:
                logger.warning(
                    "Resolution check failed for %s: %s",
                    pos.condition_id[:12], e,
                )

    logger.info(
        "Reconciliation complete: loaded=%d, reconciled=%d, resolved=%d",
        stats["loaded"], stats["reconciled"], stats["resolved"],
    )
    return stats
