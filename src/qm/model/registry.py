"""Model registry: versioned storage of model artifacts.

Each model version stores:
- model.txt (LightGBM text format)
- calibrator.pkl (isotonic regression)
- model.so/.dll (treelite compiled, optional)
- config.json (hyperparams, training config)
- metrics.json (CV and OOS metrics)
- feature_importance.json
"""

from __future__ import annotations

import json
import logging
import shutil
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)


class ModelRegistry:
    """Versioned model artifact storage.

    Layout:
        base_path/
        ├── experiment_001/
        │   ├── v1_20260318_120000/
        │   │   ├── model.txt
        │   │   ├── calibrator.pkl
        │   │   ├── model.so
        │   │   ├── config.json
        │   │   ├── metrics.json
        │   │   └── feature_importance.json
        │   ├── v2_20260319_080000/
        │   │   └── ...
        │   └── latest -> v2_20260319_080000/
    """

    def __init__(self, base_path: Path) -> None:
        self.base_path = base_path
        self.base_path.mkdir(parents=True, exist_ok=True)

    def save(
        self,
        experiment_id: str,
        model_path: Path,
        calibrator_path: Path | None = None,
        treelite_path: Path | None = None,
        config: dict | None = None,
        metrics: dict | None = None,
        feature_importance: dict | None = None,
    ) -> str:
        """Save model artifacts to registry. Returns version string."""
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        version = f"v_{ts}"
        version_dir = self.base_path / experiment_id / version
        version_dir.mkdir(parents=True, exist_ok=True)

        # Copy model
        shutil.copy2(model_path, version_dir / "model.txt")

        # Copy calibrator
        if calibrator_path and calibrator_path.exists():
            shutil.copy2(calibrator_path, version_dir / "calibrator.pkl")

        # Copy treelite
        if treelite_path and treelite_path.exists():
            shutil.copy2(treelite_path, version_dir / treelite_path.name)

        # Save config
        if config:
            (version_dir / "config.json").write_text(json.dumps(config, indent=2, default=str))

        # Save metrics
        if metrics:
            (version_dir / "metrics.json").write_text(json.dumps(metrics, indent=2, default=str))

        # Save feature importance
        if feature_importance:
            (version_dir / "feature_importance.json").write_text(
                json.dumps(feature_importance, indent=2, default=str)
            )

        # Update "latest" symlink (or just a marker file on Windows)
        latest_marker = self.base_path / experiment_id / "latest.txt"
        latest_marker.write_text(version)

        logger.info(f"Saved model {experiment_id}/{version}")
        return version

    def load_path(self, experiment_id: str, version: str = "latest") -> Path:
        """Get the directory path for a model version."""
        if version == "latest":
            marker = self.base_path / experiment_id / "latest.txt"
            if marker.exists():
                version = marker.read_text().strip()
            else:
                # Find latest by sorting directory names
                exp_dir = self.base_path / experiment_id
                if not exp_dir.exists():
                    msg = f"Experiment '{experiment_id}' not found"
                    raise FileNotFoundError(msg)
                versions = sorted(
                    [d.name for d in exp_dir.iterdir() if d.is_dir()],
                    reverse=True,
                )
                if not versions:
                    msg = f"No versions found for '{experiment_id}'"
                    raise FileNotFoundError(msg)
                version = versions[0]

        version_dir = self.base_path / experiment_id / version
        if not version_dir.exists():
            msg = f"Version {version} not found for {experiment_id}"
            raise FileNotFoundError(msg)

        return version_dir

    def load_metrics(self, experiment_id: str, version: str = "latest") -> dict:
        """Load metrics for a model version."""
        path = self.load_path(experiment_id, version) / "metrics.json"
        if path.exists():
            return json.loads(path.read_text())
        return {}

    def list_versions(self, experiment_id: str) -> list[str]:
        """List all versions for an experiment."""
        exp_dir = self.base_path / experiment_id
        if not exp_dir.exists():
            return []
        return sorted(
            [d.name for d in exp_dir.iterdir() if d.is_dir()],
        )

    def list_experiments(self) -> list[str]:
        """List all experiment IDs."""
        return sorted(
            [d.name for d in self.base_path.iterdir() if d.is_dir()],
        )
