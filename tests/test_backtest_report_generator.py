"""Tests for Phase 6.4.1 backtest report generation."""

from __future__ import annotations

from pathlib import Path
from typing import Any
import importlib
import json
import sys

import pytest


def _reports_module() -> Any:
    """Import report utilities after test collection."""
    project_root = Path(__file__).resolve().parents[1]
    if str(project_root) in sys.path:
        sys.path.remove(str(project_root))
    sys.path.insert(0, str(project_root))
    sys.modules.pop("backtests", None)
    return importlib.import_module("backtests.reports")


@pytest.fixture
def performance_payload() -> dict[str, Any]:
    """Provide a representative performance validation payload."""
    return {
        "passed": True,
        "pipeline_summary": {
            "training_time_sec": 0.565893,
            "prediction_time_sec": 0.029653,
            "prediction_latency_ms": 29.653,
            "memory_mb": 16.001,
            "included_models": ["midas", "xgboost", "lightgbm", "revision"],
            "excluded_models": ["dfm"],
        },
        "findings": [
            {
                "check_name": "prediction_bottleneck",
                "severity": "warning",
                "message": "LightGBM dominates prediction latency share",
            }
        ],
    }


@pytest.fixture
def health_payloads() -> list[dict[str, Any]]:
    """Provide representative model health payloads."""
    return [
        {
            "model_name": "midas",
            "passed": True,
            "issues": [],
        },
        {
            "model_name": "lightgbm",
            "passed": False,
            "issues": [
                {
                    "check_name": "coverage_90",
                    "severity": "warning",
                    "message": "90% interval coverage is above calibration target",
                }
            ],
        },
    ]


class TestBacktestReportGenerator:
    """Validate report generation behavior."""

    def test_generate_report_contains_required_sections(
        self,
        performance_payload: dict[str, Any],
        health_payloads: list[dict[str, Any]],
    ) -> None:
        """Report should include executive, performance, health, and accuracy sections."""
        reports = _reports_module()

        report = reports.generate_backtest_report(
            performance_report=performance_payload,
            health_reports=health_payloads,
            metadata={"vintage_date": "2025-11-29"},
        )

        assert report.metadata["phase"] == "6.4.1"
        assert [section.title for section in report.sections] == [
            "Executive Summary",
            "Performance Validation",
            "Model Health",
            "Accuracy Gates",
        ]
        assert "LightGBM dominates prediction latency share" in report.markdown
        assert "Accuracy gate validation is scheduled for Phase 6.4.2" in report.html
        assert "<table>" in report.html

    def test_generate_report_accepts_health_iterator_once(
        self,
        performance_payload: dict[str, Any],
        health_payloads: list[dict[str, Any]],
    ) -> None:
        """Health iterators should populate both summary and health sections."""
        reports = _reports_module()
        health_iter = (payload for payload in health_payloads)

        report = reports.generate_backtest_report(
            performance_report=performance_payload,
            health_reports=health_iter,
        )

        executive = report.sections[0]
        health = report.sections[2]
        assert "2 checked" in executive.items[1]
        assert health.table[0]["Model"] == "midas"
        assert health.table[1]["Model"] == "lightgbm"

    def test_report_to_dict_is_json_serializable(self, performance_payload: dict[str, Any]) -> None:
        """Generated report payload should serialize cleanly to JSON."""
        reports = _reports_module()

        report = reports.generate_backtest_report(performance_report=performance_payload)
        payload = report.to_dict()

        encoded = json.dumps(payload)
        assert "Phase 6 Backtest Report" in encoded
        assert payload["sections"][1]["table"][0]["Metric"] == "Training time"

    def test_write_report_creates_html_markdown_pdf_and_json(
        self,
        tmp_path: Path,
        performance_payload: dict[str, Any],
    ) -> None:
        """Report writer should create all expected report artifacts."""
        reports = _reports_module()
        generator = reports.BacktestReportGenerator()
        report = generator.generate(performance_report=performance_payload)

        paths = generator.write(report, tmp_path, stem="sample_report")

        assert set(paths) == {"html", "markdown", "pdf", "json"}
        assert paths["html"].read_text(encoding="utf-8").startswith("<!doctype html>")
        assert paths["markdown"].read_text(encoding="utf-8").startswith("# Phase 6 Backtest Report")
        assert paths["pdf"].read_bytes().startswith(b"%PDF-1.4")
        payload = json.loads(paths["json"].read_text(encoding="utf-8"))
        assert payload["metadata"]["report_type"] == "backtest_summary"

    def test_empty_title_is_rejected(self) -> None:
        """Report title must be explicit."""
        reports = _reports_module()

        with pytest.raises(ValueError, match="Report title cannot be empty"):
            reports.generate_backtest_report(title=" ")
