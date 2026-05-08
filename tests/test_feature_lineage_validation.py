"""Tests for Phase 6.4.4 feature registry lineage validation."""

from __future__ import annotations

from pathlib import Path
from typing import Any
import importlib
import json
import sys

import pytest

from features.registry import FeatureRegistry


def _lineage_module() -> Any:
    """Import lineage utilities after test collection."""
    project_root = Path(__file__).resolve().parents[1]
    if str(project_root) in sys.path:
        sys.path.remove(str(project_root))
    sys.path.insert(0, str(project_root))
    sys.modules.pop("backtests", None)
    return importlib.import_module("backtests.lineage")


def _registry_and_payload() -> tuple[FeatureRegistry, dict[str, Any]]:
    """Create a registry with production-style feature lineage."""
    registry = FeatureRegistry(backend="memory")
    ces_id = registry.register(
        {
            "name": "ces_nfp_lag_1",
            "source": "ces",
            "frequency": "monthly",
            "version": "1.0.0",
            "vintage_date": "2025-11-29",
        }
    )
    claims_id = registry.register(
        {
            "name": "claims_initial_4wk",
            "source": "claims",
            "frequency": "weekly",
            "version": "1.0.0",
            "vintage_date": "2025-11-29",
        }
    )
    registry.register(
        {
            "name": "midas_bridge_signal",
            "source": "feature_pipeline",
            "frequency": "monthly",
            "transform": "midas_bridge",
            "version": "2.0.0",
            "vintage_date": "2025-11-29",
            "depends_on": [ces_id, claims_id],
        }
    )
    registry.register(
        {
            "name": "gbm_feature_stack",
            "source": "feature_pipeline",
            "frequency": "monthly",
            "transform": "stack",
            "version": "1.1.0",
            "vintage_date": "2025-11-29",
            "depends_on": [claims_id],
        }
    )

    artifacts = {
        "midas": {
            "metadata": {
                "features": ["midas_bridge_signal", "claims_initial_4wk"],
                "feature_versions": {
                    "midas_bridge_signal": "2.0.0",
                    "claims_initial_4wk": "1.0.0",
                },
                "vintage_date": "2025-11-29",
            }
        },
        "lightgbm": {
            "metadata": {
                "feature_names": ["gbm_feature_stack", "claims_initial_4wk"],
                "feature_versions": {
                    "gbm_feature_stack": "1.1.0",
                    "claims_initial_4wk": "1.0.0",
                },
                "vintage_date": "2025-11-29",
            }
        },
    }
    return registry, artifacts


def _file_payload() -> dict[str, Any]:
    """Build a JSON payload for file-level lineage validation."""
    return {
        "registry_features": [
            {
                "name": "ces_nfp_lag_1",
                "source": "ces",
                "frequency": "monthly",
                "version": "1.0.0",
                "vintage_date": "2025-11-29",
            },
            {
                "name": "claims_initial_4wk",
                "source": "claims",
                "frequency": "weekly",
                "version": "1.0.0",
                "vintage_date": "2025-11-29",
            },
            {
                "name": "midas_bridge_signal",
                "source": "feature_pipeline",
                "frequency": "monthly",
                "version": "2.0.0",
                "vintage_date": "2025-11-29",
            },
        ],
        "model_artifacts": {
            "midas": {
                "metadata": {
                    "features": ["midas_bridge_signal", "claims_initial_4wk"],
                    "feature_versions": {
                        "midas_bridge_signal": "2.0.0",
                        "claims_initial_4wk": "1.0.0",
                    },
                    "vintage_date": "2025-11-29",
                }
            }
        },
        "rollback_impacts": [
            {
                "feature_name": "midas_bridge_signal",
                "baseline_metric": 42_000.0,
                "rollback_metric": 42_500.0,
                "metric_name": "rmse",
                "max_allowed_degradation": 1_000.0,
            }
        ],
        "metadata": {"validation": "phase_6_4_4"},
    }


