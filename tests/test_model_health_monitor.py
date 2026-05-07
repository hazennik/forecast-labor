"""Tests for Phase 6.3.1c model health monitoring."""

from pathlib import Path
from typing import Any
import importlib
import sys

import numpy as np
import pytest


def _health_module() -> Any:
    """Import production backtest health utilities after test collection."""
    project_root = Path(__file__).resolve().parents[1]
    if str(project_root) in sys.path:
        sys.path.remove(str(project_root))
    sys.path.insert(0, str(project_root))
    sys.modules.pop("backtests", None)
    return importlib.import_module("backtests.health")


class TestModelHealthMonitor:
    """Validate model health checks for known Phase 6 risks."""

    def test_healthy_model_run_passes_without_issues(self):
        """A well-behaved run should pass all health checks."""
        health = _health_module()
        monitor = health.ModelHealthMonitor()
        actuals = np.array([100.0, 110.0, 120.0, 130.0, 140.0])
        predictions = np.array([101.0, 109.0, 119.0, 131.0, 139.0])

        report = monitor.evaluate_model_run(
            "xgboost",
            predictions,
            actuals=actuals,
            metadata={"fold": 1},
        )

        assert report.passed is True
        assert report.has_warnings is False
        assert report.metrics["smape"] < 20.0
        assert report.to_dict()["metadata"]["fold"] == 1

    def test_dfm_instability_warning_for_large_forecasts(self):
        """DFM forecasts above 1M should be flagged for monitoring."""
        health = _health_module()
        monitor = health.ModelHealthMonitor()

        report = monitor.evaluate_model_run("dfm", [100.0, 1_250_000.0, 200.0])

        assert report.passed is True
        assert report.has_warnings is True
        assert report.issues[0].check_name == "dfm_instability"
        assert report.issues[0].severity == health.HealthCheckSeverity.WARNING

    def test_hard_magnitude_gate_is_critical_for_any_model(self):
        """Forecasts above 2M should fail the hard stability gate."""
        health = _health_module()
        monitor = health.ModelHealthMonitor()

        report = monitor.evaluate_model_run("xgboost", [100.0, 2_500_000.0])

        assert report.passed is False
        assert report.issues[0].check_name == "forecast_magnitude_hard_gate"
        assert report.issues[0].severity == health.HealthCheckSeverity.CRITICAL

    def test_non_finite_predictions_are_critical(self):
        """NaN or infinite predictions should fail immediately."""
        health = _health_module()
        monitor = health.ModelHealthMonitor()

        report = monitor.evaluate_model_run("midas", [100.0, float("nan"), 120.0])

        assert report.passed is False
        assert any(issue.check_name == "prediction_finite" for issue in report.issues)

    def test_midas_convergence_warning_is_reported(self):
        """MIDAS convergence failures should be visible in health reports."""
        health = _health_module()
        monitor = health.ModelHealthMonitor()

        report = monitor.evaluate_model_run(
            "midas",
            [100.0, 110.0, 120.0],
            convergence_warnings=["optimization_failed: maximum iterations exceeded"],
        )

        assert report.passed is True
        assert report.has_warnings is True
        assert report.metrics["convergence_warning_count"] == 1.0
        assert report.issues[0].check_name == "midas_convergence"
        assert "optimization_failed" in report.issues[0].metadata["warnings"][0]

    def test_low_coverage_is_warning(self):
        """Coverage below 85% should be flagged as overconfident intervals."""
        health = _health_module()
        monitor = health.ModelHealthMonitor()
        actuals = np.array([100.0, 110.0, 120.0, 130.0])
        predictions = np.array([100.0, 110.0, 120.0, 130.0])
        intervals = np.array(
            [
                [99.0, 101.0],
                [109.0, 111.0],
                [118.0, 119.0],
                [131.0, 132.0],
            ]
        )

        report = monitor.evaluate_model_run(
            "lightgbm",
            predictions,
            actuals=actuals,
            prediction_intervals=intervals,
        )

        assert report.passed is True
        assert report.has_warnings is True
        assert report.metrics["coverage_90"] == 50.0
        assert any(issue.check_name == "coverage_low" for issue in report.issues)

    def test_high_coverage_is_warning(self):
        """Coverage above 95% should be flagged as over-conservative intervals."""
        health = _health_module()
        monitor = health.ModelHealthMonitor()
        actuals = np.array([100.0, 110.0, 120.0, 130.0])
        predictions = np.array([100.0, 110.0, 120.0, 130.0])
        intervals = np.column_stack([actuals - 50.0, actuals + 50.0])

        report = monitor.evaluate_model_run(
            "dfm",
            predictions,
            actuals=actuals,
            prediction_intervals=intervals,
        )

        assert report.passed is True
        assert report.has_warnings is True
        assert report.metrics["coverage_90"] == 100.0
        assert any(issue.check_name == "coverage_high" for issue in report.issues)

    def test_smape_gate_warning(self):
        """Weak accuracy should be flagged even when forecasts are finite."""
        health = _health_module()
        monitor = health.ModelHealthMonitor()

        report = monitor.evaluate_model_run(
            "xgboost",
            [300.0, 300.0, 300.0],
            actuals=[100.0, 110.0, 120.0],
        )

        assert report.passed is True
        assert report.has_warnings is True
        assert report.metrics["smape"] > 20.0
        assert any(issue.check_name == "smape_gate" for issue in report.issues)

    def test_shape_mismatch_is_critical(self):
        """Mismatched actual/prediction lengths should be critical."""
        health = _health_module()
        monitor = health.ModelHealthMonitor()

        report = monitor.evaluate_model_run("revision", [100.0, 110.0], actuals=[100.0])

        assert report.passed is False
        assert any(issue.check_name == "actuals_shape" for issue in report.issues)

    def test_threshold_validation(self):
        """Invalid health thresholds should fail at construction."""
        health = _health_module()

        with pytest.raises(ValueError, match="max_abs_forecast must be positive"):
            health.HealthThresholds(max_abs_forecast=0.0)

        with pytest.raises(ValueError, match="coverage thresholds"):
            health.HealthThresholds(min_coverage_90=96.0, max_coverage_90=95.0)
