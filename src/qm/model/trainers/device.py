"""LightGBM device detection: GPU with automatic CPU fallback.

Probes GPU availability once at import time by training a tiny model.
Both LGBMTrainer and PulseTrainer use detect_device() to get the
correct device string for LightGBM params.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

_detected_device: str | None = None


def _probe_gpu() -> bool:
    """Try training a tiny LightGBM model on GPU. Returns True if it works."""
    try:
        import lightgbm as lgb
        import numpy as np

        rng = np.random.default_rng(0)
        X = rng.random((50, 3))
        y = rng.integers(0, 2, 50)
        ds = lgb.Dataset(X, y, free_raw_data=False)
        lgb.train(
            {"device": "gpu", "objective": "binary", "verbosity": -1, "num_iterations": 2},
            ds,
        )
        return True
    except Exception:
        return False


def detect_device(prefer_gpu: bool = True) -> str:
    """Detect the best available LightGBM device.

    Args:
        prefer_gpu: If True (default), try GPU first and fall back to CPU.
            If False, always use CPU.

    Returns:
        "gpu" or "cpu"
    """
    global _detected_device

    if not prefer_gpu:
        return "cpu"

    if _detected_device is not None:
        return _detected_device

    if _probe_gpu():
        _detected_device = "gpu"
        logger.info("LightGBM device: GPU (available and working)")
    else:
        _detected_device = "cpu"
        logger.warning("LightGBM device: CPU (GPU not available, falling back)")

    return _detected_device
