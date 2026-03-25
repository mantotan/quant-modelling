"""Tests for TabNet trainer.

Uses pytest.importorskip so tests are skipped if pytorch-tabnet is
not installed (it's in the optional ``gpu`` dependency group).
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

pytorch_tabnet = pytest.importorskip("pytorch_tabnet")


class TestTabNetTrainer:
    @pytest.fixture()
    def trainer(self):
        from qm.model.trainers.tabnet_trainer import TabNetTrainer

        return TabNetTrainer(n_trials=2, n_splits=2, train_period=80, test_period=40, seed=42)

    @pytest.fixture()
    def synthetic_data(self):
        rng = np.random.RandomState(42)
        n = 200
        X = rng.randn(n, 5).astype(np.float64)
        # Target correlated with first feature
        y = (X[:, 0] + rng.randn(n) * 0.5 > 0).astype(np.int64)
        feature_names = [f"feat_{i}" for i in range(5)]
        return X, y, feature_names

    def test_fit_returns_metrics(self, trainer, synthetic_data):
        X, y, names = synthetic_data
        metrics = trainer.fit(X, y, feature_names=names)
        assert "brier" in metrics
        assert 0 <= metrics["brier"] <= 1

    def test_predict_proba_shape(self, trainer, synthetic_data):
        X, y, names = synthetic_data
        trainer.fit(X, y, feature_names=names)
        probs = trainer.predict_proba(X)
        assert probs.shape == (len(X),)
        assert probs.min() >= 0.0
        assert probs.max() <= 1.0

    def test_predict_before_fit_raises(self):
        from qm.model.trainers.tabnet_trainer import TabNetTrainer

        trainer = TabNetTrainer()
        with pytest.raises(RuntimeError, match="not trained"):
            trainer.predict_proba(np.zeros((10, 5)))

    def test_feature_importance(self, trainer, synthetic_data):
        X, y, names = synthetic_data
        trainer.fit(X, y, feature_names=names)
        fi = trainer.feature_importance
        assert len(fi) == 5
        assert all(isinstance(v, (int, float)) for v in fi.values())

    def test_attention_masks_shape(self, trainer, synthetic_data):
        X, y, names = synthetic_data
        trainer.fit(X, y, feature_names=names)
        masks = trainer.attention_masks(X[:10])
        assert masks.shape == (10, 5)

    def test_best_params(self, trainer, synthetic_data):
        X, y, names = synthetic_data
        trainer.fit(X, y, feature_names=names)
        params = trainer.best_params
        assert "n_d" in params
        assert "n_steps" in params

    def test_save_load_roundtrip(self, trainer, synthetic_data, tmp_path: Path):
        X, y, names = synthetic_data
        trainer.fit(X, y, feature_names=names)

        model_path = tmp_path / "tabnet_model"
        trainer.save(model_path)

        from qm.model.trainers.tabnet_trainer import TabNetTrainer

        trainer2 = TabNetTrainer()
        trainer2.load(model_path)

        probs1 = trainer.predict_proba(X[:20])
        probs2 = trainer2.predict_proba(X[:20])
        np.testing.assert_array_almost_equal(probs1, probs2, decimal=5)

    def test_compatible_with_calibrator(self, trainer, synthetic_data):
        """TabNet output should feed into IsotonicCalibrator without error."""
        from qm.model.calibration.calibrator import IsotonicCalibrator

        X, y, names = synthetic_data
        trainer.fit(X, y, feature_names=names)
        probs = trainer.predict_proba(X)

        cal = IsotonicCalibrator()
        cal.fit(probs, y.astype(np.float64))
        cal_probs = cal.transform(probs)

        assert cal_probs.shape == probs.shape
        assert cal_probs.min() >= 0.0
        assert cal_probs.max() <= 1.0
