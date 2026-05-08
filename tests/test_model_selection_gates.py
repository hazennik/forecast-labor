"""Tests for Phase 6.4.2 model selection and accuracy gates."""

from __future__ import annotations

from pathlib import Path
from typing import Any
import importlib
import json
import sys

import pytest


def _selection_module() -> Any:
    """Import selection utilities after test collection."""
    project_root = Path(__file__).resolve().parents[1]
    if str(project_root) in sys.path:
        sys.path.remove(str(project_root))
    sys.path.insert(0, str(project_root))
    sys.modules.pop("backtests", None)
    return importlib.import_module("backtests.selection")


def _reports_module() -> Any:
    """Import report utilities after test collection."""
    project_root = Path(__file__).resolve().parents[1]
    if str(project_root) in sys.path:
        sys.path.remove(str(project_root))
    sys.path.insert(0, str(project_root))
    sys.modules.pop("backtests", None)
    return importlib.import_module("backtests.reports")


def _candidate_payload(error: float) -> dict[str, Any]:
    """Build a candidate payload with valid intervals and coherent probabilities."""
    actuals = [100_000.0 + 1_000.0 * index for index in range(20)]
    predictions = [actual + error for actual in actuals]
    intervals = []
    for index, (actual, prediction) in enumerate(zip(actuals, predictions)):
        if index < 2:
            intervals.append([prediction + 100.0, prediction + 2_000.0])
        else:
            intervals.append([prediction - 2_000.0, prediction + 2_000.0])

    binary_actuals = [0] * 10 + [1] * 10
    probabilities = [[0.98, 0.02] for _ in range(10)] + [[0.02, 0.98] for _ in range(10)]
    return {
        "actuals": actuals,
        "predictions": predictions,
        "prediction_intervals": intervals,
        "component_sum_predictions": [prediction - 10.0 for prediction in predictions],
        "probabilities": probabilities,
        "probability_history": [
            [0.30, 0.40, 0.30],
            [0.31, 0.39, 0.30],
            [0.32, 0.38, 0.30],
        ],
        "binary_actuals": binary_actuals,
        "revision_actuals": [5_000.0, -10_000.0, 20_000.0],
        "revision_predictions": [4_000.0, -11_000.0, 19_000.0],
        "turning_point_actuals": [100.0, 90.0, 110.0, 95.0, 120.0],
        "turning_point_predictions": [101.0, 89.0, 111.0, 94.0, 121.0],
        "state_actuals": {
            "CA": [10_000.0, 12_000.0],
            "TX": [8_000.0, 9_000.0],
            "NY": [6_000.0, 7_000.0],
            "FL": [5_000.0, 6_000.0],
            "PA": [4_000.0, 5_000.0],
        },
        "state_predictions": {
            "CA": [11_000.0, 11_500.0],
            "TX": [8_500.0, 9_500.0],
            "NY": [6_500.0, 6_500.0],
            "FL": [5_500.0, 6_500.0],
            "PA": [4_500.0, 5_500.0],
        },
    }


def _selection_payload() -> dict[str, Any]:
    """Return a representative Phase 6.4.2 selection payload."""
    return {
        "candidates": {
            "midas": _candidate_payload(error=300.0),
            "xgboost": _candidate_payload(error=1_000.0),
            "lightgbm": _candidate_payload(error=700.0),
            "dfm": _candidate_payload(error=20_000.0),
        },
        "production_candidates": ["midas", "xgboost", "lightgbm"],
        "excluded_models": ["dfm"],
        "metadata": {"vintage_date": "2025-11-29"},
    }


