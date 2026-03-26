"""Attention-LSTM trainer with Optuna HPO and walk-forward evaluation.

Cherry-picked from Qlib's ALSTM architecture, adapted to output
calibrated probabilities (not ranking scores) and use the existing
WalkForwardSplitter with purge+embargo.

Requires ``torch`` (optional gpu dependency).
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import numpy as np
import optuna

from qm.backtest.engine import BacktestEngine
from qm.backtest.validation.walk_forward import WalkForwardSplitter
from qm.model.trainers.sequence import SequenceNormalizer, create_sequences

logger = logging.getLogger(__name__)
optuna.logging.set_verbosity(optuna.logging.WARNING)


def _build_alstm_model(
    n_features: int,
    hidden_size: int,
    num_layers: int,
    dropout: float,
):
    """Build ALSTMModel. Import torch lazily."""
    import torch
    import torch.nn as nn
    import torch.nn.functional as F  # noqa: N812

    class ALSTMModel(nn.Module):
        """LSTM with attention over hidden states."""

        def __init__(self, n_feat: int, h_size: int, n_layers: int, drop: float):
            super().__init__()
            self.lstm = nn.LSTM(
                n_feat, h_size, n_layers,
                dropout=drop if n_layers > 1 else 0.0,
                batch_first=True,
            )
            self.attention = nn.Linear(h_size, 1)
            self.fc = nn.Linear(h_size, 1)

        def forward(self, x: torch.Tensor) -> torch.Tensor:
            h, _ = self.lstm(x)  # (batch, seq, hidden)
            attn_w = F.softmax(self.attention(h), dim=1)  # (batch, seq, 1)
            context = (h * attn_w).sum(dim=1)  # (batch, hidden)
            return torch.sigmoid(self.fc(context)).squeeze(-1)  # (batch,)

        def get_attention_weights(self, x: torch.Tensor) -> torch.Tensor:
            """Return attention weights for feature importance."""
            with torch.no_grad():
                h, _ = self.lstm(x)
                return F.softmax(self.attention(h), dim=1).squeeze(-1)

    return ALSTMModel(n_features, hidden_size, num_layers, dropout)


class ALSTMTrainer:
    """ALSTM trainer for Sentinel bar-level predictions.

    Interface matches :class:`LGBMTrainer` so it can be swapped in
    ``train_sentinel.py`` via ``--model-type alstm``.
    """

    def __init__(
        self,
        n_trials: int = 30,
        n_splits: int = 5,
        train_period: int = 5000,
        test_period: int = 1000,
        backtest_engine: BacktestEngine | None = None,
        seed: int = 42,
        seq_len: int = 20,
        use_gpu: bool = True,
    ) -> None:
        self.n_trials = n_trials
        self.n_splits = n_splits
        self.train_period = train_period
        self.test_period = test_period
        self._engine = backtest_engine or BacktestEngine()
        self.seed = seed
        self.seq_len = seq_len
        self.use_gpu = use_gpu
        self._model: Any = None  # ALSTMModel
        self._normalizer = SequenceNormalizer()
        self._best_params: dict[str, Any] = {}
        self._feature_names: list[str] = []
        self._device: Any = None  # torch.device

    def _get_device(self):
        if self._device is None:
            from qm.model.trainers.torch_device import detect_torch_device
            self._device = detect_torch_device(prefer_gpu=self.use_gpu)
        return self._device

    def _train_one_model(
        self,
        X_train: np.ndarray,
        y_train: np.ndarray,
        X_val: np.ndarray,
        y_val: np.ndarray,
        params: dict[str, Any],
    ) -> Any:
        """Train a single ALSTM model, return it."""
        import torch
        from torch.utils.data import DataLoader, TensorDataset

        device = self._get_device()
        model = _build_alstm_model(
            n_features=X_train.shape[-1],
            hidden_size=params["hidden_size"],
            num_layers=params["num_layers"],
            dropout=params["dropout"],
        ).to(device)

        optimizer = torch.optim.AdamW(
            model.parameters(),
            lr=params["lr"],
            weight_decay=params["weight_decay"],
        )
        criterion = torch.nn.BCELoss()

        train_ds = TensorDataset(
            torch.tensor(X_train, dtype=torch.float32),
            torch.tensor(y_train, dtype=torch.float32),
        )
        val_ds = TensorDataset(
            torch.tensor(X_val, dtype=torch.float32),
            torch.tensor(y_val, dtype=torch.float32),
        )
        train_dl = DataLoader(
            train_ds, batch_size=params["batch_size"], shuffle=True,
        )
        val_dl = DataLoader(val_ds, batch_size=params["batch_size"])

        scheduler = torch.optim.lr_scheduler.OneCycleLR(
            optimizer,
            max_lr=params["lr"],
            epochs=100,
            steps_per_epoch=len(train_dl),
        )

        best_val_loss = float("inf")
        patience_counter = 0
        best_state = None

        for epoch in range(100):
            # Train
            model.train()
            for xb, yb in train_dl:
                xb, yb = xb.to(device), yb.to(device)
                pred = model(xb)
                loss = criterion(pred, yb)
                optimizer.zero_grad()
                loss.backward()
                torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=1.0)
                optimizer.step()
                scheduler.step()

            # Validate
            model.eval()
            val_losses = []
            with torch.no_grad():
                for xb, yb in val_dl:
                    xb, yb = xb.to(device), yb.to(device)
                    pred = model(xb)
                    val_losses.append(criterion(pred, yb).item())
            val_loss = np.mean(val_losses)

            if val_loss < best_val_loss:
                best_val_loss = val_loss
                patience_counter = 0
                best_state = {k: v.cpu().clone() for k, v in model.state_dict().items()}
            else:
                patience_counter += 1
                if patience_counter >= 10:
                    logger.debug("Early stopping at epoch %d", epoch)
                    break

        if best_state is not None:
            model.load_state_dict(best_state)
        model.to(device)
        return model

    def _predict_with_model(
        self, model: Any, X_seq: np.ndarray, batch_size: int = 4096,
    ) -> np.ndarray:
        """Run batched inference on 3-D sequence array."""
        import torch

        device = self._get_device()
        model.eval()
        all_probs = []
        with torch.no_grad():
            for i in range(0, len(X_seq), batch_size):
                batch = torch.tensor(
                    X_seq[i : i + batch_size], dtype=torch.float32,
                ).to(device)
                all_probs.append(model(batch).cpu().numpy())
        return np.concatenate(all_probs)

    def fit(
        self,
        X: np.ndarray,
        y: np.ndarray,
        feature_names: list[str] | None = None,
        market_probs: np.ndarray | None = None,
    ) -> dict[str, float]:
        """Full training pipeline: HPO -> retrain -> return metrics."""
        import torch

        if hasattr(X, "to_numpy"):
            X = X.to_numpy()
        if hasattr(y, "to_numpy"):
            y = y.to_numpy()

        X = X.astype(np.float64)
        y = y.astype(np.float64)
        self._feature_names = feature_names or [f"f{i}" for i in range(X.shape[1])]

        splitter = WalkForwardSplitter(
            n_splits=self.n_splits,
            train_period=self.train_period,
            test_period=self.test_period,
            purge_period=12,
            embargo_period=6,
        )

        best_metrics: dict[str, float] = {}

        def objective(trial: optuna.Trial) -> float:
            params = {
                "hidden_size": trial.suggest_categorical(
                    "hidden_size", [32, 64, 128, 256],
                ),
                "num_layers": trial.suggest_int("num_layers", 1, 3),
                "dropout": trial.suggest_float("dropout", 0.1, 0.5),
                "lr": trial.suggest_float("lr", 1e-4, 1e-2, log=True),
                "batch_size": trial.suggest_categorical(
                    "batch_size", [64, 128, 256, 512],
                ),
                "weight_decay": trial.suggest_float(
                    "weight_decay", 1e-6, 1e-2, log=True,
                ),
            }

            all_oos_probs = np.full(len(y), np.nan)
            all_oos_mask = np.zeros(len(y), dtype=bool)

            for train_idx, test_idx in splitter.split(len(y)):
                # Normalize on train
                norm = SequenceNormalizer()
                X_tr_norm = norm.fit_transform(X[train_idx])
                X_te_norm = norm.transform(X[test_idx])

                # Create sequences
                X_tr_seq, y_tr_seq, vi_tr = create_sequences(
                    X_tr_norm, y[train_idx], self.seq_len,
                )
                X_te_seq, y_te_seq, vi_te = create_sequences(
                    X_te_norm, y[test_idx], self.seq_len,
                )

                if len(X_tr_seq) < 20 or len(X_te_seq) < 5:
                    continue

                # Use last 20% of train as validation for early stopping
                val_n = max(1, len(X_tr_seq) // 5)
                model = self._train_one_model(
                    X_tr_seq[:-val_n], y_tr_seq[:-val_n],
                    X_tr_seq[-val_n:], y_tr_seq[-val_n:],
                    params,
                )

                probs = self._predict_with_model(model, X_te_seq)
                # Map back to flat indices
                flat_test_indices = test_idx[vi_te]
                all_oos_probs[flat_test_indices] = probs
                all_oos_mask[flat_test_indices] = True

                del model
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()

            if not all_oos_mask.any():
                return 1.0

            oos_idx = np.where(all_oos_mask)[0]
            mp = market_probs[oos_idx] if market_probs is not None else None
            metrics = self._engine.evaluate_model_fast(
                all_oos_probs[oos_idx], y[oos_idx], mp,
            )

            nonlocal best_metrics
            brier = metrics["brier"]
            if not best_metrics or brier < best_metrics.get("brier", 1.0):
                best_metrics = metrics

            return brier

        study = optuna.create_study(
            direction="minimize",
            sampler=optuna.samplers.TPESampler(seed=self.seed),
        )
        study.optimize(objective, n_trials=self.n_trials, n_jobs=1)

        self._best_params = study.best_params
        logger.info("ALSTM HPO complete. Best Brier: %.4f", study.best_value)

        # Retrain on full data
        self._normalizer.fit(X)
        X_norm = self._normalizer.transform(X)
        X_seq, y_seq, _ = create_sequences(X_norm, y, self.seq_len)

        val_n = max(1, len(X_seq) // 10)
        params = {
            "hidden_size": self._best_params.get("hidden_size", 64),
            "num_layers": self._best_params.get("num_layers", 2),
            "dropout": self._best_params.get("dropout", 0.3),
            "lr": self._best_params.get("lr", 1e-3),
            "batch_size": self._best_params.get("batch_size", 256),
            "weight_decay": self._best_params.get("weight_decay", 1e-4),
        }
        self._model = self._train_one_model(
            X_seq[:-val_n], y_seq[:-val_n],
            X_seq[-val_n:], y_seq[-val_n:],
            params,
        )

        return best_metrics

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        """Predict P(Up). Accepts flat (n, n_features), returns (n - seq_len + 1,)."""
        if self._model is None:
            msg = "Model not trained. Call fit() first."
            raise RuntimeError(msg)
        if hasattr(X, "to_numpy"):
            X = X.to_numpy()

        X_norm = self._normalizer.transform(X.astype(np.float64))
        X_seq, _, _ = create_sequences(X_norm, np.zeros(len(X)), self.seq_len)
        if len(X_seq) == 0:
            return np.array([], dtype=np.float64)
        return self._predict_with_model(self._model, X_seq)

    def save(self, path: Path) -> None:
        """Save model + normalizer to directory."""
        import torch

        if self._model is None:
            msg = "No model to save"
            raise RuntimeError(msg)
        path.mkdir(parents=True, exist_ok=True)
        torch.save(self._model.state_dict(), path / "model.pt")
        self._normalizer.save(path / "normalizer.pkl")

        # Save architecture params for reconstruction
        import json
        meta = {
            "seq_len": self.seq_len,
            "n_features": self._model.lstm.input_size,
            "best_params": self._best_params,
            "feature_names": self._feature_names,
        }
        (path / "meta.json").write_text(json.dumps(meta))

    def load(self, path: Path) -> None:
        """Load model + normalizer from directory."""
        import json

        import torch

        meta = json.loads((path / "meta.json").read_text())
        self.seq_len = meta["seq_len"]
        self._best_params = meta["best_params"]
        self._feature_names = meta.get("feature_names", [])

        self._model = _build_alstm_model(
            n_features=meta["n_features"],
            hidden_size=self._best_params.get("hidden_size", 64),
            num_layers=self._best_params.get("num_layers", 2),
            dropout=self._best_params.get("dropout", 0.3),
        )
        self._model.load_state_dict(
            torch.load(path / "model.pt", weights_only=True),
        )
        device = self._get_device()
        self._model.to(device)
        self._model.eval()

        self._normalizer = SequenceNormalizer()
        self._normalizer.load(path / "normalizer.pkl")

    @property
    def feature_importance(self) -> dict[str, int]:
        """Placeholder — attention-based importance requires data."""
        return {}

    @property
    def best_params(self) -> dict[str, Any]:
        return self._best_params
