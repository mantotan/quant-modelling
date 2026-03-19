"""Model drift monitoring and retraining trigger system.

Tracks rolling Brier scores per asset on live predictions and raises alerts
when drift thresholds are breached. Implements the DEPLOY-4 retraining cadence
policy from the strategy directive (iter 57).

Retraining triggers:
  - Mandatory: rolling 30-day OOS Brier exceeds 1.2x the validation floor.
  - Scheduled: 90-day (quarterly) forced retrain regardless of drift metrics.
  - Emergency: structural market break — external manual trigger via force_retrain().
  - BTC-specific: regime monotonicity violation (crisis Sharpe < normal Sharpe).

Validation floors (from autoresearch iterations):
  BTC: 0.101759 (iter 22)  -> mandatory threshold: 0.12211
  ETH: 0.177772 (iter 32)  -> mandatory threshold: 0.21333
  SOL: 0.189372 (iter 39)  -> mandatory threshold: 0.22725
  XRP: 0.195309 (iter 53)  -> mandatory threshold: 0.23437
"""

from __future__ import annotations

import logging
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any

from qm.core.types import Asset, RegimeState

logger = logging.getLogger(__name__)

# ── Validation floors (from autoresearch) ─────────────────────────────

VALIDATION_FLOORS: dict[Asset, float] = {
    Asset.BTC: 0.101759,
    Asset.ETH: 0.177772,
    Asset.SOL: 0.189372,
    Asset.XRP: 0.195309,
}

# Mandatory retrain if rolling Brier > floor * DRIFT_MULTIPLIER
DRIFT_MULTIPLIER: float = 1.2

# Scheduled retrain interval
SCHEDULED_RETRAIN_DAYS: int = 90

# Rolling window size for Brier computation
ROLLING_WINDOW_DAYS: int = 30


class RetrainReason(str, Enum):
    """Reason a retrain was triggered."""

    DRIFT = "drift"  # Rolling Brier exceeded 1.2x floor
    SCHEDULED = "scheduled"  # 90-day quarterly retrain
    EMERGENCY = "emergency"  # Manual structural break trigger
    REGIME_MONOTONICITY = "regime_monotonicity"  # BTC: crisis < normal Sharpe


@dataclass(frozen=True, slots=True)
class Prediction:
    """A single live prediction with its outcome."""

    timestamp: datetime
    asset: Asset
    prob_up: float  # Model's predicted P(Up)
    outcome: float  # 1.0 if Up, 0.0 if Down
    regime: RegimeState | None = None  # For BTC regime monitoring
    sharpe_contribution: float | None = None  # Per-trade Sharpe for regime bucketing


@dataclass(frozen=True, slots=True)
class RetrainSignal:
    """Signal that a retrain should be triggered."""

    asset: Asset
    reason: RetrainReason
    triggered_at: datetime
    rolling_brier: float | None = None
    threshold: float | None = None
    details: str = ""


@dataclass
class AssetDriftState:
    """Per-asset drift tracking state."""

    predictions: deque[Prediction] = field(default_factory=deque)
    last_retrain: datetime | None = None
    last_deploy: datetime | None = None
    regime_sharpes: dict[RegimeState, list[float]] = field(default_factory=dict)

    def rolling_brier(self, window_days: int = ROLLING_WINDOW_DAYS) -> float | None:
        """Compute rolling Brier score over the last N days."""
        if not self.predictions:
            return None

        cutoff = datetime.now(timezone.utc) - timedelta(days=window_days)
        recent = [p for p in self.predictions if p.timestamp >= cutoff]

        if len(recent) < 50:  # Minimum sample size for meaningful Brier
            return None

        brier = sum(
            (p.prob_up - p.outcome) ** 2 for p in recent
        ) / len(recent)
        return brier

    def rolling_ece(self, n_bins: int = 10, window_days: int = ROLLING_WINDOW_DAYS) -> float | None:
        """Compute rolling ECE over the last N days."""
        cutoff = datetime.now(timezone.utc) - timedelta(days=window_days)
        recent = [p for p in self.predictions if p.timestamp >= cutoff]

        if len(recent) < 50:
            return None

        # Bin predictions by predicted probability
        bins: list[list[Prediction]] = [[] for _ in range(n_bins)]
        for p in recent:
            idx = min(int(p.prob_up * n_bins), n_bins - 1)
            bins[idx].append(p)

        ece = 0.0
        total = len(recent)
        for bin_preds in bins:
            if not bin_preds:
                continue
            avg_pred = sum(p.prob_up for p in bin_preds) / len(bin_preds)
            avg_outcome = sum(p.outcome for p in bin_preds) / len(bin_preds)
            ece += len(bin_preds) / total * abs(avg_pred - avg_outcome)

        return ece

    def prediction_count(self, window_days: int = ROLLING_WINDOW_DAYS) -> int:
        """Count predictions in the rolling window."""
        cutoff = datetime.now(timezone.utc) - timedelta(days=window_days)
        return sum(1 for p in self.predictions if p.timestamp >= cutoff)

    def prune_old(self, max_days: int = 120) -> int:
        """Remove predictions older than max_days. Returns count removed."""
        cutoff = datetime.now(timezone.utc) - timedelta(days=max_days)
        original = len(self.predictions)
        while self.predictions and self.predictions[0].timestamp < cutoff:
            self.predictions.popleft()
        return original - len(self.predictions)


