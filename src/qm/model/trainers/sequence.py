"""Sequence windowing and normalisation utilities for temporal models.

Converts flat feature matrices (n_samples, n_features) into 3-D tensors
(n_valid, seq_len, n_features) suitable for ALSTM / Transformer input.
"""

from __future__ import annotations

import logging
import pickle
from pathlib import Path

import numpy as np

logger = logging.getLogger(__name__)


def create_sequences(
    X: np.ndarray,
    y: np.ndarray,
    seq_len: int,
    bar_indices: np.ndarray | None = None,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Sliding window over flat features -> 3-D tensor.

    Args:
        X: Feature matrix, shape ``(n_samples, n_features)``.
        y: Target vector, shape ``(n_samples,)``.
        seq_len: Number of time-steps per sequence.
        bar_indices: Optional array of bar indices per sample.  When
            provided, sequences that cross bar boundaries are dropped
            (critical for Pulse intra-bar data where correlated samples
            within one bar must not leak into another bar's sequence).

    Returns:
        X_seq:  ``(n_valid, seq_len, n_features)``
        y_seq:  ``(n_valid,)``
        valid_indices:  ``(n_valid,)`` – original row indices of valid
            samples so callers can map predictions back to the flat array
            (e.g. for OOS mask bookkeeping).
    """
    if seq_len < 1:
        msg = f"seq_len must be >= 1, got {seq_len}"
        raise ValueError(msg)

    n_samples, n_features = X.shape
    if n_samples < seq_len:
        return (
            np.empty((0, seq_len, n_features), dtype=X.dtype),
            np.empty(0, dtype=y.dtype),
            np.empty(0, dtype=np.intp),
        )

    # Build candidate indices: each sample t uses rows [t-seq_len+1 .. t]
    candidates = np.arange(seq_len - 1, n_samples)

    # If bar_indices given, drop sequences that span multiple bars
    if bar_indices is not None:
        valid_mask = np.ones(len(candidates), dtype=bool)
        for i, t in enumerate(candidates):
            start = t - seq_len + 1
            if bar_indices[start] != bar_indices[t]:
                valid_mask[i] = False
        candidates = candidates[valid_mask]

    if len(candidates) == 0:
        return (
            np.empty((0, seq_len, n_features), dtype=X.dtype),
            np.empty(0, dtype=y.dtype),
            np.empty(0, dtype=np.intp),
        )

    # Build sequences via stacking slices
    X_seq = np.stack([X[t - seq_len + 1 : t + 1] for t in candidates])
    y_seq = y[candidates]

    return X_seq, y_seq, candidates


class SequenceNormalizer:
    """Per-feature z-score normalizer fitted on training data.

    Neural networks require normalised inputs; LightGBM does not.
    The normalizer is saved alongside the model so that live inference
    applies the same transformation.
    """

    def __init__(self) -> None:
        self._mean: np.ndarray | None = None
        self._std: np.ndarray | None = None

    @property
    def is_fitted(self) -> bool:
        return self._mean is not None

    def fit(self, X: np.ndarray) -> None:
        """Compute per-feature mean and std from training data."""
        self._mean = np.nanmean(X, axis=0).astype(np.float32)
        self._std = np.nanstd(X, axis=0).astype(np.float32)
        # Replace zero-std with 1.0 to avoid division by zero
        self._std[self._std < 1e-8] = 1.0
        logger.debug(
            "SequenceNormalizer fitted on %d samples, %d features",
            X.shape[0], X.shape[1],
        )

    def transform(self, X: np.ndarray) -> np.ndarray:
        """Apply z-score normalisation."""
        if self._mean is None or self._std is None:
            msg = "Normalizer not fitted. Call fit() first."
            raise RuntimeError(msg)
        return ((X - self._mean) / self._std).astype(np.float32)

    def fit_transform(self, X: np.ndarray) -> np.ndarray:
        self.fit(X)
        return self.transform(X)

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "wb") as f:
            pickle.dump({"mean": self._mean, "std": self._std}, f)

    def load(self, path: Path) -> None:
        with open(path, "rb") as f:  # noqa: S301
            data = pickle.load(f)  # noqa: S301
        self._mean = data["mean"]
        self._std = data["std"]
