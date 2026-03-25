"""PyTorch device detection with caching.

Parallel to ``device.py`` which handles LightGBM GPU detection.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

_cached_device: object | None = None  # torch.device, but typed loosely to avoid hard import


def detect_torch_device(prefer_gpu: bool = True) -> object:
    """Detect best available PyTorch device.

    Returns a ``torch.device`` object.  Result is cached module-level.
    """
    global _cached_device  # noqa: PLW0603
    if _cached_device is not None:
        return _cached_device

    import torch

    if prefer_gpu and torch.cuda.is_available():
        device = torch.device("cuda")
        name = torch.cuda.get_device_name(0)
        vram_gb = torch.cuda.get_device_properties(0).total_memory / 1e9
        logger.info("PyTorch device: %s (%s, %.1f GB VRAM)", device, name, vram_gb)
    else:
        device = torch.device("cpu")
        logger.info("PyTorch device: cpu")

    _cached_device = device
    return device
