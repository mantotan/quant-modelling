"""Tests for specialist model routing and factory."""

import json
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pytest

from qm.model.specialist import SpecialistModelRouter, load_pulse_model


@pytest.fixture
def model_dir(tmp_path):
    """Create a temp directory with two tiny LightGBM models + calibrators."""
    rng = np.random.default_rng(42)
    X = rng.random((200, 5))
    y = rng.integers(0, 2, 200).astype(float)
    feature_names = ["f0", "f1", "f2", "f3", "f4"]

    for name in ("model_early", "model_late"):
        ds = lgb.Dataset(X, y, feature_name=feature_names)
        model = lgb.train(
            {"objective": "binary", "verbosity": -1, "num_leaves": 4},
            ds, num_boost_round=5,
        )
        model.save_model(str(tmp_path / f"{name}.lgb"))

    # Save calibrators (use simple pickle-compatible objects)
    from qm.model.calibration.calibrator import TimeAwareCalibrator
    for name in ("calibrator_early", "calibrator_late"):
        cal = TimeAwareCalibrator()
        # Fit with dummy data
        probs = rng.uniform(0.3, 0.7, 100)
        labels = rng.integers(0, 2, 100).astype(float)
        time_pcts = rng.uniform(0, 1, 100)
        cal.fit(probs, labels, time_pcts)
        cal.save(tmp_path / f"{name}.pkl")

    # Save specialist config
    config = {
        "boundary": 0.40,
        "early_time_pcts": [0.10, 0.20],
        "late_time_pcts": [0.40, 0.60, 0.80],
    }
    (tmp_path / "specialist_config.json").write_text(json.dumps(config))

    return tmp_path


@pytest.fixture
def single_model_dir(tmp_path):
    """Create a temp directory with a single model.lgb (no specialist)."""
    rng = np.random.default_rng(42)
    X = rng.random((200, 5))
    y = rng.integers(0, 2, 200).astype(float)
    ds = lgb.Dataset(X, y, feature_name=["f0", "f1", "f2", "f3", "f4"])
    model = lgb.train(
        {"objective": "binary", "verbosity": -1, "num_leaves": 4},
        ds, num_boost_round=5,
    )
    model.save_model(str(tmp_path / "model.lgb"))
    return tmp_path


class TestSpecialistModelRouter:
    def test_routes_early(self, model_dir):
        router = SpecialistModelRouter(model_dir)
        X = np.random.default_rng(0).random((1, 5))
        prob = router.predict_routed(X, elapsed_pct=0.10)
        assert 0.0 <= prob <= 1.0

    def test_routes_late(self, model_dir):
        router = SpecialistModelRouter(model_dir)
        X = np.random.default_rng(0).random((1, 5))
        prob = router.predict_routed(X, elapsed_pct=0.80)
        assert 0.0 <= prob <= 1.0

    def test_boundary_goes_to_late(self, model_dir):
        """Exactly at boundary should use late model."""
        router = SpecialistModelRouter(model_dir)
        X = np.random.default_rng(0).random((1, 5))
        prob = router.predict_routed(X, elapsed_pct=0.40)
        assert 0.0 <= prob <= 1.0

    def test_unrouted_predict(self, model_dir):
        """predict() without routing uses late model."""
        router = SpecialistModelRouter(model_dir)
        X = np.random.default_rng(0).random((1, 5))
        result = router.predict(X)
        assert isinstance(result, np.ndarray)
        assert len(result) == 1
        assert 0.0 <= result[0] <= 1.0

    def test_feature_name(self, model_dir):
        router = SpecialistModelRouter(model_dir)
        names = router.feature_name()
        assert names == ["f0", "f1", "f2", "f3", "f4"]

    def test_num_trees(self, model_dir):
        router = SpecialistModelRouter(model_dir)
        assert router.num_trees() == 10  # 5 + 5


class TestLoadPulseModel:
    def test_loads_specialist(self, model_dir):
        model = load_pulse_model(model_dir)
        assert isinstance(model, SpecialistModelRouter)

    def test_loads_single(self, single_model_dir):
        model = load_pulse_model(single_model_dir)
        assert isinstance(model, lgb.Booster)

    def test_not_found(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            load_pulse_model(tmp_path)

    def test_specialist_and_single_same_interface(self, model_dir, single_model_dir):
        """Both model types expose predict(), feature_name(), num_trees()."""
        specialist = load_pulse_model(model_dir)
        single = load_pulse_model(single_model_dir)

        X = np.random.default_rng(0).random((1, 5))

        # Both should predict
        assert hasattr(specialist, "predict")
        assert hasattr(single, "predict")
        s_pred = specialist.predict(X)
        b_pred = single.predict(X)
        assert isinstance(s_pred, np.ndarray)
        assert isinstance(b_pred, np.ndarray)

        # Both should have feature_name
        assert specialist.feature_name() == single.feature_name()

        # Both should have num_trees
        assert specialist.num_trees() > 0
        assert single.num_trees() > 0
