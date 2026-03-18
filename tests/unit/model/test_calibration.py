"""Tests for probability calibration."""

import numpy as np
import pytest

from qm.model.calibration.calibrator import IsotonicCalibrator, OnlineCalibrator


class TestIsotonicCalibrator:
    def test_fit_and_transform(self):
        cal = IsotonicCalibrator()
        # Simulate: model outputs are overconfident
        raw = np.array([0.1, 0.3, 0.5, 0.7, 0.9])
        labels = np.array([0, 0, 1, 1, 1])
        cal.fit(raw, labels)

        calibrated = cal.transform(raw)
        assert len(calibrated) == 5
        assert all(0.01 <= p <= 0.99 for p in calibrated)

    def test_clipping(self):
        cal = IsotonicCalibrator(clip_min=0.05, clip_max=0.95)
        raw = np.array([0.01, 0.5, 0.99])
        labels = np.array([0, 1, 1])
        cal.fit(raw, labels)

        calibrated = cal.transform(np.array([0.0, 1.0]))
        assert calibrated[0] >= 0.05
        assert calibrated[1] <= 0.95

    def test_well_calibrated_model_stays_similar(self):
        """If model is already well-calibrated, isotonic shouldn't change much."""
        rng = np.random.RandomState(42)
        n = 1000
        true_probs = rng.uniform(0.1, 0.9, n)
        labels = (rng.random(n) < true_probs).astype(float)

        cal = IsotonicCalibrator()
        cal.fit(true_probs, labels)
        calibrated = cal.transform(true_probs)

        # Should be close to original
        max_diff = np.max(np.abs(calibrated - true_probs))
        assert max_diff < 0.15  # reasonable tolerance for isotonic on well-calibrated data

    def test_unfitted_returns_clipped(self):
        cal = IsotonicCalibrator()
        raw = np.array([0.0, 0.5, 1.0])
        result = cal.transform(raw)
        assert result[0] >= 0.01
        assert result[2] <= 0.99

    def test_save_load(self, tmp_path):
        cal = IsotonicCalibrator()
        raw = np.linspace(0, 1, 100)
        labels = (raw > 0.5).astype(float)
        cal.fit(raw, labels)

        save_path = tmp_path / "cal.pkl"
        cal.save(save_path)

        cal2 = IsotonicCalibrator()
        cal2.load(save_path)
        assert cal2.is_fitted

        # Should produce same outputs
        orig = cal.transform(np.array([0.3, 0.7]))
        loaded = cal2.transform(np.array([0.3, 0.7]))
        np.testing.assert_array_almost_equal(orig, loaded)


class TestOnlineCalibrator:
    def test_recalibration_trigger(self):
        base = IsotonicCalibrator()
        base.fit(np.linspace(0, 1, 50), (np.linspace(0, 1, 50) > 0.5).astype(float))

        online = OnlineCalibrator(base_calibrator=base, recalibrate_every=10)

        triggered = False
        for i in range(15):
            result = online.update(0.5 + i * 0.01, int(i > 7))
            if result:
                triggered = True

        assert triggered, "Recalibration should have triggered after 10 updates"