class TestFeatureLineageValidation:
    """Validate lineage checks for model artifacts and registry features."""

    def test_valid_lineage_payload_passes(self) -> None:
        """Registered features, versions, vintages, and lineage should pass."""
        lineage = _lineage_module()
        registry, artifacts = _registry_and_payload()

        report = lineage.validate_feature_lineage(
            registry=registry,
            model_artifacts=artifacts,
            rollback_impacts=[
                lineage.RollbackImpact(
                    feature_name="midas_bridge_signal",
                    baseline_metric=40_000.0,
                    rollback_metric=40_250.0,
                    max_allowed_degradation=500.0,
                )
            ],
            metadata={"vintage_date": "2025-11-29"},
        )

        assert report.passed is True
        assert len(report.model_results) == 2
        midas = next(result for result in report.model_results if result.model_name == "midas")
        bridge = next(node for node in midas.feature_nodes if node.name == "midas_bridge_signal")
        assert bridge.version == "2.0.0"
        assert set(bridge.lineage_names) == {"ces_nfp_lag_1", "claims_initial_4wk"}

    def test_missing_artifact_feature_is_critical(self) -> None:
        """Artifact features must resolve against the feature registry."""
        lineage = _lineage_module()
        registry, artifacts = _registry_and_payload()
        artifacts["midas"]["metadata"]["features"].append("missing_feature")

        report = lineage.validate_feature_lineage(registry=registry, model_artifacts=artifacts)

        assert report.passed is False
        assert any(
            finding.check_name == "feature_registered"
            and finding.severity == lineage.LineageSeverity.CRITICAL
            for finding in report.findings
        )

    def test_feature_version_mismatch_is_critical(self) -> None:
        """Artifact feature_versions must match registered feature versions."""
        lineage = _lineage_module()
        registry, artifacts = _registry_and_payload()
        artifacts["midas"]["metadata"]["feature_versions"]["midas_bridge_signal"] = "9.9.9"

        report = lineage.validate_feature_lineage(registry=registry, model_artifacts=artifacts)

        assert report.passed is False
        assert any(finding.check_name == "feature_version_match" for finding in report.findings)

    def test_vintage_mismatch_is_warning(self) -> None:
        """Vintage mismatches should be visible without blocking the report."""
        lineage = _lineage_module()
        registry, artifacts = _registry_and_payload()
        artifacts["lightgbm"]["metadata"]["vintage_date"] = "2025-12-31"

        report = lineage.validate_feature_lineage(registry=registry, model_artifacts=artifacts)

        assert report.passed is True
        assert any(
            finding.check_name == "feature_vintage_match"
            and finding.severity == lineage.LineageSeverity.WARNING
            for finding in report.findings
        )

    def test_empty_artifact_features_are_critical(self) -> None:
        """Model artifacts must list their training features."""
        lineage = _lineage_module()
        registry, artifacts = _registry_and_payload()
        artifacts["midas"]["metadata"]["features"] = []

        report = lineage.validate_feature_lineage(registry=registry, model_artifacts=artifacts)

        assert report.passed is False
        assert any(finding.check_name == "artifact_features_present" for finding in report.findings)

    def test_rollback_impact_warning_when_degradation_exceeds_tolerance(self) -> None:
        """Rollback impact analysis should flag material degradation."""
        lineage = _lineage_module()
        registry, artifacts = _registry_and_payload()

        report = lineage.validate_feature_lineage(
            registry=registry,
            model_artifacts=artifacts,
            rollback_impacts=[
                {
                    "feature_name": "claims_initial_4wk",
                    "baseline_metric": 40_000.0,
                    "rollback_metric": 45_000.0,
                    "max_allowed_degradation": 500.0,
                }
            ],
        )

        assert report.passed is True
        impact_finding = next(
            finding
            for finding in report.findings
            if finding.check_name == "rollback_impact"
            and finding.feature_name == "claims_initial_4wk"
        )
        assert impact_finding.severity == lineage.LineageSeverity.WARNING
        assert impact_finding.metadata["degradation"] == 5_000.0

    def test_file_validation_writes_report(self, tmp_path: Path) -> None:
        """File-level validation should build a registry and persist JSON."""
        lineage = _lineage_module()
        input_path = tmp_path / "lineage_input.json"
        report_path = tmp_path / "lineage_report.json"
        input_path.write_text(json.dumps(_file_payload()), encoding="utf-8")

        report = lineage.validate_feature_lineage_file(input_path, report_path=report_path)

        assert report.passed is True
        written = json.loads(report_path.read_text(encoding="utf-8"))
        assert written["metadata"]["validation"] == "phase_6_4_4"
        assert written["model_results"][0]["feature_nodes"][0]["name"] == "midas_bridge_signal"

    def test_invalid_rollback_impact_fails_early(self) -> None:
        """Rollback impact values should be validated."""
        lineage = _lineage_module()

        with pytest.raises(ValueError, match="max_allowed_degradation"):
            lineage.RollbackImpact(
                feature_name="claims_initial_4wk",
                baseline_metric=1.0,
                rollback_metric=2.0,
                max_allowed_degradation=-1.0,
            )
