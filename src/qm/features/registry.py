"""Feature registry — single source of truth for all features.

Every feature has a unique name, group, required lookback, computation
function reference, and dependency list. The registry enables:
- Dependency-aware topological ordering of computation
- Automated documentation
- Point-in-time correctness enforcement
"""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class FeatureSpec:
    """Specification for a single feature."""

    name: str
    group: str
    lookback: int  # minimum bars of history required
    inputs: tuple[str, ...]  # column names this feature reads from
    dependencies: tuple[str, ...] = ()  # other feature names that must be computed first
    enabled: bool = True
    description: str = ""


class FeatureRegistry:
    """Central registry of all available features.

    Features are registered by group calculators at import time.
    The registry provides topological ordering for dependency-aware computation.
    """

    def __init__(self) -> None:
        self._features: dict[str, FeatureSpec] = {}
        self._groups: dict[str, list[str]] = defaultdict(list)

    def register(self, spec: FeatureSpec) -> None:
        if spec.name in self._features:
            logger.warning(f"Feature '{spec.name}' already registered, overwriting")
            # Remove from old group to prevent duplicates
            old_group = self._features[spec.name].group
            if spec.name in self._groups[old_group]:
                self._groups[old_group].remove(spec.name)
        self._features[spec.name] = spec
        if spec.name not in self._groups[spec.group]:
            self._groups[spec.group].append(spec.name)

    def register_many(self, specs: list[FeatureSpec]) -> None:
        for spec in specs:
            self.register(spec)

    def get(self, name: str) -> FeatureSpec:
        return self._features[name]

    def get_enabled(self) -> list[FeatureSpec]:
        return [s for s in self._features.values() if s.enabled]

    def get_by_group(self, group: str) -> list[FeatureSpec]:
        return [self._features[n] for n in self._groups.get(group, [])]

    def all_names(self) -> list[str]:
        return list(self._features.keys())

    def max_lookback(self) -> int:
        """Maximum lookback across all enabled features."""
        enabled = self.get_enabled()
        return max((s.lookback for s in enabled), default=0)

    def compute_order(self) -> list[FeatureSpec]:
        """Topological sort: features with no dependencies first."""
        enabled = {s.name: s for s in self.get_enabled()}
        visited: set[str] = set()
        order: list[FeatureSpec] = []

        def visit(name: str) -> None:
            if name in visited or name not in enabled:
                return
            visited.add(name)
            spec = enabled[name]
            for dep in spec.dependencies:
                visit(dep)
            order.append(spec)

        for name in enabled:
            visit(name)

        return order

    def __len__(self) -> int:
        return len(self._features)


# Global registry instance — feature groups register into this at import time
GLOBAL_REGISTRY = FeatureRegistry()
