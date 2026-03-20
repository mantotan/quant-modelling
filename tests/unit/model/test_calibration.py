"""Tests for probability calibration."""

import numpy as np
import pytest

from qm.model.calibration.calibrator import (
    IsotonicCalibrator,
    OnlineCalibrator,
    TimeAwareCalibrator,
)


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


class TestTimeAwareCalibrator:
    def _make_data(self, n_per_bucket=200, seed=42):
        """Generate synthetic data spanning multiple time buckets."""
        rng = np.random.RandomState(seed)
        time_pcts = []
        raw_probs = []
        labels = []
        for tp in [0.05, 0.10, 0.25, 0.40, 0.60, 0.80]:
            # Higher accuracy at later time points (realistic)
            accuracy = 0.50 + tp * 0.30
            probs = rng.beta(2, 2, n_per_bucket) * 0.6 + 0.2  # probs in [0.2, 0.8]
            labs = (rng.random(n_per_bucket) < accuracy).astype(float)
            time_pcts.extend([tp] * n_per_bucket)
            raw_probs.extend(probs)
            labels.extend(labs)
        return np.array(raw_probs), np.array(labels), np.array(time_pcts)

    def test_fit_and_transform(self):
        raw, labels, tps = self._make_data()
        cal = TimeAwareCalibrator()
        cal.fit(raw, labels, tps)
        assert cal.is_fitted

        result = cal.transform(raw, tps)
        assert len(result) == len(raw)
        assert all(0.01 <= p <= 0.99 for p in result)

    def test_per_bucket_calibrators_created(self):
        raw, labels, tps = self._make_data()
        cal = TimeAwareCalibrator()
        cal.fit(raw, labels, tps)

        info = cal.bucket_info
        # Buckets with samples should have their own calibrators
        for i, meta in info.items():
            if meta["n_samples"] >= TimeAwareCalibrator.MIN_SAMPLES_PER_BUCKET:
                assert meta["has_own_calibrator"], f"Bucket {i} should have own calibrator"

    def test_transform_without_time_pcts_uses_global(self):
        """Backward compat: transform(probs) without time_pcts uses global."""
        raw, labels, tps = self._make_data()
        cal = TimeAwareCalibrator()
        cal.fit(raw, labels, tps)

        result = cal.transform(raw)  # no time_pcts
        assert len(result) == len(raw)

    def test_save_load_roundtrip(self, tmp_path):
        raw, labels, tps = self._make_data()
        cal = TimeAwareCalibrator()
        cal.fit(raw, labels, tps)

        path = tmp_path / "cal.pkl"
        cal.save(path)

        cal2 = TimeAwareCalibrator()
        cal2.load(path)
        assert cal2.is_fitted

        test_probs = np.array([0.3, 0.5, 0.7])
        test_tps = np.array([0.10, 0.40, 0.80])
        np.testing.assert_array_almost_equal(
            cal.transform(test_probs, test_tps),
            cal2.transform(test_probs, test_tps),
        )

    def test_load_legacy_isotonic_pickle(self, tmp_path):
        """Loading an old IsotonicCalibrator pickle should work as global fallback."""
        old_cal = IsotonicCalibrator()
        old_cal.fit(np.linspace(0, 1, 100), (np.linspace(0, 1, 100) > 0.5).astype(float))

        path = tmp_path / "old_cal.pkl"
        old_cal.save(path)

        new_cal = TimeAwareCalibrator()
        new_cal.load(path)
        assert new_cal.is_fitted

        # Should produce same result as old calibrator (using global fallback)
        test = np.array([0.3, 0.7])
        np.testing.assert_array_almost_equal(
            old_cal.transform(test),
            new_cal.transform(test),  # no time_pcts → global
        )

    def test_small_bucket_falls_back_to_global(self):
        """Buckets with <50 samples should use global calibrator."""
        rng = np.random.RandomState(42)
        # Only put samples in one time bucket
        n = 500
        raw = rng.beta(2, 2, n) * 0.6 + 0.2
        labels = (rng.random(n) < 0.65).astype(float)
        tps = np.full(n, 0.80)  # all in bucket 4

        cal = TimeAwareCalibrator()
        cal.fit(raw, labels, tps)

        info = cal.bucket_info
        # Only bucket 4 should have its own calibrator
        for i, meta in info.items():
            if i == 4:
                assert meta["has_own_calibrator"]
            else:
                assert not meta["has_own_calibrator"]

        # Transform at t=0.10 should still work (uses global)
        result = cal.transform(np.array([0.5]), np.array([0.10]))
        assert 0.01 <= result[0] <= 0.99

    def test_single_prediction_transform(self):
        """Common case: paper trading sends single prediction with scalar time_pct."""
        raw, labels, tps = self._make_data()
        cal = TimeAwareCalibrator()
        cal.fit(raw, labels, tps)

        result = cal.transform(np.array([0.65]), np.array([0.80]))
        assert result.shape == (1,)
        assert 0.01 <= result[0] <= 0.99


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
