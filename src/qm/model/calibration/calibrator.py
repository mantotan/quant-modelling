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


class TimeAwareCalibrator:
    """Per-time-bucket isotonic calibration for multi-timepoint Pulse models.

    Different elapsed times have fundamentally different prediction distributions.
    At t=0.10, accuracy is ~58% with tight prob spread; at t=0.80, accuracy is ~74%
    with wide spread. A single calibrator distorts early-time predictions.

    Holds one IsotonicCalibrator per time bucket, routing predictions to the
    appropriate bucket based on elapsed_pct. Falls back to a global calibrator
    for buckets with insufficient samples.
    """

    # (lower_bound, upper_bound) — upper is exclusive except for the last bucket
    DEFAULT_BUCKETS: list[tuple[float, float]] = [
        (0.00, 0.15),
        (0.15, 0.30),
        (0.30, 0.50),
        (0.50, 0.70),
        (0.70, 1.01),  # 1.01 to include t=1.0
    ]

    MIN_SAMPLES_PER_BUCKET = 50

    def __init__(
        self,
        buckets: list[tuple[float, float]] | None = None,
        clip_min: float = 0.01,
        clip_max: float = 0.99,
    ) -> None:
        self._buckets = buckets or self.DEFAULT_BUCKETS
        self._clip_min = clip_min
        self._clip_max = clip_max
        self._calibrators: dict[int, IsotonicCalibrator] = {}
        self._global = IsotonicCalibrator(clip_min=clip_min, clip_max=clip_max)
        self._fitted = False
        self._bucket_sample_counts: dict[int, int] = {}

    def _bucket_index(self, time_pct: float) -> int:
        for i, (lo, hi) in enumerate(self._buckets):
            if lo <= time_pct < hi:
                return i
        return len(self._buckets) - 1

    def _bucket_indices(self, time_pcts: np.ndarray) -> np.ndarray:
        indices = np.zeros(len(time_pcts), dtype=int)
        for i, (lo, hi) in enumerate(self._buckets):
            mask = (time_pcts >= lo) & (time_pcts < hi)
            indices[mask] = i
        return indices

    def fit(
        self,
        raw_probs: np.ndarray,
        true_labels: np.ndarray,
        time_pcts: np.ndarray,
    ) -> None:
        """Fit per-bucket calibrators on OOS predictions."""
        # Fit global calibrator first (fallback)
        self._global.fit(raw_probs, true_labels)

        bucket_ids = self._bucket_indices(time_pcts)
        for i in range(len(self._buckets)):
            mask = bucket_ids == i
            n = int(mask.sum())
            self._bucket_sample_counts[i] = n
            if n >= self.MIN_SAMPLES_PER_BUCKET:
                cal = IsotonicCalibrator(clip_min=self._clip_min, clip_max=self._clip_max)
                cal.fit(raw_probs[mask], true_labels[mask])
                self._calibrators[i] = cal
                logger.info(
                    "TimeAwareCalibrator bucket %d [%.2f-%.2f): %d samples",
                    i, self._buckets[i][0], self._buckets[i][1], n,
                )
            else:
                logger.warning(
                    "TimeAwareCalibrator bucket %d [%.2f-%.2f): only %d samples, using global fallback",
                    i, self._buckets[i][0], self._buckets[i][1], n,
                )

        self._fitted = True

    def transform(
        self,
        raw_probs: np.ndarray,
        time_pcts: np.ndarray | None = None,
    ) -> np.ndarray:
        """Transform raw probs using per-bucket calibrators.

        If time_pcts is None, falls back to global calibrator (backward compat).
        """
        if not self._fitted:
            logger.warning("TimeAwareCalibrator not fitted, returning clipped raw probs")
            return np.clip(raw_probs, self._clip_min, self._clip_max)

        if time_pcts is None:
            return self._global.transform(raw_probs)

        result = np.empty_like(raw_probs)
        bucket_ids = self._bucket_indices(time_pcts)

        for i in range(len(self._buckets)):
            mask = bucket_ids == i
            if not mask.any():
                continue
            cal = self._calibrators.get(i, self._global)
            result[mask] = cal.transform(raw_probs[mask])

        return result

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "wb") as f:
            pickle.dump({
                "type": "TimeAwareCalibrator",
                "buckets": self._buckets,
                "calibrators": {
                    k: {"calibrator": v._calibrator, "n_samples": v._n_samples_fitted}
                    for k, v in self._calibrators.items()
                },
                "global": {
                    "calibrator": self._global._calibrator,
                    "n_samples": self._global._n_samples_fitted,
                },
                "clip_min": self._clip_min,
                "clip_max": self._clip_max,
                "bucket_sample_counts": self._bucket_sample_counts,
            }, f)

    def load(self, path: Path) -> None:
        with open(path, "rb") as f:
            data = pickle.load(f)  # noqa: S301

        # Backward compat: old pickles are plain IsotonicCalibrator dicts
        if "type" not in data:
            logger.info("Loading legacy IsotonicCalibrator pickle as global fallback")
            self._global._calibrator = data["calibrator"]
            self._global._clip_min = data["clip_min"]
            self._global._clip_max = data["clip_max"]
            self._global._n_samples_fitted = data["n_samples"]
            self._global._fitted = True
            self._calibrators = {}
            self._fitted = True
            return

        self._buckets = data["buckets"]
        self._clip_min = data["clip_min"]
        self._clip_max = data["clip_max"]
        self._bucket_sample_counts = data.get("bucket_sample_counts", {})

        # Restore global
        self._global._calibrator = data["global"]["calibrator"]
        self._global._n_samples_fitted = data["global"]["n_samples"]
        self._global._fitted = True

        # Restore per-bucket calibrators
        self._calibrators = {}
        for k, v in data["calibrators"].items():
            cal = IsotonicCalibrator(clip_min=self._clip_min, clip_max=self._clip_max)
            cal._calibrator = v["calibrator"]
            cal._n_samples_fitted = v["n_samples"]
            cal._fitted = True
            self._calibrators[int(k)] = cal

        self._fitted = True

    @property
    def is_fitted(self) -> bool:
        return self._fitted

    @property
    def bucket_info(self) -> dict[int, dict]:
        """Return bucket metadata for logging/debugging."""
        info = {}
        for i, (lo, hi) in enumerate(self._buckets):
            info[i] = {
                "range": (lo, hi),
                "n_samples": self._bucket_sample_counts.get(i, 0),
                "has_own_calibrator": i in self._calibrators,
            }
        return info


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
