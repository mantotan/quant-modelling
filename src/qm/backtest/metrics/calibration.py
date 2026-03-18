"""Calibration metrics for probability predictions.

Critical for Polymarket: our model must output true probabilities,
not just rankings. If model says 60%, it must be right ~60% of the time.
"""

from __future__ import annotations

import numpy as np


def brier_score(probs: np.ndarray, labels: np.ndarray) -> float:
    """Brier score = mean((prob - label)^2). Lower is better. 0.25 is uninformed."""
    return float(np.mean((probs - labels) ** 2))


def expected_calibration_error(
    probs: np.ndarray,
    labels: np.ndarray,
    n_bins: int = 10,
) -> float:
    """ECE: weighted average of |accuracy - confidence| per bin.

    Args:
        probs: Predicted probabilities.
        labels: Binary true labels.
        n_bins: Number of probability bins.

    Returns:
        ECE in [0, 1]. Lower is better.
    """
    bin_edges = np.linspace(0, 1, n_bins + 1)
    ece = 0.0
    total = len(probs)

    for i in range(n_bins):
        mask = (probs >= bin_edges[i]) & (probs < bin_edges[i + 1])
        n_in_bin = mask.sum()
        if n_in_bin == 0:
            continue
        avg_confidence = probs[mask].mean()
        avg_accuracy = labels[mask].mean()
        ece += (n_in_bin / total) * abs(avg_accuracy - avg_confidence)

    return float(ece)


def reliability_diagram(
    probs: np.ndarray,
    labels: np.ndarray,
    n_bins: int = 10,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Compute reliability diagram data.

    Returns:
        (mean_predicted, actual_frequency, bin_counts) — arrays of length n_bins.
    """
    bin_edges = np.linspace(0, 1, n_bins + 1)
    mean_predicted = np.zeros(n_bins)
    actual_freq = np.zeros(n_bins)
    bin_counts = np.zeros(n_bins, dtype=int)

    for i in range(n_bins):
        mask = (probs >= bin_edges[i]) & (probs < bin_edges[i + 1])
        n_in_bin = mask.sum()
        bin_counts[i] = n_in_bin
        if n_in_bin > 0:
            mean_predicted[i] = probs[mask].mean()
            actual_freq[i] = labels[mask].mean()

    return mean_predicted, actual_freq, bin_counts


def brier_decomposition(
    probs: np.ndarray,
    labels: np.ndarray,
    n_bins: int = 10,
) -> tuple[float, float, float]:
    """Decompose Brier score into reliability, resolution, uncertainty.

    Brier = Reliability - Resolution + Uncertainty

    - Reliability: measures calibration quality (lower = better calibrated)
    - Resolution: measures sharpness of predictions (higher = better)
    - Uncertainty: base rate variance (fixed for a given dataset)
    """
    bin_edges = np.linspace(0, 1, n_bins + 1)
    total = len(probs)
    base_rate = labels.mean()

    reliability = 0.0
    resolution = 0.0

    for i in range(n_bins):
        mask = (probs >= bin_edges[i]) & (probs < bin_edges[i + 1])
        n_in_bin = mask.sum()
        if n_in_bin == 0:
            continue
        avg_pred = probs[mask].mean()
        avg_actual = labels[mask].mean()
        reliability += n_in_bin * (avg_pred - avg_actual) ** 2
        resolution += n_in_bin * (avg_actual - base_rate) ** 2

    reliability /= total
    resolution /= total
    uncertainty = base_rate * (1 - base_rate)

    return float(reliability), float(resolution), float(uncertainty)
