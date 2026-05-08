"""Tests for Phase 6.4.3 scenario testing."""

from __future__ import annotations

from pathlib import Path
from typing import Any
import importlib
import json
import sys

import pytest


def _scenarios_module() -> Any:
    """Import scenario utilities after test collection."""
    project_root = Path(__file__).resolve().parents[1]
    if str(project_root) in sys.path:
        sys.path.remove(str(project_root))
    sys.path.insert(0, str(project_root))
    sys.modules.pop("backtests", None)
    return importlib.import_module("backtests.scenarios")


def _scenario_payload() -> dict[str, Any]:
    """Return a representative scenario payload."""
    return {
        "baseline_forecast": 180_000.0,
        "baseline_features": {
            "storm_severity_index": 0.5,
            "weekly_hours_growth": 0.4,
            "strike_workers": 5_000.0,
            "payroll_diffusion_index": 53.0,
            "policy_uncertainty_index": 100.0,
            "withholding_growth": 2.0,
        },
        "feature_sensitivities": {
            "storm_severity_index": -3_000.0,
            "weekly_hours_growth": 8_000.0,
            "strike_workers": -0.08,
            "payroll_diffusion_index": 1_500.0,
            "policy_uncertainty_index": -120.0,
            "withholding_growth": 12_000.0,
        },
        "metadata": {"vintage_date": "2025-11-29"},
    }


class TestScenarioTesting:
    """Validate Phase 6.4.3 scenario testing behavior."""

    def test_default_scenarios_pass_with_expected_directions(self) -> None:
        """Default storm, strike, and policy scenarios should be audited."""
        scenarios = _scenarios_module()
        payload = _scenario_payload()

        report = scenarios.evaluate_scenarios(**payload)

        assert report.passed is True
        assert [result.category for result in report.results] == ["storm", "strike", "policy"]
        assert all(result.forecast_delta < 0.0 for result in report.results)
        assert report.metadata["vintage_date"] == "2025-11-29"

    def test_report_is_json_serializable(self) -> None:
        """Scenario reports should be usable by report and audit tooling."""
        scenarios = _scenarios_module()

        report = scenarios.evaluate_scenarios(**_scenario_payload())
        payload = report.to_dict()

        assert payload["passed"] is True
        assert payload["results"][0]["scenario_name"] == "major_hurricane_labor_disruption"
        json.dumps(payload)

    def test_direction_failure_is_critical(self) -> None:
        """A scenario with the wrong directional response should fail."""
        scenarios = _scenarios_module()
        payload = _scenario_payload()
        payload["feature_sensitivities"]["storm_severity_index"] = 10_000.0
        payload["feature_sensitivities"]["weekly_hours_growth"] = -1_000.0

        report = scenarios.evaluate_scenarios(**payload)

        storm = next(result for result in report.results if result.category == "storm")
        assert report.passed is False
        assert any(
            finding.check_name == "scenario_direction"
            and finding.severity == scenarios.ScenarioSeverity.CRITICAL
            for finding in storm.findings
        )

    def test_missing_sensitivity_is_critical(self) -> None:
        """Every shocked feature should have a forecast sensitivity."""
        scenarios = _scenarios_module()
        payload = _scenario_payload()
        payload["feature_sensitivities"].pop("strike_workers")

        report = scenarios.evaluate_scenarios(**payload)

        strike = next(result for result in report.results if result.category == "strike")
        assert strike.passed is False
        assert any(
            finding.check_name == "scenario_sensitivity_coverage"
            for finding in strike.findings
        )

    def test_forecast_magnitude_gate_is_critical(self) -> None:
        """Scenario forecasts must respect hard magnitude bounds."""
        scenarios = _scenarios_module()
        payload = _scenario_payload()
        payload["baseline_forecast"] = 3_000_000.0

        report = scenarios.evaluate_scenarios(**payload)

        assert report.passed is False
        assert any(
            finding.check_name == "scenario_forecast_magnitude"
            and finding.severity == scenarios.ScenarioSeverity.CRITICAL
            for result in report.results
            for finding in result.findings
        )

    def test_custom_neutral_scenario_uses_tolerance(self) -> None:
        """Neutral scenarios should pass when impact stays within tolerance."""
        scenarios = _scenarios_module()
        payload = _scenario_payload()
        neutral = scenarios.ScenarioDefinition(
            name="small_calendar_reclassification",
            category="policy",
            expected_direction="neutral",
            shocks=[
                scenarios.ScenarioShock(
                    "withholding_growth",
                    scenarios.ShockOperation.ADD,
                    0.01,
                )
            ],
        )

        report = scenarios.evaluate_scenarios(
            baseline_features=payload["baseline_features"],
            baseline_forecast=payload["baseline_forecast"],
            feature_sensitivities=payload["feature_sensitivities"],
            scenarios=[neutral],
        )

        assert report.passed is True
        assert abs(report.results[0].forecast_delta) <= report.thresholds.neutral_tolerance

    def test_file_validation_writes_report(self, tmp_path: Path) -> None:
        """File-level scenario validation should optionally persist JSON."""
        scenarios = _scenarios_module()
        input_path = tmp_path / "scenario_input.json"
        report_path = tmp_path / "scenario_report.json"
        input_path.write_text(json.dumps(_scenario_payload()), encoding="utf-8")

        report = scenarios.evaluate_scenario_file(input_path, report_path=report_path)

        assert report.passed is True
        written = json.loads(report_path.read_text(encoding="utf-8"))
        assert written["results"][1]["category"] == "strike"
        assert written["metadata"]["vintage_date"] == "2025-11-29"

    def test_invalid_definitions_fail_early(self) -> None:
        """Invalid scenario and threshold definitions should raise immediately."""
        scenarios = _scenarios_module()

        with pytest.raises(ValueError, match="expected_direction"):
            scenarios.ScenarioDefinition(
                name="bad",
                category="policy",
                expected_direction="sideways",
                shocks=[scenarios.ScenarioShock("x", scenarios.ShockOperation.ADD, 1.0)],
            )

        with pytest.raises(ValueError, match="max_abs_forecast"):
            scenarios.ScenarioThresholds(max_abs_forecast=0.0)
