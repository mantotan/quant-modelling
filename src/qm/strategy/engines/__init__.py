"""Strategy engine factory.

Creates strategy engines by name, backed by the StrategyEngine protocol.
"""

from __future__ import annotations

from typing import Any

from qm.strategy.base import StrategyEngine


def create_engine(name: str, config: dict[str, Any], bar_seconds: float) -> StrategyEngine:
    """Create a strategy engine by name.

    Args:
        name: One of "dutch", "directional", "selective", "divergence",
              "late_snipe", "hybrid".
        config: Strategy-specific configuration dict.
        bar_seconds: Bar duration in seconds.

    Returns:
        A StrategyEngine instance.
    """
    config_with_bs = {**config, "bar_seconds": bar_seconds}

    if name == "dutch":
        from qm.strategy.dutch.engine import DutchAccumulationEngine, DutchConfig

        return DutchAccumulationEngine(DutchConfig(**config_with_bs))

    if name in ("directional", "selective"):
        from qm.strategy.engines.directional import DirectionalConfig, DirectionalEngine

        if name == "selective" and "magnitude_threshold" not in config_with_bs:
            config_with_bs["magnitude_threshold"] = 0.08
        return DirectionalEngine(DirectionalConfig(**config_with_bs))

    if name == "divergence":
        from qm.strategy.engines.divergence import DivergenceConfig, DivergenceEngine

        return DivergenceEngine(DivergenceConfig(**config_with_bs))

    if name == "late_snipe":
        from qm.strategy.engines.late_snipe import LateSnipeConfig, LateSnipeEngine

        return LateSnipeEngine(LateSnipeConfig(**config_with_bs))

    if name == "hybrid":
        from qm.strategy.engines.hybrid import HybridConfig, HybridEngine

        return HybridEngine(HybridConfig(**config_with_bs))

    msg = f"Unknown strategy: {name!r}"
    raise ValueError(msg)
