"""Tests for load_resolutions() fix: multi-prediction condition_id aggregation.

Verifies that when multiple resolution records share a condition_id, PnL
is summed correctly instead of being overwritten by the last record.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent / "scripts"))

from replay_backtest import build_arrays, load_resolutions


class TestLoadResolutionsAccumulates:
    """Verify load_resolutions() accumulates instead of overwriting."""

    def test_single_resolution_per_condition(self, tmp_path: Path):
        """Single resolution per condition_id works as before."""
        log_dir = tmp_path / "ETH_5m"
        log_dir.mkdir(parents=True)

        events = [
            {"type": "resolution", "condition_id": "cid_1", "outcome": "UP", "pnl": 10.0},
            {"type": "resolution", "condition_id": "cid_2", "outcome": "DOWN", "pnl": -5.0},
        ]
        jsonl = log_dir / "trades_2026-03-20.jsonl"
        jsonl.write_text("\n".join(json.dumps(e) for e in events), encoding="utf-8")

        result = load_resolutions(tmp_path, "ETH", "5m", None)

        assert len(result) == 2
        assert len(result["cid_1"]) == 1
        assert len(result["cid_2"]) == 1
        assert result["cid_1"][0]["pnl"] == 10.0
        assert result["cid_2"][0]["pnl"] == -5.0

    def test_multiple_resolutions_same_condition_id(self, tmp_path: Path):
        """Multiple resolutions for one condition_id must all be kept."""
        log_dir = tmp_path / "ETH_5m"
        log_dir.mkdir(parents=True)

        events = [
            {"type": "resolution", "condition_id": "cid_1", "outcome": "UP", "pnl": 15.0},
            {"type": "resolution", "condition_id": "cid_1", "outcome": "UP", "pnl": 8.0},
            {"type": "resolution", "condition_id": "cid_1", "outcome": "UP", "pnl": 0.0},
        ]
        jsonl = log_dir / "trades_2026-03-20.jsonl"
        jsonl.write_text("\n".join(json.dumps(e) for e in events), encoding="utf-8")

        result = load_resolutions(tmp_path, "ETH", "5m", None)

        assert len(result) == 1
        assert len(result["cid_1"]) == 3
        total_pnl = sum(r["pnl"] for r in result["cid_1"])
        assert total_pnl == pytest.approx(23.0, abs=0.01)

    def test_clobbering_bug_would_lose_pnl(self, tmp_path: Path):
        """Regression: old code would keep only the last record (pnl=0)."""
        log_dir = tmp_path / "ETH_5m"
        log_dir.mkdir(parents=True)

        # Simulates the real bug: filled prediction with pnl=+210.96
        # followed by unfilled prediction with pnl=0 for the same condition_id
        events = [
            {"type": "resolution", "condition_id": "cid_x", "outcome": "UP", "pnl": 210.96},
            {"type": "resolution", "condition_id": "cid_x", "outcome": "UP", "pnl": 0.0},
        ]
        jsonl = log_dir / "trades_2026-03-20.jsonl"
        jsonl.write_text("\n".join(json.dumps(e) for e in events), encoding="utf-8")

        result = load_resolutions(tmp_path, "ETH", "5m", None)

        # Must have both records, not just the last one
        assert len(result["cid_x"]) == 2
        total = sum(r["pnl"] for r in result["cid_x"])
        assert total == pytest.approx(210.96, abs=0.01)

    def test_nonexistent_dir_returns_empty(self, tmp_path: Path):
        """Missing directory returns empty dict."""
        result = load_resolutions(tmp_path, "ETH", "5m", None)
        assert result == {}

    def test_non_resolution_events_ignored(self, tmp_path: Path):
        """Prediction events should not appear in resolutions."""
        log_dir = tmp_path / "ETH_5m"
        log_dir.mkdir(parents=True)

        events = [
            {"type": "prediction", "condition_id": "cid_1", "model_prob": 0.7},
            {"type": "resolution", "condition_id": "cid_1", "outcome": "UP", "pnl": 5.0},
        ]
        jsonl = log_dir / "trades_2026-03-20.jsonl"
        jsonl.write_text("\n".join(json.dumps(e) for e in events), encoding="utf-8")

        result = load_resolutions(tmp_path, "ETH", "5m", None)
        assert len(result) == 1
        assert len(result["cid_1"]) == 1

    def test_date_filter(self, tmp_path: Path):
        """Date filter should only load matching file."""
        log_dir = tmp_path / "ETH_5m"
        log_dir.mkdir(parents=True)

        evt_a = {"type": "resolution", "condition_id": "cid_a",
                 "outcome": "UP", "pnl": 1.0}
        (log_dir / "trades_2026-03-20.jsonl").write_text(
            json.dumps(evt_a), encoding="utf-8",
        )
        evt_b = {"type": "resolution", "condition_id": "cid_b",
                 "outcome": "DOWN", "pnl": -2.0}
        (log_dir / "trades_2026-03-21.jsonl").write_text(
            json.dumps(evt_b), encoding="utf-8",
        )

        result = load_resolutions(tmp_path, "ETH", "5m", "2026-03-20")
        assert "cid_a" in result
        assert "cid_b" not in result


class TestBuildArraysWithAggregatedResolutions:
    """Verify build_arrays() correctly uses list-based resolutions."""

    def _make_predictions(self, condition_ids: list[str]) -> list[dict]:
        return [
            {
                "condition_id": cid,
                "model_prob": 0.75,
                "market_prob": 0.50,
                "elapsed_pct": 0.50,
                "bar_id": i,
                "fill_status": "filled",
                "fill_price": 0.50,
                "size_usd": 25.0,
                "market_spread": 0.02,
                "signal_side": "UP",
            }
            for i, cid in enumerate(condition_ids)
        ]

    def test_single_resolution_per_condition(self):
        """Single resolution per condition works correctly."""
        predictions = self._make_predictions(["cid_1", "cid_2"])
        resolutions = {
            "cid_1": [{"outcome": "UP", "pnl": 10.0}],
            "cid_2": [{"outcome": "DOWN", "pnl": -5.0}],
        }

        arrays = build_arrays(predictions, resolutions)
        assert arrays is not None
        assert arrays["targets"][0] == 1.0
        assert arrays["targets"][1] == 0.0
        # paper_pnls computed from fills: signal_side=UP, fp=0.50, size=25
        # cid_1 outcome=UP → correct → shares=50, pnl=50*(1-0.50)=25.0
        # cid_2 outcome=DOWN → wrong (bet UP) → pnl=-25.0
        assert arrays["paper_pnls"][0] == pytest.approx(25.0)
        assert arrays["paper_pnls"][1] == pytest.approx(-25.0)

    def test_multi_resolution_pnl_consistent(self):
        """Multiple resolutions for same cid: paper_pnl comes from fills, not resolution logs."""
        predictions = self._make_predictions(["cid_1"])
        resolutions = {
            "cid_1": [
                {"outcome": "UP", "pnl": 15.0},
                {"outcome": "UP", "pnl": 8.0},
                {"outcome": "UP", "pnl": 0.0},
            ],
        }

        arrays = build_arrays(predictions, resolutions)
        assert arrays is not None
        # paper_pnls from fill data: signal_side=UP, outcome=UP, correct
        # shares=25/0.50=50, pnl=50*(1-0.50)=25.0
        assert arrays["paper_pnls"][0] == pytest.approx(25.0, abs=0.01)

    def test_unfilled_prediction_gets_zero_pnl(self):
        """Unfilled predictions should have zero PnL regardless of resolutions."""
        predictions = self._make_predictions(["cid_1"])
        predictions[0]["fill_status"] = "no_trade"
        resolutions = {
            "cid_1": [{"outcome": "UP", "pnl": 100.0}],
        }

        arrays = build_arrays(predictions, resolutions)
        assert arrays is not None
        assert arrays["paper_pnls"][0] == pytest.approx(0.0)

    def test_unresolved_predictions_excluded(self):
        """Predictions without resolutions should be excluded."""
        predictions = self._make_predictions(["cid_1", "cid_2"])
        resolutions = {
            "cid_1": [{"outcome": "UP", "pnl": 5.0}],
        }

        arrays = build_arrays(predictions, resolutions)
        assert arrays is not None
        assert len(arrays["model_probs"]) == 1

    def test_empty_predictions_returns_none(self):
        """Empty predictions list should return None."""
        result = build_arrays([], {})
        assert result is None

    def test_multi_prediction_same_condition_independent_pnl(self):
        """Multiple filled predictions sharing a condition_id get independent PnL from fills."""
        predictions = self._make_predictions(["cid_1", "cid_1"])
        resolutions = {
            "cid_1": [
                {"outcome": "UP", "pnl": 15.0},
                {"outcome": "UP", "pnl": 0.0},
            ],
        }
        arrays = build_arrays(predictions, resolutions)
        assert arrays is not None
        # Both predictions: signal_side=UP, outcome=UP, correct
        # Each: shares=25/0.50=50, pnl=50*(1-0.50)=25.0
        assert arrays["paper_pnls"][0] == pytest.approx(25.0, abs=0.01)
        assert arrays["paper_pnls"][1] == pytest.approx(25.0, abs=0.01)
        assert arrays["paper_pnls"].sum() == pytest.approx(50.0, abs=0.01)

    def test_no_resolutions_returns_none(self):
        """No matching resolutions should return None with warning."""
        predictions = self._make_predictions(["cid_1"])
        result = build_arrays(predictions, {})
        assert result is None
