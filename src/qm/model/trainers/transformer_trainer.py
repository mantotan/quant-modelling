"""Transformer trainer with Optuna HPO and walk-forward evaluation.

Cherry-picked from Qlib's Transformer architecture.  Uses learned
positional encoding (financial sequences are not translation-invariant)
and a CLS token for sequence-level classification.

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

# Maximum sequence length for positional embedding
_MAX_SEQ_LEN = 128


def _build_transformer_model(
    n_features: int,
    d_model: int,
    n_heads: int,
    n_layers: int,
    dim_feedforward: int,
    dropout: float,
    max_seq_len: int = _MAX_SEQ_LEN,
):
    """Build TransformerModel. Import torch lazily."""
    import torch
    import torch.nn as nn

    class TransformerModel(nn.Module):
        """Transformer encoder with CLS token and learned positional encoding."""

        def __init__(
            self, n_feat: int, d_mod: int, n_hd: int, n_lay: int,
            dim_ff: int, drop: float, max_sl: int,
        ):
            super().__init__()
            self.d_model = d_mod
            self.input_proj = nn.Linear(n_feat, d_mod)
            self.pos_embed = nn.Embedding(max_sl + 1, d_mod)  # +1 for CLS
            self.cls_token = nn.Parameter(torch.randn(1, 1, d_mod) * 0.02)
            encoder_layer = nn.TransformerEncoderLayer(
                d_model=d_mod, nhead=n_hd, dim_feedforward=dim_ff,
                dropout=drop, batch_first=True,
            )
            self.encoder = nn.TransformerEncoder(encoder_layer, num_layers=n_lay)
            self.fc = nn.Linear(d_mod, 1)
            self._max_sl = max_sl

        def forward(self, x: torch.Tensor) -> torch.Tensor:
            batch, seq_len, _ = x.shape
            # Project input to d_model
            x = self.input_proj(x)
            # Add positional encoding (positions 1..seq_len, 0 reserved for CLS)
            positions = torch.arange(1, seq_len + 1, device=x.device).unsqueeze(0)
            x = x + self.pos_embed(positions)
            # Prepend CLS token
            cls = self.cls_token.expand(batch, -1, -1)
            cls = cls + self.pos_embed(torch.zeros(1, 1, dtype=torch.long, device=x.device))
            x = torch.cat([cls, x], dim=1)
            # Encode
            x = self.encoder(x)
            # CLS token output
            return torch.sigmoid(self.fc(x[:, 0])).squeeze(-1)

    return TransformerModel(
        n_features, d_model, n_heads, n_layers, dim_feedforward, dropout, max_seq_len,
    )


class TransformerTrainer:
    """Transformer trainer for Sentinel bar-level predictions.

    Interface matches :class:`LGBMTrainer` / :class:`ALSTMTrainer`.
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
        self._model: Any = None
        self._normalizer = SequenceNormalizer()
        self._best_params: dict[str, Any] = {}
        self._feature_names: list[str] = []
        self._device: Any = None

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
        """Train a single Transformer model."""
        import torch
        from torch.utils.data import DataLoader, TensorDataset

        device = self._get_device()
        model = _build_transformer_model(
            n_features=X_train.shape[-1],
            d_model=params["d_model"],
            n_heads=params["n_heads"],
            n_layers=params["n_layers"],
            dim_feedforward=params["dim_feedforward"],
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
        bs = params["batch_size"]
        train_dl = DataLoader(train_ds, batch_size=bs, shuffle=True)
        val_dl = DataLoader(val_ds, batch_size=bs)

        scheduler = torch.optim.lr_scheduler.OneCycleLR(
            optimizer, max_lr=params["lr"],
            epochs=100, steps_per_epoch=len(train_dl),
        )

        best_val_loss = float("inf")
        patience_counter = 0
        best_state = None

        for epoch in range(100):
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

            model.eval()
            val_losses = []
            with torch.no_grad():
                for xb, yb in val_dl:
                    xb, yb = xb.to(device), yb.to(device)
                    val_losses.append(criterion(model(xb), yb).item())
            val_loss = np.mean(val_losses)

            if val_loss < best_val_loss:
                best_val_loss = val_loss
                patience_counter = 0
                best_state = {
                    k: v.cpu().clone() for k, v in model.state_dict().items()
                }
            else:
                patience_counter += 1
                if patience_counter >= 10:
                    logger.debug("Transformer early stop at epoch %d", epoch)
                    break

        if best_state is not None:
            model.load_state_dict(best_state)
        model.to(device)
        return model

    def _predict_with_model(self, model: Any, X_seq: np.ndarray) -> np.ndarray:
        import torch

        device = self._get_device()
        model.eval()
        with torch.no_grad():
            t = torch.tensor(X_seq, dtype=torch.float32).to(device)
            return model(t).cpu().numpy()

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
            # Constrain d_model % n_heads == 0
            n_heads = trial.suggest_categorical("n_heads", [2, 4])
            d_model = trial.suggest_categorical(
                "d_model", [32, 64, 128],
            )
            # Ensure divisibility
            if d_model % n_heads != 0:
                d_model = max(32, (d_model // n_heads) * n_heads)

            params = {
                "d_model": d_model,
                "n_heads": n_heads,
                "n_layers": trial.suggest_int("n_layers", 1, 4),
                "dim_feedforward": trial.suggest_categorical(
                    "dim_feedforward", [64, 128, 256],
                ),
                "dropout": trial.suggest_float("dropout", 0.1, 0.5),
                "lr": trial.suggest_float("lr", 1e-4, 5e-3, log=True),
                "batch_size": trial.suggest_categorical(
                    "batch_size", [64, 128, 256],
                ),
                "weight_decay": trial.suggest_float(
                    "weight_decay", 1e-5, 1e-2, log=True,
                ),
            }

            all_oos_probs = np.full(len(y), np.nan)
            all_oos_mask = np.zeros(len(y), dtype=bool)

            for train_idx, test_idx in splitter.split(len(y)):
                norm = SequenceNormalizer()
                X_tr_norm = norm.fit_transform(X[train_idx])
                X_te_norm = norm.transform(X[test_idx])

                X_tr_seq, y_tr_seq, _ = create_sequences(
                    X_tr_norm, y[train_idx], self.seq_len,
                )
                X_te_seq, _, vi_te = create_sequences(
                    X_te_norm, y[test_idx], self.seq_len,
                )

                if len(X_tr_seq) < 100 or len(X_te_seq) < 10:
                    continue

                val_n = max(1, len(X_tr_seq) // 5)
                model = self._train_one_model(
                    X_tr_seq[:-val_n], y_tr_seq[:-val_n],
                    X_tr_seq[-val_n:], y_tr_seq[-val_n:],
                    params,
                )

                probs = self._predict_with_model(model, X_te_seq)
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
        # Fix d_model/n_heads divisibility in saved params
        if "d_model" in self._best_params and "n_heads" in self._best_params:
            d = self._best_params["d_model"]
            h = self._best_params["n_heads"]
            if d % h != 0:
                self._best_params["d_model"] = max(32, (d // h) * h)

        logger.info("Transformer HPO complete. Best Brier: %.4f", study.best_value)

        # Retrain on full data
        self._normalizer.fit(X)
        X_norm = self._normalizer.transform(X)
        X_seq, y_seq, _ = create_sequences(X_norm, y, self.seq_len)

        val_n = max(1, len(X_seq) // 10)
        params = {
            "d_model": self._best_params.get("d_model", 64),
            "n_heads": self._best_params.get("n_heads", 4),
            "n_layers": self._best_params.get("n_layers", 2),
            "dim_feedforward": self._best_params.get("dim_feedforward", 128),
            "dropout": self._best_params.get("dropout", 0.3),
            "lr": self._best_params.get("lr", 1e-3),
            "batch_size": self._best_params.get("batch_size", 128),
            "weight_decay": self._best_params.get("weight_decay", 1e-4),
        }
        self._model = self._train_one_model(
            X_seq[:-val_n], y_seq[:-val_n],
            X_seq[-val_n:], y_seq[-val_n:],
            params,
        )

        return best_metrics

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        """Predict P(Up). Accepts flat (n, n_features)."""
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
        import json

        import torch

        if self._model is None:
            msg = "No model to save"
            raise RuntimeError(msg)
        path.mkdir(parents=True, exist_ok=True)
        torch.save(self._model.state_dict(), path / "model.pt")
        self._normalizer.save(path / "normalizer.pkl")

        meta = {
            "seq_len": self.seq_len,
            "n_features": self._model.input_proj.in_features,
            "best_params": self._best_params,
            "feature_names": self._feature_names,
        }
        (path / "meta.json").write_text(json.dumps(meta))

    def load(self, path: Path) -> None:
        import json

        import torch

        meta = json.loads((path / "meta.json").read_text())
        self.seq_len = meta["seq_len"]
        self._best_params = meta["best_params"]
        self._feature_names = meta.get("feature_names", [])

        self._model = _build_transformer_model(
            n_features=meta["n_features"],
            d_model=self._best_params.get("d_model", 64),
            n_heads=self._best_params.get("n_heads", 4),
            n_layers=self._best_params.get("n_layers", 2),
            dim_feedforward=self._best_params.get("dim_feedforward", 128),
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
        return {}

    @property
    def best_params(self) -> dict[str, Any]:
        return self._best_params
