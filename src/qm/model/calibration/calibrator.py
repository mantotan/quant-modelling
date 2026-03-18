"""Probability calibration for Polymarket edge calculation.

Critical: raw LightGBM outputs are NOT true probabilities. We must calibrate
them so that when the model says "60% chance of Up", it's right ~60% of the time.
Without calibration, edge calculation (model_prob - market_prob) is meaningless.

Uses expanding-window isotonic regression fitted on OOS walk-forward predictions.
"""

from __future__ import annotations

import logging
from pathlib import Path
import pickle

import numpy as np
from sklearn.isotonic import IsotonicRegression

logger = logging.getLogger(__name__)


class IsotonicCalibrator:
    """Isotonic regression calibrator with expanding-window support.

    Isotonic regression is non-parametric and can correct arbitrary monotonic
    distortions in model output. Better than Platt scaling for LightGBM
    which can have non-sigmoid miscalibration.

    Key design: fitted on OOS walk-forward predictions, NOT training data.
    """

    def __init__(self, clip_min: float = 0.01, clip_max: float = 0.99) -> None:
        self._calibrator = IsotonicRegression(
            y_min=clip_min, y_max=clip_max, out_of_bounds="clip"
        )
        self._clip_min = clip_min
        self._clip_max = clip_max
        self._fitted = False
        self._n_samples_fitted = 0

    def fit(self, raw_probs: np.ndarray, true_labels: np.ndarray) -> None:
        """Fit calibrator on out-of-sample predictions.

        Args:
            raw_probs: Raw model P(Up) from OOS walk-forward.
            true_labels: Actual binary outcomes (1=Up, 0=Down).
        """
        if len(raw_probs) < 20:
            logger.warning(f"Calibrating on only {len(raw_probs)} samples — results may be noisy")

        self._calibrator.fit(raw_probs, true_labels)
        self._fitted = True
        self._n_samples_fitted = len(raw_probs)
        logger.info(f"Calibrator fitted on {self._n_samples_fitted} OOS samples")

    def transform(self, raw_probs: np.ndarray) -> np.ndarray:
        """Transform raw model outputs to calibrated probabilities.

        Returns values clipped to [clip_min, clip_max] — never 0 or 1.
        """
        if not self._fitted:
            logger.warning("Calibrator not fitted, returning clipped raw probs")
            return np.clip(raw_probs, self._clip_min, self._clip_max)

        calibrated = self._calibrator.predict(raw_probs)
        return np.clip(calibrated, self._clip_min, self._clip_max)

    def fit_transform(self, raw_probs: np.ndarray, true_labels: np.ndarray) -> np.ndarray:
        self.fit(raw_probs, true_labels)
        return self.transform(raw_probs)

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "wb") as f:
            pickle.dump({
                "calibrator": self._calibrator,
                "clip_min": self._clip_min,
                "clip_max": self._clip_max,
                "n_samples": self._n_samples_fitted,
            }, f)

    def load(self, path: Path) -> None:
        with open(path, "rb") as f:
            data = pickle.load(f)  # noqa: S301
        self._calibrator = data["calibrator"]
        self._clip_min = data["clip_min"]
        self._clip_max = data["clip_max"]
        self._n_samples_fitted = data["n_samples"]
        self._fitted = True

    @property
    def is_fitted(self) -> bool:
        return self._fitted


class OnlineCalibrator:
    """Wraps IsotonicCalibrator with online recalibration support.

    Accumulates live predictions and outcomes, periodically refits
    the calibrator when enough new data arrives or drift is detected.
    """

    def __init__(
        self,
        base_calibrator: IsotonicCalibrator | None = None,
        recalibrate_every: int = 500,
        max_buffer: int = 5000,
    ) -> None:
        self._calibrator = base_calibrator or IsotonicCalibrator()
        self.recalibrate_every = recalibrate_every
        self._buffer_probs: list[float] = []
        self._buffer_labels: list[int] = []
        self._max_buffer = max_buffer

    def transform(self, raw_probs: np.ndarray) -> np.ndarray:
        return self._calibrator.transform(raw_probs)

    def update(self, raw_prob: float, true_label: int) -> bool:
        """Record a new observation. Returns True if recalibration triggered."""
        self._buffer_probs.append(raw_prob)
        self._buffer_labels.append(true_label)

        if len(self._buffer_probs) >= self.recalibrate_every:
            self._recalibrate()
            return True
        return False

    def _recalibrate(self) -> None:
        probs = np.array(self._buffer_probs[-self._max_buffer:])
        labels = np.array(self._buffer_labels[-self._max_buffer:])
        self._calibrator.fit(probs, labels)
        logger.info(f"Online recalibration on {len(probs)} samples")

        # Trim buffer
        if len(self._buffer_probs) > self._max_buffer:
            self._buffer_probs = self._buffer_probs[-self._max_buffer:]
            self._buffer_labels = self._buffer_labels[-self._max_buffer:]

    @property
    def base_calibrator(self) -> IsotonicCalibrator:
        return self._calibrator
