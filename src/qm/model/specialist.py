"""Specialist model routing for per-timepoint Pulse models.

When specialist mode is enabled, two LightGBM models are trained:
one for early time_pcts (e.g., t <= 0.20) and one for late (t >= 0.40).
The ``SpecialistModelRouter`` routes predictions to the appropriate
model based on elapsed_pct.

``load_pulse_model()`` is the factory function that detects the model
format (specialist vs single) and returns the appropriate object.
Both expose ``.predict()``, ``.feature_name()``, and ``.num_trees()``
so scripts can use duck typing.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import lightgbm as lgb
import numpy as np

from qm.model.calibration.calibrator import TimeAwareCalibrator

logger = logging.getLogger(__name__)


class SpecialistModelRouter:
    """Routes predictions to early or late specialist based on elapsed_pct.

    Args:
        model_dir: Directory containing ``specialist_config.json``,
            ``model_early.lgb``, ``model_late.lgb``,
            ``calibrator_early.pkl``, ``calibrator_late.pkl``.
    """

    def __init__(self, model_dir: Path) -> None:
        config = json.loads((model_dir / "specialist_config.json").read_text())
        self.boundary: float = config["boundary"]
        self.early_time_pcts: list[float] = config.get("early_time_pcts", [])
        self.late_time_pcts: list[float] = config.get("late_time_pcts", [])

        self.model_early = lgb.Booster(
            model_file=str(model_dir / "model_early.lgb")
        )
        self.model_late = lgb.Booster(
            model_file=str(model_dir / "model_late.lgb")
        )

        self.cal_early = TimeAwareCalibrator()
        self.cal_early.load(model_dir / "calibrator_early.pkl")
        self.cal_late = TimeAwareCalibrator()
        self.cal_late.load(model_dir / "calibrator_late.pkl")

        logger.info(
            "Loaded specialist models: boundary=%.2f, "
            "early=%d trees, late=%d trees",
            self.boundary,
            self.model_early.num_trees(),
            self.model_late.num_trees(),
        )

    def predict_routed(
        self, features_2d: np.ndarray, elapsed_pct: float
    ) -> float:
        """Predict + calibrate using the appropriate specialist.

        Args:
            features_2d: Feature array of shape ``(1, n_features)``.
            elapsed_pct: Bar elapsed fraction (0.0 to 1.0).

        Returns:
            Calibrated probability in [0, 1].
        """
        if elapsed_pct < self.boundary:
            raw = float(self.model_early.predict(features_2d)[0])
            return float(
                self.cal_early.transform(
                    np.array([raw]), np.array([elapsed_pct])
                )[0]
            )
        raw = float(self.model_late.predict(features_2d)[0])
        return float(
            self.cal_late.transform(
                np.array([raw]), np.array([elapsed_pct])
            )[0]
        )

    def predict(self, features_2d: np.ndarray) -> np.ndarray:
        """Unrouted predict — defaults to late model (the money-maker).

        Maintains backward compatibility with scripts that call
        ``model.predict()`` without elapsed_pct.
        """
        return self.model_late.predict(features_2d)

    def feature_name(self) -> list[str]:
        """Feature names (same for both specialists)."""
        return self.model_early.feature_name()

    def num_trees(self) -> int:
        """Total trees across both specialists."""
        return self.model_early.num_trees() + self.model_late.num_trees()


def load_pulse_model(model_dir: Path) -> lgb.Booster | SpecialistModelRouter:
    """Factory: load the best available Pulse model from *model_dir*.

    Returns ``SpecialistModelRouter`` when ``specialist_config.json``
    exists, otherwise a plain ``lgb.Booster``.

    Raises:
        FileNotFoundError: If no model files are found.
    """
    if (model_dir / "specialist_config.json").exists():
        return SpecialistModelRouter(model_dir)
    model_path = model_dir / "model.lgb"
    if not model_path.exists():
        msg = f"No model found at {model_dir}"
        raise FileNotFoundError(msg)
    return lgb.Booster(model_file=str(model_path))
