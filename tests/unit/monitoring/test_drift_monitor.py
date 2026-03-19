"""Tests for DriftMonitor — model drift detection and retrain triggers.

Covers:
  - Rolling Brier computation
  - Rolling ECE computation
  - Drift threshold triggers (1.2x validation floor)
  - Scheduled retrain triggers (90-day quarterly)
  - Emergency retrain (manual force_retrain)
  - BTC regime monotonicity check
  - Prediction pruning
  - Minimum prediction count guard
  - Multi-asset tracking
  - Status reporting
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from qm.core.types import Asset, RegimeState
from qm.monitoring.drift_monitor import (
    DRIFT_MULTIPLIER,
    ROLLING_WINDOW_DAYS,
    SCHEDULED_RETRAIN_DAYS,
    VALIDATION_FLOORS,
    AssetDriftState,
    DriftMonitor,
    Prediction,
    RetrainReason,
    RetrainSignal,
)


# ── Helpers ─────────────────────────────────────────────────────────────

def _now() -> datetime:
    return datetime.now(timezone.utc)


def _make_predictions(
    asset: Asset,
    n: int,
    prob_up: float = 0.6,
    outcome: float = 1.0,
    start: datetime | None = None,
    interval_minutes: int = 5,
    regime: RegimeState | None = None,
    sharpe_contribution: float | None = None,
) -> list[Prediction]:
    """Generate a list of predictions for testing."""
    start = start or _now() - timedelta(days=1)
    return [
        Prediction(
            timestamp=start + timedelta(minutes=i * interval_minutes),
            asset=asset,
            prob_up=prob_up,
            outcome=outcome,
            regime=regime,
            sharpe_contribution=sharpe_contribution,
        )
        for i in range(n)
    ]


def _make_drifted_predictions(
    asset: Asset,
    n: int,
    start: datetime | None = None,
) -> list[Prediction]:
    """Generate predictions with high Brier (drifted model: predicts 0.9 but outcome is 0.0)."""
    start = start or _now() - timedelta(days=1)
    return _make_predictions(
        asset=asset,
        n=n,
        prob_up=0.9,
        outcome=0.0,
        start=start,
    )


def _make_good_predictions(
    asset: Asset,
    n: int,
    start: datetime | None = None,
) -> list[Prediction]:
    """Generate predictions with low Brier (good model: predicts 0.8 and outcome is 1.0)."""
    start = start or _now() - timedelta(days=1)
    return _make_predictions(
        asset=asset,
        n=n,
        prob_up=0.8,
        outcome=1.0,
        start=start,
    )


# ── AssetDriftState tests ──────────────────────────────────────────────

class TestAssetDriftState:
    def test_rolling_brier_empty(self):
        state = AssetDriftState()
        assert state.rolling_brier() is None

    def test_rolling_brier_too_few_predictions(self):
        state = AssetDriftState()
        preds = _make_good_predictions(Asset.BTC, 10)
        for p in preds:
            state.predictions.append(p)
        assert state.rolling_brier() is None  # < 50 minimum

    def test_rolling_brier_good_predictions(self):
        state = AssetDriftState()
        # prob_up=0.8, outcome=1.0 => Brier = (0.8 - 1.0)^2 = 0.04
        preds = _make_good_predictions(Asset.BTC, 100)
        for p in preds:
            state.predictions.append(p)
        brier = state.rolling_brier()
        assert brier is not None
        assert abs(brier - 0.04) < 1e-10

    def test_rolling_brier_drifted_predictions(self):
        state = AssetDriftState()
        # prob_up=0.9, outcome=0.0 => Brier = (0.9 - 0.0)^2 = 0.81
        preds = _make_drifted_predictions(Asset.BTC, 100)
        for p in preds:
            state.predictions.append(p)
        brier = state.rolling_brier()
        assert brier is not None
        assert abs(brier - 0.81) < 1e-10

    def test_rolling_brier_window_filter(self):
        state = AssetDriftState()
        # Old predictions (60 days ago) should be excluded from 30-day window
        old_preds = _make_drifted_predictions(
            Asset.BTC, 100, start=_now() - timedelta(days=60)
        )
        for p in old_preds:
            state.predictions.append(p)
        # Recent good predictions
        recent_preds = _make_good_predictions(Asset.BTC, 100)
        for p in recent_preds:
            state.predictions.append(p)

        brier = state.rolling_brier(window_days=30)
        assert brier is not None
        assert abs(brier - 0.04) < 1e-10  # Only recent good ones counted

    def test_rolling_ece_empty(self):
        state = AssetDriftState()
        assert state.rolling_ece() is None

    def test_rolling_ece_perfect_calibration(self):
        state = AssetDriftState()
        # Perfect calibration: predict 0.8, 80% are outcome=1.0
        start = _now() - timedelta(hours=12)
        for i in range(100):
            outcome = 1.0 if i < 80 else 0.0
            state.predictions.append(
                Prediction(
                    timestamp=start + timedelta(minutes=i * 5),
                    asset=Asset.ETH,
                    prob_up=0.8,
                    outcome=outcome,
                )
            )
        ece = state.rolling_ece()
        assert ece is not None
        assert ece < 0.01  # Near-perfect calibration

    def test_prediction_count(self):
        state = AssetDriftState()
        preds = _make_good_predictions(Asset.BTC, 75)
        for p in preds:
            state.predictions.append(p)
        assert state.prediction_count() == 75

    def test_prune_old(self):
        state = AssetDriftState()
        old = _make_good_predictions(
            Asset.BTC, 50, start=_now() - timedelta(days=200)
        )
        recent = _make_good_predictions(Asset.BTC, 50)
        for p in old + recent:
            state.predictions.append(p)

        pruned = state.prune_old(max_days=120)
        assert pruned == 50
        assert len(state.predictions) == 50


# ── DriftMonitor tests ─────────────────────────────────────────────────

class TestDriftMonitor:
    def test_default_floors(self):
        monitor = DriftMonitor()
        assert monitor._floors == VALIDATION_FLOORS

    def test_custom_floors(self):
        custom = {Asset.BTC: 0.15}
        monitor = DriftMonitor(validation_floors=custom)
        assert monitor._floors[Asset.BTC] == 0.15

    def test_no_triggers_insufficient_data(self):
        monitor = DriftMonitor()
        # Only 10 predictions — below min_predictions threshold
        preds = _make_drifted_predictions(Asset.BTC, 10)
        for p in preds:
            monitor.record_prediction(p)
        signals = monitor.check_triggers()
        assert len(signals) == 0

    def test_no_drift_good_model(self):
        monitor = DriftMonitor()
        # Good predictions: Brier = 0.04, well below BTC threshold 0.122
        preds = _make_good_predictions(Asset.BTC, 100)
        for p in preds:
            monitor.record_prediction(p)
        signals = monitor.check_triggers()
        assert len(signals) == 0

    def test_drift_detected(self):
        monitor = DriftMonitor()
        # Drifted: Brier = 0.81, way above BTC threshold 0.122
        preds = _make_drifted_predictions(Asset.BTC, 100)
        for p in preds:
            monitor.record_prediction(p)
        signals = monitor.check_triggers()

        drift_signals = [s for s in signals if s.reason == RetrainReason.DRIFT]
        assert len(drift_signals) == 1
        assert drift_signals[0].asset == Asset.BTC
        assert drift_signals[0].rolling_brier is not None
        assert drift_signals[0].rolling_brier > 0.12

    def test_drift_threshold_exact(self):
        """Test with Brier just at the threshold boundary."""
        # BTC floor = 0.101759, threshold = 0.101759 * 1.2 = 0.122111
        # Brier = (p - o)^2 where we want brier ~ 0.122
        # sqrt(0.122) ~ 0.349, so prob_up=0.349, outcome=0.0 => Brier = 0.1218 (just below)
        monitor = DriftMonitor()
        preds = _make_predictions(
            Asset.BTC, 100, prob_up=0.349, outcome=0.0
        )
        for p in preds:
            monitor.record_prediction(p)
        signals = monitor.check_triggers()
        drift_signals = [s for s in signals if s.reason == RetrainReason.DRIFT]
        # 0.349^2 = 0.121801 < 0.122111 => no drift
        assert len(drift_signals) == 0

    def test_drift_just_above_threshold(self):
        """Test with Brier just above threshold."""
        # prob_up=0.351, outcome=0.0 => Brier = 0.3510^2 = 0.12320 > 0.12211
        monitor = DriftMonitor()
        preds = _make_predictions(
            Asset.BTC, 100, prob_up=0.351, outcome=0.0
        )
        for p in preds:
            monitor.record_prediction(p)
        signals = monitor.check_triggers()
        drift_signals = [s for s in signals if s.reason == RetrainReason.DRIFT]
        assert len(drift_signals) == 1

    def test_scheduled_retrain_not_due(self):
        monitor = DriftMonitor()
        monitor.record_deploy(Asset.ETH, _now() - timedelta(days=30))
        signals = monitor.check_triggers()
        sched = [s for s in signals if s.reason == RetrainReason.SCHEDULED]
        assert len(sched) == 0

    def test_scheduled_retrain_due(self):
        monitor = DriftMonitor()
        monitor.record_deploy(Asset.ETH, _now() - timedelta(days=91))
        signals = monitor.check_triggers()
        sched = [s for s in signals if s.reason == RetrainReason.SCHEDULED]
        assert len(sched) == 1
        assert sched[0].asset == Asset.ETH

    def test_scheduled_retrain_resets_after_retrain(self):
        monitor = DriftMonitor()
        monitor.record_deploy(Asset.ETH, _now() - timedelta(days=180))
        monitor.record_retrain(Asset.ETH, _now() - timedelta(days=10))
        signals = monitor.check_triggers()
        sched = [s for s in signals if s.reason == RetrainReason.SCHEDULED]
        assert len(sched) == 0  # Reset by recent retrain

    def test_scheduled_no_deploy_no_trigger(self):
        """No deploy recorded => no scheduled retrain trigger."""
        monitor = DriftMonitor()
        signals = monitor.check_triggers()
        sched = [s for s in signals if s.reason == RetrainReason.SCHEDULED]
        assert len(sched) == 0

    def test_emergency_retrain(self):
        monitor = DriftMonitor()
        signal = monitor.force_retrain(Asset.SOL, "FTX 2.0 collapse")
        assert signal.reason == RetrainReason.EMERGENCY
        assert signal.asset == Asset.SOL
        assert "FTX 2.0" in signal.details

        # Signal should appear on next check
        signals = monitor.check_triggers()
        emergency = [s for s in signals if s.reason == RetrainReason.EMERGENCY]
        assert len(emergency) == 1

    def test_emergency_consumed_after_check(self):
        monitor = DriftMonitor()
        monitor.force_retrain(Asset.SOL, "test")
        monitor.check_triggers()  # Consume it
        signals = monitor.check_triggers()  # Should be empty now
        emergency = [s for s in signals if s.reason == RetrainReason.EMERGENCY]
        assert len(emergency) == 0


class TestRegimeMonotonicity:
    def test_no_trigger_insufficient_regime_data(self):
        monitor = DriftMonitor()
        # Only 10 crisis trades (need 30)
        preds = _make_predictions(
            Asset.BTC, 10, regime=RegimeState.CRISIS, sharpe_contribution=2.0
        )
        for p in preds:
            monitor.record_prediction(p)
        preds = _make_predictions(
            Asset.BTC, 50, regime=RegimeState.NORMAL, sharpe_contribution=1.0,
            start=_now() - timedelta(hours=6),
        )
        for p in preds:
            monitor.record_prediction(p)
        signals = monitor.check_triggers()
        regime = [s for s in signals if s.reason == RetrainReason.REGIME_MONOTONICITY]
        assert len(regime) == 0

    def test_monotonicity_holds(self):
        """Crisis > normal => no trigger."""
        monitor = DriftMonitor()
        crisis = _make_predictions(
            Asset.BTC, 50, regime=RegimeState.CRISIS, sharpe_contribution=3.0
        )
        normal = _make_predictions(
            Asset.BTC, 50, regime=RegimeState.NORMAL, sharpe_contribution=1.5,
            start=_now() - timedelta(hours=6),
        )
        for p in crisis + normal:
            monitor.record_prediction(p)
        signals = monitor.check_triggers()
        regime = [s for s in signals if s.reason == RetrainReason.REGIME_MONOTONICITY]
        assert len(regime) == 0

    def test_monotonicity_violated(self):
        """Crisis < normal => trigger."""
        monitor = DriftMonitor()
        crisis = _make_predictions(
            Asset.BTC, 50, regime=RegimeState.CRISIS, sharpe_contribution=0.5
        )
        normal = _make_predictions(
            Asset.BTC, 50, regime=RegimeState.NORMAL, sharpe_contribution=2.0,
            start=_now() - timedelta(hours=6),
        )
        for p in crisis + normal:
            monitor.record_prediction(p)
        signals = monitor.check_triggers()
        regime = [s for s in signals if s.reason == RetrainReason.REGIME_MONOTONICITY]
        assert len(regime) == 1
        assert "monotonicity" in regime[0].details.lower()

    def test_regime_check_only_btc(self):
        """Regime monotonicity only applies to BTC."""
        monitor = DriftMonitor()
        crisis = _make_predictions(
            Asset.ETH, 50, regime=RegimeState.CRISIS, sharpe_contribution=0.5
        )
        normal = _make_predictions(
            Asset.ETH, 50, regime=RegimeState.NORMAL, sharpe_contribution=2.0,
            start=_now() - timedelta(hours=6),
        )
        for p in crisis + normal:
            monitor.record_prediction(p)
        signals = monitor.check_triggers()
        regime = [s for s in signals if s.reason == RetrainReason.REGIME_MONOTONICITY]
        assert len(regime) == 0  # Not BTC, no regime check


class TestMultiAsset:
    def test_multi_asset_drift(self):
        """Multiple assets can independently trigger drift."""
        monitor = DriftMonitor()

        # BTC drifted
        btc_preds = _make_drifted_predictions(Asset.BTC, 100)
        for p in btc_preds:
            monitor.record_prediction(p)

        # ETH fine
        eth_preds = _make_good_predictions(Asset.ETH, 100)
        for p in eth_preds:
            monitor.record_prediction(p)

        signals = monitor.check_triggers()
        drift_assets = {s.asset for s in signals if s.reason == RetrainReason.DRIFT}
        assert Asset.BTC in drift_assets
        assert Asset.ETH not in drift_assets

    def test_all_assets_tracked(self):
        """All 4 assets from VALIDATION_FLOORS are checked."""
        monitor = DriftMonitor()
        status = monitor.get_all_status()
        assert set(status.keys()) == {"BTC", "ETH", "SOL", "XRP"}


class TestStatus:
    def test_status_empty(self):
        monitor = DriftMonitor()
        status = monitor.get_status(Asset.BTC)
        assert status["asset"] == "BTC"
        assert status["rolling_brier"] is None
        assert status["rolling_ece"] is None
        assert status["prediction_count"] == 0
        assert status["drift_detected"] is False

    def test_status_with_data(self):
        monitor = DriftMonitor()
        preds = _make_good_predictions(Asset.ETH, 100)
        for p in preds:
            monitor.record_prediction(p)
        monitor.record_deploy(Asset.ETH, _now() - timedelta(days=10))

        status = monitor.get_status(Asset.ETH)
        assert status["asset"] == "ETH"
        assert status["rolling_brier"] is not None
        assert abs(status["rolling_brier"] - 0.04) < 1e-10
        assert status["prediction_count"] == 100
        assert status["days_since_retrain"] == 10
        assert status["drift_detected"] is False
        assert status["scheduled_due"] is False
        assert status["validation_floor"] == VALIDATION_FLOORS[Asset.ETH]
        assert abs(status["drift_threshold"] - VALIDATION_FLOORS[Asset.ETH] * 1.2) < 1e-10


class TestRetrainSignal:
    def test_signal_immutable(self):
        signal = RetrainSignal(
            asset=Asset.BTC,
            reason=RetrainReason.DRIFT,
            triggered_at=_now(),
            rolling_brier=0.15,
            threshold=0.122,
        )
        with pytest.raises(AttributeError):
            signal.rolling_brier = 0.20  # type: ignore[misc]

    def test_prediction_immutable(self):
        pred = Prediction(
            timestamp=_now(),
            asset=Asset.BTC,
            prob_up=0.7,
            outcome=1.0,
        )
        with pytest.raises(AttributeError):
            pred.prob_up = 0.5  # type: ignore[misc]


class TestEdgeCases:
    def test_custom_min_predictions(self):
        monitor = DriftMonitor(min_predictions=200)
        preds = _make_drifted_predictions(Asset.BTC, 100)
        for p in preds:
            monitor.record_prediction(p)
        signals = monitor.check_triggers()
        drift = [s for s in signals if s.reason == RetrainReason.DRIFT]
        assert len(drift) == 0  # 100 < 200 minimum

    def test_custom_drift_multiplier(self):
        # With 3x multiplier, BTC threshold = 0.101759 * 3 = 0.305
        monitor = DriftMonitor(drift_multiplier=3.0)
        # Brier = 0.25 (prob=0.5, outcome=0.0 => (0.5)^2 = 0.25)
        preds = _make_predictions(Asset.BTC, 100, prob_up=0.5, outcome=0.0)
        for p in preds:
            monitor.record_prediction(p)
        signals = monitor.check_triggers()
        drift = [s for s in signals if s.reason == RetrainReason.DRIFT]
        assert len(drift) == 0  # 0.25 < 0.305

    def test_custom_scheduled_days(self):
        monitor = DriftMonitor(scheduled_days=30)
        monitor.record_deploy(Asset.SOL, _now() - timedelta(days=31))
        signals = monitor.check_triggers()
        sched = [s for s in signals if s.reason == RetrainReason.SCHEDULED]
        assert len(sched) == 1

    def test_multiple_triggers_same_check(self):
        """An asset can trigger both drift and scheduled retrain simultaneously."""
        monitor = DriftMonitor()
        # Deploy 91 days ago
        monitor.record_deploy(Asset.BTC, _now() - timedelta(days=91))
        # Drifted predictions
        preds = _make_drifted_predictions(Asset.BTC, 100)
        for p in preds:
            monitor.record_prediction(p)
        signals = monitor.check_triggers()
        reasons = {s.reason for s in signals if s.asset == Asset.BTC}
        assert RetrainReason.DRIFT in reasons
        assert RetrainReason.SCHEDULED in reasons

    def test_record_deploy_defaults_to_now(self):
        monitor = DriftMonitor()
        before = _now()
        monitor.record_deploy(Asset.XRP)
        after = _now()
        state = monitor._get_state(Asset.XRP)
        assert state.last_deploy is not None
        assert before <= state.last_deploy <= after

    def test_record_retrain_defaults_to_now(self):
        monitor = DriftMonitor()
        before = _now()
        monitor.record_retrain(Asset.XRP)
        after = _now()
        state = monitor._get_state(Asset.XRP)
        assert state.last_retrain is not None
        assert before <= state.last_retrain <= after

    def test_force_retrain_default_details(self):
        monitor = DriftMonitor()
        signal = monitor.force_retrain(Asset.ETH)
        assert "ETH" in signal.details