class TestModelSelectionGates:
    """Validate accuracy gates and model selection behavior."""

    def test_best_eligible_model_is_selected(self) -> None:
        """The lowest-scoring eligible production candidate should be selected."""
        selection = _selection_module()

        report = selection.evaluate_model_selection(**_selection_payload())

        assert report.passed is True
        assert report.selected_model == "midas"
        assert report.candidate_scores[0].model_name == "midas"
        assert report.candidate_scores[0].rank == 1
        assert report.candidate_scores[0].eligible is True
        assert any(gate.name == "model_selection" and gate.passed for gate in report.gates)

    def test_accuracy_gate_failure_blocks_selection(self) -> None:
        """A candidate with poor point accuracy should be ineligible."""
        selection = _selection_module()
        payload = _selection_payload()
        payload["candidates"]["midas"] = _candidate_payload(error=80_000.0)

        report = selection.evaluate_model_selection(**payload)

        midas = next(score for score in report.candidate_scores if score.model_name == "midas")
        assert midas.eligible is False
        assert any(gate.name == "rmse" and not gate.passed for gate in midas.gates)
        assert report.selected_model == "lightgbm"

    def test_probability_coherence_gate_is_critical(self) -> None:
        """Probability vectors must sum to one within the deployment tolerance."""
        selection = _selection_module()
        payload = _selection_payload()
        payload["candidates"]["midas"]["probabilities"][0] = [0.40, 0.40]

        report = selection.evaluate_model_selection(**payload)

        midas = next(score for score in report.candidate_scores if score.model_name == "midas")
        assert midas.eligible is False
        assert any(
            gate.name == "probability_coherence"
            and gate.severity == selection.AccuracyGateSeverity.CRITICAL
            for gate in midas.gates
        )

    def test_phase_6_4_2_extended_gates_are_recorded(self) -> None:
        """The validator should cover the full Phase 6.4.2 gate checklist."""
        selection = _selection_module()

        report = selection.evaluate_model_selection(**_selection_payload())
        midas = next(score for score in report.candidate_scores if score.model_name == "midas")
        gate_names = {gate.name for gate in midas.gates}

        assert {
            "forecast_stability",
            "hierarchical_coherence",
            "revision_direction_accuracy",
            "turning_point_precision",
            "state_level_accuracy",
            "probability_stability",
        }.issubset(gate_names)
        assert midas.metrics["states_passing_accuracy"] == 5.0
        assert midas.metrics["revision_direction_accuracy"] == 100.0

    def test_state_level_accuracy_gate_can_fail(self) -> None:
        """State-level validation should enforce the top-state passing count."""
        selection = _selection_module()
        payload = _selection_payload()
        payload["candidates"]["midas"]["state_predictions"] = {
            state: [100_000.0, 100_000.0]
            for state in payload["candidates"]["midas"]["state_actuals"]
        }

        report = selection.evaluate_model_selection(**payload)

        midas = next(score for score in report.candidate_scores if score.model_name == "midas")
        assert midas.eligible is False
        assert any(gate.name == "state_level_accuracy" and not gate.passed for gate in midas.gates)

    def test_probability_stability_gate_can_fail(self) -> None:
        """SN41 probability stability should flag unstable probability paths."""
        selection = _selection_module()
        payload = _selection_payload()
        payload["candidates"]["midas"]["probability_history"] = [
            [0.90, 0.05, 0.05],
            [0.05, 0.90, 0.05],
        ]

        report = selection.evaluate_model_selection(**payload)

        midas = next(score for score in report.candidate_scores if score.model_name == "midas")
        assert midas.eligible is False
        assert any(gate.name == "probability_stability" and not gate.passed for gate in midas.gates)

    def test_excluded_dfm_cannot_be_selected(self) -> None:
        """DFM remains diagnostic-only even when its synthetic metrics are strong."""
        selection = _selection_module()
        payload = _selection_payload()
        payload["candidates"]["dfm"] = _candidate_payload(error=10.0)

        report = selection.evaluate_model_selection(**payload)

        dfm = next(score for score in report.candidate_scores if score.model_name == "dfm")
        assert dfm.eligible is False
        assert report.selected_model == "midas"
        assert any(gate.name == "model_exclusion" for gate in dfm.gates)

    def test_missing_production_candidate_fails_portfolio_gate(self) -> None:
        """The report should fail when expected candidate results are absent."""
        selection = _selection_module()
        payload = _selection_payload()
        payload["candidates"].pop("lightgbm")

        report = selection.evaluate_model_selection(**payload)

        assert report.passed is False
        assert any(
            gate.name == "production_candidate_coverage" and not gate.passed
            for gate in report.gates
        )

    def test_file_validation_writes_json_report(self, tmp_path: Path) -> None:
        """File-level validation should persist a JSON report when requested."""
        selection = _selection_module()
        input_path = tmp_path / "selection_input.json"
        report_path = tmp_path / "selection_report.json"
        input_path.write_text(json.dumps(_selection_payload()), encoding="utf-8")

        report = selection.evaluate_model_selection_file(input_path, report_path=report_path)

        assert report.passed is True
        written = json.loads(report_path.read_text(encoding="utf-8"))
        assert written["selected_model"] == "midas"
        assert written["metadata"]["vintage_date"] == "2025-11-29"

    def test_invalid_thresholds_fail_early(self) -> None:
        """Invalid threshold configuration should raise before evaluation."""
        selection = _selection_module()

        with pytest.raises(ValueError, match="max_smape"):
            selection.AccuracyGateThresholds(max_smape=0)

        with pytest.raises(ValueError, match="coverage thresholds"):
            selection.AccuracyGateThresholds(min_coverage_90=96, max_coverage_90=95)

    def test_selection_report_feeds_backtest_report_accuracy_section(self) -> None:
        """Phase 6.4.1 reports should render Phase 6.4.2 gate payloads."""
        selection = _selection_module()
        reports = _reports_module()
        selection_report = selection.evaluate_model_selection(**_selection_payload())

        backtest_report = reports.generate_backtest_report(
            accuracy_gates=selection_report.to_dict(),
            metadata={"validation": "phase_6_4_2"},
        )

        assert "Selected model: midas" in backtest_report.markdown
        assert "probability_coherence" in backtest_report.html
