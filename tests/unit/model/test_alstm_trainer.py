"""Tests for ALSTM trainer.

Skipped if torch is not installed (optional gpu dependency).
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

torch = pytest.importorskip("torch")


@pytest.fixture()
def synthetic_data():
    rng = np.random.RandomState(42)
    n = 150
    X = rng.randn(n, 5).astype(np.float64)
    y = (X[:, 0] + rng.randn(n) * 0.3 > 0).astype(np.float64)
    return X, y, [f"f{i}" for i in range(5)]


class TestALSTMTrainer:
    def test_fit_returns_metrics(self, synthetic_data):
        from qm.model.trainers.alstm_trainer import ALSTMTrainer

        X, y, names = synthetic_data
        trainer = ALSTMTrainer(
            n_trials=2, n_splits=2, train_period=50, test_period=25,
            seq_len=5, seed=42, use_gpu=False,
        )
        metrics = trainer.fit(X, y, feature_names=names)
        assert "brier" in metrics
        assert 0 <= metrics["brier"] <= 1

    def test_predict_proba_shape(self, synthetic_data):
        from qm.model.trainers.alstm_trainer import ALSTMTrainer

        X, y, names = synthetic_data
        trainer = ALSTMTrainer(
            n_trials=1, n_splits=2, train_period=50, test_period=25,
            seq_len=5, seed=42, use_gpu=False,
        )
        trainer.fit(X, y, feature_names=names)
        probs = trainer.predict_proba(X)
        # Output is (n - seq_len + 1,)
        assert len(probs) == len(X) - 4
        assert probs.min() >= 0.0
        assert probs.max() <= 1.0

    def test_predict_before_fit_raises(self):
        from qm.model.trainers.alstm_trainer import ALSTMTrainer

        trainer = ALSTMTrainer(use_gpu=False)
        with pytest.raises(RuntimeError, match="not trained"):
            trainer.predict_proba(np.zeros((20, 5)))

    def test_save_load_roundtrip(self, synthetic_data, tmp_path: Path):
        from qm.model.trainers.alstm_trainer import ALSTMTrainer

        X, y, names = synthetic_data
        trainer = ALSTMTrainer(
            n_trials=1, n_splits=2, train_period=50, test_period=25,
            seq_len=5, seed=42, use_gpu=False,
        )
        trainer.fit(X, y, feature_names=names)

        save_dir = tmp_path / "alstm_model"
        trainer.save(save_dir)

        trainer2 = ALSTMTrainer(use_gpu=False)
        trainer2.load(save_dir)

        probs1 = trainer.predict_proba(X[:50])
        probs2 = trainer2.predict_proba(X[:50])
        np.testing.assert_array_almost_equal(probs1, probs2, decimal=4)

    def test_best_params(self, synthetic_data):
        from qm.model.trainers.alstm_trainer import ALSTMTrainer

        X, y, names = synthetic_data
        trainer = ALSTMTrainer(
            n_trials=2, n_splits=2, train_period=50, test_period=25,
            seq_len=5, seed=42, use_gpu=False,
        )
        trainer.fit(X, y, feature_names=names)
        assert "hidden_size" in trainer.best_params
        assert "num_layers" in trainer.best_params
