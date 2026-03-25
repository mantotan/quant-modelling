"""Tests for stacking ensemble trainer.

Uses mock base trainers (simple LGBMTrainer) to avoid needing
torch as a dependency.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from qm.model.trainers.stacking_trainer import StackingTrainer


class _MockTrainer:
    """Minimal trainer for stacking tests — wraps a fixed prediction."""

    def __init__(self, bias: float = 0.0, **kwargs):
        self.bias = bias
        self.n_trials = kwargs.get("n_trials", 2)
        self.n_splits = kwargs.get("n_splits", 2)
        self.train_period = kwargs.get("train_period", 50)
        self.test_period = kwargs.get("test_period", 25)
        self.seed = kwargs.get("seed", 42)
        self._fitted = False
        self._best_params: dict = {}

    def fit(self, X, y, feature_names=None, market_probs=None):
        self._fitted = True
        self._mean = y.mean() + self.bias
        self._best_params = {"bias": self.bias}
        return {"brier": 0.25}

    def predict_proba(self, X):
        n = X.shape[0]
        rng = np.random.RandomState(self.seed)
        return np.clip(self._mean + rng.randn(n) * 0.1, 0.01, 0.99)

    def save(self, path):
        path.mkdir(parents=True, exist_ok=True)
        (path / "mock.txt").write_text(f"{self.bias}")

    def load(self, path):
        self.bias = float((path / "mock.txt").read_text())
        self._fitted = True
        self._mean = 0.5 + self.bias

    @property
    def best_params(self):
        return self._best_params


class TestStackingTrainer:
    @pytest.fixture()
    def synthetic_data(self):
        rng = np.random.RandomState(42)
        n = 300
        X = rng.randn(n, 5).astype(np.float64)
        y = (X[:, 0] + rng.randn(n) * 0.5 > 0).astype(np.float64)
        return X, y, [f"f{i}" for i in range(5)]

    def test_fit_returns_metrics(self, synthetic_data):
        X, y, names = synthetic_data
        base_trainers = [
            ("m1", _MockTrainer(bias=0.0)),
            ("m2", _MockTrainer(bias=0.05)),
        ]
        stacker = StackingTrainer(
            base_trainers=base_trainers, n_stacking_splits=2, seed=42,
        )
        metrics = stacker.fit(X, y, feature_names=names)
        assert "brier" in metrics
        assert 0 <= metrics["brier"] <= 1

    def test_predict_proba_shape(self, synthetic_data):
        X, y, names = synthetic_data
        base_trainers = [
            ("m1", _MockTrainer(bias=0.0)),
            ("m2", _MockTrainer(bias=0.05)),
        ]
        stacker = StackingTrainer(
            base_trainers=base_trainers, n_stacking_splits=2, seed=42,
        )
        stacker.fit(X, y, feature_names=names)
        probs = stacker.predict_proba(X)
        assert probs.shape == (len(X),)
        assert probs.min() >= 0.0
        assert probs.max() <= 1.0

    def test_predict_before_fit_raises(self):
        stacker = StackingTrainer(
            base_trainers=[("m1", _MockTrainer())], seed=42,
        )
        with pytest.raises(RuntimeError, match="not trained"):
            stacker.predict_proba(np.zeros((10, 5)))

    def test_save_load_roundtrip(self, synthetic_data, tmp_path: Path):
        X, y, names = synthetic_data
        base_trainers = [
            ("m1", _MockTrainer(bias=0.0)),
            ("m2", _MockTrainer(bias=0.05)),
        ]
        stacker = StackingTrainer(
            base_trainers=base_trainers, n_stacking_splits=2, seed=42,
        )
        stacker.fit(X, y, feature_names=names)

        save_dir = tmp_path / "stacking"
        stacker.save(save_dir)

        # Verify save created expected structure
        assert (save_dir / "meta.json").exists()
        assert (save_dir / "meta_model.pkl").exists()
        assert (save_dir / "base" / "m1" / "mock.txt").exists()
        assert (save_dir / "base" / "m2" / "mock.txt").exists()

        # Load with fresh trainers and verify meta model loads
        base_trainers2 = [
            ("m1", _MockTrainer(bias=0.0)),
            ("m2", _MockTrainer(bias=0.05)),
        ]
        stacker2 = StackingTrainer(
            base_trainers=base_trainers2, seed=42,
        )
        stacker2.load(save_dir)

        # After load, should be able to predict without error
        probs2 = stacker2.predict_proba(X[:50])
        assert probs2.shape == (50,)
        assert probs2.min() >= 0.0
        assert probs2.max() <= 1.0

    def test_meta_model_lgbm(self, synthetic_data):
        X, y, names = synthetic_data
        base_trainers = [
            ("m1", _MockTrainer(bias=0.0)),
            ("m2", _MockTrainer(bias=0.05)),
        ]
        stacker = StackingTrainer(
            base_trainers=base_trainers,
            meta_model="lgbm",
            n_stacking_splits=2,
            seed=42,
        )
        metrics = stacker.fit(X, y, feature_names=names)
        assert "brier" in metrics
        probs = stacker.predict_proba(X)
        assert probs.shape == (len(X),)

    def test_best_params(self, synthetic_data):
        X, y, names = synthetic_data
        base_trainers = [
            ("m1", _MockTrainer(bias=0.0)),
            ("m2", _MockTrainer(bias=0.05)),
        ]
        stacker = StackingTrainer(
            base_trainers=base_trainers, n_stacking_splits=2, seed=42,
        )
        stacker.fit(X, y, feature_names=names)
        params = stacker.best_params
        assert "base_models" in params
        assert params["base_models"] == ["m1", "m2"]