class DriftMonitor:
    """Monitors model drift and triggers retraining.

    Usage:
        monitor = DriftMonitor()
        monitor.record_prediction(prediction)
        signals = monitor.check_triggers()
        for signal in signals:
            if signal.reason == RetrainReason.DRIFT:
                # Trigger retraining pipeline
                ...

    Args:
        validation_floors: Per-asset Brier validation floors. Defaults to autoresearch values.
        drift_multiplier: Retrain when rolling Brier > floor * multiplier. Default 1.2.
        scheduled_days: Days between scheduled retrains. Default 90.
        rolling_window_days: Days in the rolling Brier window. Default 30.
        min_predictions: Minimum predictions before drift checks activate. Default 50.
    """

    def __init__(
        self,
        validation_floors: dict[Asset, float] | None = None,
        drift_multiplier: float = DRIFT_MULTIPLIER,
        scheduled_days: int = SCHEDULED_RETRAIN_DAYS,
        rolling_window_days: int = ROLLING_WINDOW_DAYS,
        min_predictions: int = 50,
    ) -> None:
        self._floors = validation_floors or dict(VALIDATION_FLOORS)
        self._drift_multiplier = drift_multiplier
        self._scheduled_days = scheduled_days
        self._rolling_window_days = rolling_window_days
        self._min_predictions = min_predictions
        self._states: dict[Asset, AssetDriftState] = {}
        self._pending_signals: list[RetrainSignal] = []

    def _get_state(self, asset: Asset) -> AssetDriftState:
        """Get or create per-asset state."""
        if asset not in self._states:
            self._states[asset] = AssetDriftState()
        return self._states[asset]

    def record_prediction(self, prediction: Prediction) -> None:
        """Record a live prediction for drift tracking.

        Args:
            prediction: A completed prediction with known outcome.
        """
        state = self._get_state(prediction.asset)
        state.predictions.append(prediction)

        # Track regime-level Sharpe contributions for BTC monotonicity check
        if prediction.regime is not None and prediction.sharpe_contribution is not None:
            if prediction.regime not in state.regime_sharpes:
                state.regime_sharpes[prediction.regime] = []
            state.regime_sharpes[prediction.regime].append(prediction.sharpe_contribution)

    def record_deploy(self, asset: Asset, deploy_time: datetime | None = None) -> None:
        """Record when a model was deployed (starts the scheduled retrain clock)."""
        state = self._get_state(asset)
        state.last_deploy = deploy_time or datetime.now(timezone.utc)

    def record_retrain(self, asset: Asset, retrain_time: datetime | None = None) -> None:
        """Record that a retrain occurred (resets the scheduled retrain clock)."""
        state = self._get_state(asset)
        state.last_retrain = retrain_time or datetime.now(timezone.utc)

    def force_retrain(self, asset: Asset, details: str = "") -> RetrainSignal:
        """Manually trigger an emergency retrain signal.

        Use for structural market breaks (new exchange mechanism, major protocol
        changes, BTC halving period).

        Args:
            asset: Asset to retrain.
            details: Human-readable reason for the emergency retrain.
        """
        signal = RetrainSignal(
            asset=asset,
            reason=RetrainReason.EMERGENCY,
            triggered_at=datetime.now(timezone.utc),
            details=details or f"Emergency retrain requested for {asset.value}",
        )
        self._pending_signals.append(signal)
        logger.critical(
            "EMERGENCY retrain triggered for %s: %s",
            asset.value,
            signal.details,
        )
        return signal

    def check_triggers(self, now: datetime | None = None) -> list[RetrainSignal]:
        """Check all retrain triggers across all tracked assets.

        Returns a list of retrain signals (may be empty if no triggers fired).
        Should be called periodically (e.g., every bar or every hour).
        """
        now = now or datetime.now(timezone.utc)
        signals: list[RetrainSignal] = []

        # Drain any pending signals (from force_retrain)
        signals.extend(self._pending_signals)
        self._pending_signals.clear()

        for asset in self._floors:
            state = self._get_state(asset)

            # 1. Drift check: rolling Brier > 1.2x floor
            drift_signal = self._check_drift(asset, state, now)
            if drift_signal:
                signals.append(drift_signal)

            # 2. Scheduled retrain: 90-day quarterly
            sched_signal = self._check_scheduled(asset, state, now)
            if sched_signal:
                signals.append(sched_signal)

            # 3. BTC-specific: regime monotonicity
            if asset == Asset.BTC:
                regime_signal = self._check_regime_monotonicity(asset, state, now)
                if regime_signal:
                    signals.append(regime_signal)

            # Housekeeping: prune old predictions
            pruned = state.prune_old()
            if pruned > 0:
                logger.debug("Pruned %d old predictions for %s", pruned, asset.value)

        return signals

    def _check_drift(
        self, asset: Asset, state: AssetDriftState, now: datetime
    ) -> RetrainSignal | None:
        """Check if rolling Brier exceeds drift threshold."""
        if state.prediction_count(self._rolling_window_days) < self._min_predictions:
            return None

        brier = state.rolling_brier(self._rolling_window_days)
        if brier is None:
            return None

        floor = self._floors[asset]
        threshold = floor * self._drift_multiplier

        if brier > threshold:
            signal = RetrainSignal(
                asset=asset,
                reason=RetrainReason.DRIFT,
                triggered_at=now,
                rolling_brier=brier,
                threshold=threshold,
                details=(
                    f"{asset.value} rolling {self._rolling_window_days}d Brier "
                    f"{brier:.6f} > threshold {threshold:.6f} "
                    f"(floor {floor:.6f} x {self._drift_multiplier})"
                ),
            )
            logger.warning(
                "DRIFT detected for %s: Brier %.6f > %.6f",
                asset.value,
                brier,
                threshold,
            )
            return signal

        return None

    def _check_scheduled(
        self, asset: Asset, state: AssetDriftState, now: datetime
    ) -> RetrainSignal | None:
        """Check if scheduled retrain is due."""
        reference = state.last_retrain or state.last_deploy
        if reference is None:
            return None

        elapsed = now - reference
        if elapsed >= timedelta(days=self._scheduled_days):
            signal = RetrainSignal(
                asset=asset,
                reason=RetrainReason.SCHEDULED,
                triggered_at=now,
                details=(
                    f"{asset.value} scheduled {self._scheduled_days}-day retrain "
                    f"(last: {reference.isoformat()}, elapsed: {elapsed.days}d)"
                ),
            )
            logger.info(
                "Scheduled retrain due for %s (%d days since last)",
                asset.value,
                elapsed.days,
            )
            return signal

        return None

    def _check_regime_monotonicity(
        self, asset: Asset, state: AssetDriftState, now: datetime
    ) -> RetrainSignal | None:
        """Check BTC regime monotonicity: crisis Sharpe must exceed normal Sharpe.

        From strategy directive: BTC edge monotonically increases with volatility
        (low 92 < normal 114 < high 138 < crisis 168). If this monotonicity breaks,
        it's a model drift signal regardless of absolute Brier.

        Requires at least 30 trades per regime bucket before activating.
        """
        min_trades_per_bucket = 30

        normal_sharpes = state.regime_sharpes.get(RegimeState.NORMAL, [])
        crisis_sharpes = state.regime_sharpes.get(RegimeState.CRISIS, [])

        if len(normal_sharpes) < min_trades_per_bucket or len(crisis_sharpes) < min_trades_per_bucket:
            return None

        # Compare mean Sharpe contributions
        normal_mean = sum(normal_sharpes) / len(normal_sharpes)
        crisis_mean = sum(crisis_sharpes) / len(crisis_sharpes)

        if crisis_mean < normal_mean:
            signal = RetrainSignal(
                asset=asset,
                reason=RetrainReason.REGIME_MONOTONICITY,
                triggered_at=now,
                details=(
                    f"BTC regime monotonicity violated: crisis Sharpe {crisis_mean:.2f} "
                    f"< normal Sharpe {normal_mean:.2f} "
                    f"(n_crisis={len(crisis_sharpes)}, n_normal={len(normal_sharpes)})"
                ),
            )
            logger.warning(
                "REGIME MONOTONICITY violation for BTC: crisis %.2f < normal %.2f",
                crisis_mean,
                normal_mean,
            )
            return signal

        return None

    def get_status(self, asset: Asset) -> dict[str, Any]:
        """Get current drift monitoring status for an asset.

        Returns a dict suitable for Prometheus metrics or JSON serialization.
        """
        state = self._get_state(asset)
        floor = self._floors.get(asset, 0.0)
        threshold = floor * self._drift_multiplier
        brier = state.rolling_brier(self._rolling_window_days)
        ece = state.rolling_ece(window_days=self._rolling_window_days)
        count = state.prediction_count(self._rolling_window_days)

        reference = state.last_retrain or state.last_deploy
        days_since_retrain = (
            (datetime.now(timezone.utc) - reference).days if reference else None
        )

        return {
            "asset": asset.value,
            "rolling_brier": brier,
            "rolling_ece": ece,
            "drift_threshold": threshold,
            "validation_floor": floor,
            "prediction_count": count,
            "days_since_retrain": days_since_retrain,
            "scheduled_retrain_days": self._scheduled_days,
            "drift_detected": brier is not None and brier > threshold,
            "scheduled_due": (
                days_since_retrain is not None
                and days_since_retrain >= self._scheduled_days
            ),
        }

    def get_all_status(self) -> dict[str, dict[str, Any]]:
        """Get drift monitoring status for all tracked assets."""
        return {asset.value: self.get_status(asset) for asset in self._floors}
