"""Tests for Phase 6.3.2 comprehensive performance validation."""

from pathlib import Path
from typing import Any
import importlib
import json
import sys

import pytest


def _performance_module() -> Any:
    """Import production performance utilities after test collection."""
    project_root = Path(__file__).resolve().parents[1]
    if str(project_root) in sys.path:
        sys.path.remove(str(project_root))
    sys.path.insert(0, str(project_root))
    sys.modules.pop("backtests", None)
    return importlib.import_module("backtests.performance")


def _baseline_payload() -> dict:
    """Return a compact measured-baseline payload for tests."""
    return {
        "_purpose": "Track real model performance over time to detect regressions",
        "real_models": {
            "midas": {
                "training_time_sec": 0.12,
                "prediction_time_sec": 0.001,
                "memory_mb": 0.2,
            },
            "xgboost": {
                "training_time_sec": 0.24,
                "prediction_time_sec": 0.012,
                "memory_mb": 7.0,
            },
            "lightgbm": {
                "training_time_sec": 0.20,
                "prediction_time_sec": 0.016,
                "memory_mb": 9.0,
            },
            "revision": {
                "training_time_sec": 0.01,
                "prediction_time_sec": 0.001,
                "memory_mb": 0.1,
            },
            "dfm": {
                "training_time_sec": 0.16,
                "prediction_time_sec": 0.003,
                "memory_mb": 12.0,
                "production_inclusion": False,
            },
            "full_pipeline": {
                "training_time_sec": 0.57,
                "prediction_time_sec": 0.03,
                "memory_mb": 16.3,
                "throughput_pred_per_sec": 400.0,
                "included_models": ["midas", "xgboost", "lightgbm", "revision"],
                "excluded_models": ["dfm"],
            },
        },
        "slas": {
            "full_pipeline_max_minutes": 30,
            "prediction_latency_max_ms": 1000,
            "memory_limit_mb": 4096,
        },
    }


class TestPerformanceValidation:
    """Validate comprehensive performance report behavior."""

    def test_valid_baseline_passes_sla_checks(self):
        """Measured pipeline should pass when under all SLA limits."""
        performance = _performance_module()

        report = performance.validate_performance_baseline(_baseline_payload())

        assert report.passed is True
        assert report.pipeline_summary["included_models"] == [
            "midas",
            "xgboost",
            "lightgbm",
            "revision",
        ]
        assert report.pipeline_summary["excluded_models"] == ["dfm"]
        assert report.pipeline_summary["prediction_latency_ms"] == 30.0
        assert report.pipeline_summary["dominant_training_component"] == "xgboost"
        assert report.pipeline_summary["dominant_prediction_component"] == "lightgbm"
        assert report.pipeline_summary["dominant_memory_component"] == "lightgbm"
        assert any(finding.check_name == "dfm_exclusion" for finding in report.findings)

    def test_report_is_json_serializable(self):
        """Validation report payload should be usable by future report generators."""
        performance = _performance_module()
        report = performance.validate_performance_baseline(_baseline_payload())

        payload = report.to_dict()

        assert payload["passed"] is True
        assert payload["pipeline_summary"]["memory_mb"] == 16.3
        assert payload["component_profiles"][0]["model_name"] == "xgboost"
        json.dumps(payload)

    def test_training_sla_failure_is_critical(self):
        """Training time over the SLA should fail the report."""
        performance = _performance_module()
        payload = _baseline_payload()
        payload["real_models"]["full_pipeline"]["training_time_sec"] = 3600.0

        report = performance.validate_performance_baseline(payload)

        assert report.passed is False
        assert any(
            finding.check_name == "full_pipeline_training_sla"
            and finding.severity == performance.PerformanceSeverity.CRITICAL
            for finding in report.findings
        )

    def test_latency_sla_failure_is_critical(self):
        """Prediction latency over the SLA should fail the report."""
        performance = _performance_module()
        payload = _baseline_payload()
        payload["real_models"]["full_pipeline"]["prediction_time_sec"] = 2.0

        report = performance.validate_performance_baseline(payload)

        assert report.passed is False
        assert any(
            finding.check_name == "prediction_latency_sla"
            and finding.severity == performance.PerformanceSeverity.CRITICAL
            for finding in report.findings
        )

    def test_memory_sla_failure_is_critical(self):
        """Memory over the SLA should fail the report."""
        performance = _performance_module()
        payload = _baseline_payload()
        payload["real_models"]["full_pipeline"]["memory_mb"] = 5000.0

        report = performance.validate_performance_baseline(payload)

        assert report.passed is False
        assert any(
            finding.check_name == "memory_sla"
            and finding.severity == performance.PerformanceSeverity.CRITICAL
            for finding in report.findings
        )

    def test_missing_candidate_model_is_critical(self):
        """The pipeline composition check should protect candidate coverage."""
        performance = _performance_module()
        payload = _baseline_payload()
        payload["real_models"]["full_pipeline"]["included_models"] = ["midas", "xgboost"]

        report = performance.validate_performance_baseline(payload)

        assert report.passed is False
        assert any(
            finding.check_name == "pipeline_candidate_composition"
            and finding.severity == performance.PerformanceSeverity.CRITICAL
            for finding in report.findings
        )

    def test_missing_dfm_exclusion_is_warning(self):
        """DFM should remain explicitly excluded from current production candidates."""
        performance = _performance_module()
        payload = _baseline_payload()
        payload["real_models"]["full_pipeline"]["excluded_models"] = []

        report = performance.validate_performance_baseline(payload)

        assert report.passed is True
        assert any(
            finding.check_name == "dfm_exclusion"
            and finding.severity == performance.PerformanceSeverity.WARNING
            for finding in report.findings
        )

    def test_bottleneck_warning_is_recorded(self):
        """Components dominating a dimension should be called out as bottlenecks."""
        performance = _performance_module()
        payload = _baseline_payload()
        payload["real_models"]["xgboost"]["training_time_sec"] = 10.0

        report = performance.validate_performance_baseline(payload)

        assert any(
            finding.check_name == "training_bottleneck"
            and finding.severity == performance.PerformanceSeverity.WARNING
            and finding.metadata["model_name"] == "xgboost"
            for finding in report.findings
        )

    def test_validate_file_writes_report(self, tmp_path):
        """File-level validation should optionally persist a report."""
        performance = _performance_module()
        baseline_path = tmp_path / "baseline.json"
        report_path = tmp_path / "report.json"
        baseline_path.write_text(json.dumps(_baseline_payload()), encoding="utf-8")

        report = performance.validate_performance_baseline_file(
            baseline_path,
            report_path=report_path,
        )

        assert report.passed is True
        assert report_path.exists()
        written = json.loads(report_path.read_text(encoding="utf-8"))
        assert written["pipeline_summary"]["included_models"] == [
            "midas",
            "xgboost",
            "lightgbm",
            "revision",
        ]

    def test_sla_validation(self):
        """Invalid SLA settings should fail early."""
        performance = _performance_module()

        with pytest.raises(ValueError, match="full_pipeline_max_minutes"):
            performance.PerformanceSLA(full_pipeline_max_minutes=0)

        with pytest.raises(ValueError, match="bottleneck_warning_share"):
            performance.PerformanceSLA(bottleneck_warning_share=1.5)
