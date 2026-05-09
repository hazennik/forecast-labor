"""Feature registry lineage validation for Phase 6.4.4.

The validator checks that model artifact metadata remains tied to registered
feature definitions, versions, vintages, and dependency graphs. It is designed
to work with the existing ``FeatureRegistry`` API and plain JSON payloads from
future backtest runners.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence
import json

from loguru import logger

from features.registry import FeatureRegistry


class LineageSeverity(str, Enum):
    """Severity levels for lineage validation findings."""

    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


@dataclass(frozen=True)
class LineageFinding:
    """A single feature-lineage validation finding."""

    check_name: str
    severity: LineageSeverity
    message: str
    model_name: Optional[str] = None
    feature_name: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Return a JSON-serializable finding."""
        return {
            "check_name": self.check_name,
            "severity": self.severity.value,
            "message": self.message,
            "model_name": self.model_name,
            "feature_name": self.feature_name,
            "metadata": self.metadata,
        }


@dataclass(frozen=True)
class FeatureLineageNode:
    """Resolved registry state for one model feature."""

    feature_id: str
    name: str
    version: str
    vintage_date: Optional[str]
    lineage_ids: List[str]
    lineage_names: List[str]

    def to_dict(self) -> Dict[str, Any]:
        """Return a JSON-serializable lineage node."""
        return asdict(self)


@dataclass(frozen=True)
class ModelLineageResult:
    """Lineage validation result for one model artifact."""

    model_name: str
    feature_nodes: List[FeatureLineageNode]
    findings: List[LineageFinding]
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def passed(self) -> bool:
        """Return True when no critical findings were found."""
        return not any(finding.severity == LineageSeverity.CRITICAL for finding in self.findings)

    def to_dict(self) -> Dict[str, Any]:
        """Return a JSON-serializable result."""
        return {
            "model_name": self.model_name,
            "passed": self.passed,
            "metadata": self.metadata,
            "feature_nodes": [node.to_dict() for node in self.feature_nodes],
            "findings": [finding.to_dict() for finding in self.findings],
        }


@dataclass(frozen=True)
class RollbackImpact:
    """Impact analysis for rolling a feature back to an earlier version."""

    feature_name: str
    baseline_metric: float
    rollback_metric: float
    metric_name: str = "rmse"
    max_allowed_degradation: float = 0.0

    def __post_init__(self) -> None:
        """Validate rollback impact values."""
        if not self.feature_name.strip():
            raise ValueError("feature_name cannot be empty")
        if self.max_allowed_degradation < 0.0:
            raise ValueError("max_allowed_degradation must be non-negative")

    @property
    def degradation(self) -> float:
        """Return rollback degradation where positive is worse."""
        return self.rollback_metric - self.baseline_metric

    @property
    def passed(self) -> bool:
        """Return whether rollback degradation stays within tolerance."""
        return self.degradation <= self.max_allowed_degradation

    def to_dict(self) -> Dict[str, Any]:
        """Return a JSON-serializable impact payload."""
        return {
            "feature_name": self.feature_name,
            "metric_name": self.metric_name,
            "baseline_metric": self.baseline_metric,
            "rollback_metric": self.rollback_metric,
            "degradation": self.degradation,
            "max_allowed_degradation": self.max_allowed_degradation,
            "passed": self.passed,
        }


@dataclass(frozen=True)
class LineageValidationReport:
    """Phase 6.4.4 lineage validation report."""

    passed: bool
    model_results: List[ModelLineageResult]
    rollback_impacts: List[RollbackImpact]
    findings: List[LineageFinding]
    generated_at: str
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Return a JSON-serializable report."""
        return {
            "passed": self.passed,
            "generated_at": self.generated_at,
            "metadata": self.metadata,
            "model_results": [result.to_dict() for result in self.model_results],
            "rollback_impacts": [impact.to_dict() for impact in self.rollback_impacts],
            "findings": [finding.to_dict() for finding in self.findings],
        }


def validate_feature_lineage(
    *,
    registry: FeatureRegistry,
    model_artifacts: Mapping[str, Mapping[str, Any]],
    rollback_impacts: Optional[Iterable[RollbackImpact | Mapping[str, Any]]] = None,
    metadata: Optional[Mapping[str, Any]] = None,
) -> LineageValidationReport:
    """Validate feature lineage across model artifacts.

    Args:
        registry: Feature registry containing production features.
        model_artifacts: Mapping from model name to artifact metadata payloads.
        rollback_impacts: Optional rollback impact records.
        metadata: Optional report metadata.

    Returns:
        LineageValidationReport with model and portfolio findings.
    """
    if not model_artifacts:
        raise ValueError("model_artifacts cannot be empty")

    model_results = [
        _validate_model_artifact(registry, model_name, artifact)
        for model_name, artifact in model_artifacts.items()
    ]
    impacts = [_coerce_rollback_impact(impact) for impact in (rollback_impacts or [])]
    findings = _portfolio_findings(model_results, impacts)
    all_findings = findings + [finding for result in model_results for finding in result.findings]
    passed = not any(finding.severity == LineageSeverity.CRITICAL for finding in all_findings)

    report = LineageValidationReport(
        passed=passed,
        model_results=model_results,
        rollback_impacts=impacts,
        findings=all_findings,
        generated_at=datetime.now(timezone.utc).isoformat(),
        metadata=dict(metadata or {}),
    )
    logger.info(
        "feature_lineage_validated",
        passed=report.passed,
        n_models=len(model_results),
        n_findings=len(all_findings),
    )
    return report


def validate_feature_lineage_file(
    input_path: Path,
    *,
    report_path: Optional[Path] = None,
) -> LineageValidationReport:
    """Validate feature lineage from a JSON payload and optionally write a report."""
    payload = _load_json_mapping(input_path)
    registry = FeatureRegistry(backend="memory")
    for feature in payload.get("registry_features", []):
        registry.register(feature)

    report = validate_feature_lineage(
        registry=registry,
        model_artifacts=payload["model_artifacts"],
        rollback_impacts=payload.get("rollback_impacts"),
        metadata=payload.get("metadata"),
    )
    if report_path is not None:
        report_path = Path(report_path)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report.to_dict(), indent=2) + "\n", encoding="utf-8")
        logger.info("feature_lineage_report_written", path=str(report_path))
    return report


def _validate_model_artifact(
    registry: FeatureRegistry,
    model_name: str,
    artifact: Mapping[str, Any],
) -> ModelLineageResult:
    """Validate one model artifact against registry metadata."""
    metadata = _artifact_metadata(artifact)
    feature_names = _feature_names(metadata)
    expected_versions = dict(metadata.get("feature_versions") or {})
    artifact_vintage = metadata.get("vintage_date")

    findings: List[LineageFinding] = []
    nodes: List[FeatureLineageNode] = []
    if not feature_names:
        findings.append(
            LineageFinding(
                check_name="artifact_features_present",
                severity=LineageSeverity.CRITICAL,
                message="Model artifact does not list training features",
                model_name=model_name,
            )
        )
        return ModelLineageResult(model_name=model_name, feature_nodes=nodes, findings=findings)

    for feature_name in feature_names:
        matches = registry.search(name=feature_name)
        if not matches:
            findings.append(
                LineageFinding(
                    check_name="feature_registered",
                    severity=LineageSeverity.CRITICAL,
                    message="Model feature is not registered",
                    model_name=model_name,
                    feature_name=feature_name,
                )
            )
            continue

        feature = _select_feature_version(matches, expected_versions.get(feature_name))
        feature_id = _feature_id(feature)
        feature_version = _feature_version(feature)
        lineage_ids = _safe_lineage(registry, feature_id, findings, model_name, feature_name)
        lineage_names = _lineage_names(registry, lineage_ids, findings, model_name, feature_name)
        nodes.append(
            FeatureLineageNode(
                feature_id=feature_id,
                name=str(feature.get("name", feature_name)),
                version=feature_version,
                vintage_date=_optional_str(feature.get("vintage_date")),
                lineage_ids=lineage_ids,
                lineage_names=lineage_names,
            )
        )

        expected_version = expected_versions.get(feature_name)
        if expected_version and feature_version != str(expected_version):
            findings.append(
                LineageFinding(
                    check_name="feature_version_match",
                    severity=LineageSeverity.CRITICAL,
                    message="Model artifact references a feature version not present in registry",
                    model_name=model_name,
                    feature_name=feature_name,
                    metadata={"expected": expected_version, "observed": feature_version},
                )
            )

        if artifact_vintage and feature.get("vintage_date") != artifact_vintage:
            findings.append(
                LineageFinding(
                    check_name="feature_vintage_match",
                    severity=LineageSeverity.WARNING,
                    message="Feature vintage differs from model artifact vintage",
                    model_name=model_name,
                    feature_name=feature_name,
                    metadata={
                        "artifact_vintage": artifact_vintage,
                        "feature_vintage": feature.get("vintage_date"),
                    },
                )
            )

    findings.append(
        LineageFinding(
            check_name="artifact_lineage_coverage",
            severity=LineageSeverity.INFO
            if len(nodes) == len(feature_names)
            else LineageSeverity.CRITICAL,
            message="Model artifact features resolved against feature registry",
            model_name=model_name,
            metadata={"resolved": len(nodes), "expected": len(feature_names)},
        )
    )
    return ModelLineageResult(
        model_name=model_name,
        feature_nodes=nodes,
        findings=findings,
        metadata={"feature_count": len(feature_names), "vintage_date": artifact_vintage},
    )


def _portfolio_findings(
    model_results: Sequence[ModelLineageResult],
    rollback_impacts: Sequence[RollbackImpact],
) -> List[LineageFinding]:
    """Build portfolio-level lineage findings."""
    findings = [
        LineageFinding(
            check_name="lineage_models_present",
            severity=LineageSeverity.INFO if model_results else LineageSeverity.CRITICAL,
            message="Model lineage payloads are present",
            metadata={"model_count": len(model_results)},
        )
    ]
    for impact in rollback_impacts:
        findings.append(
            LineageFinding(
                check_name="rollback_impact",
                severity=LineageSeverity.INFO if impact.passed else LineageSeverity.WARNING,
                message="Feature rollback impact analysis recorded",
                feature_name=impact.feature_name,
                metadata=impact.to_dict(),
            )
        )
    if not rollback_impacts:
        findings.append(
            LineageFinding(
                check_name="rollback_impact",
                severity=LineageSeverity.WARNING,
                message="No feature rollback impact analysis was provided",
            )
        )
    return findings


def _artifact_metadata(artifact: Mapping[str, Any]) -> Mapping[str, Any]:
    """Return normalized artifact metadata."""
    metadata = artifact.get("metadata", artifact)
    if not isinstance(metadata, Mapping):
        raise ValueError("artifact metadata must be a mapping")
    return metadata


def _feature_names(metadata: Mapping[str, Any]) -> List[str]:
    """Return feature names from current or legacy metadata fields."""
    values = metadata.get("features") or metadata.get("feature_names") or []
    return [str(value) for value in values]


def _select_feature_version(
    matches: Sequence[Mapping[str, Any]],
    expected_version: Optional[str],
) -> Mapping[str, Any]:
    """Select the registry feature version expected by the artifact."""
    if expected_version is not None:
        for feature in matches:
            if _feature_version(feature) == str(expected_version):
                return feature
    return sorted(matches, key=_feature_version)[-1]


def _feature_id(feature: Mapping[str, Any]) -> str:
    """Return feature ID from registry search result."""
    feature_id = feature.get("feature_id")
    if feature_id is None:
        raise ValueError(f"registry feature {feature.get('name')} is missing feature_id")
    return str(feature_id)


def _feature_version(feature: Mapping[str, Any]) -> str:
    """Return normalized feature version."""
    if feature.get("version") is not None:
        return str(feature["version"])
    if feature.get("current_version") is not None:
        return f"{feature['current_version']}.0.0"
    return "1.0.0"


def _safe_lineage(
    registry: FeatureRegistry,
    feature_id: str,
    findings: List[LineageFinding],
    model_name: str,
    feature_name: str,
) -> List[str]:
    """Return lineage IDs while recording lookup failures."""
    try:
        return [str(item) for item in registry.get_lineage(feature_id)]
    except Exception as exc:
        findings.append(
            LineageFinding(
                check_name="feature_lineage_query",
                severity=LineageSeverity.CRITICAL,
                message="Feature lineage query failed",
                model_name=model_name,
                feature_name=feature_name,
                metadata={"feature_id": feature_id, "error": str(exc)},
            )
        )
        return []


def _lineage_names(
    registry: FeatureRegistry,
    lineage_ids: Iterable[str],
    findings: List[LineageFinding],
    model_name: str,
    feature_name: str,
) -> List[str]:
    """Resolve lineage IDs to feature names and record missing nodes."""
    names: List[str] = []
    for lineage_id in lineage_ids:
        try:
            lineage_feature = registry.get(lineage_id)
            names.append(str(lineage_feature.get("name", lineage_id)))
        except Exception as exc:
            findings.append(
                LineageFinding(
                    check_name="lineage_node_resolves",
                    severity=LineageSeverity.CRITICAL,
                    message="Lineage dependency is not retrievable from registry",
                    model_name=model_name,
                    feature_name=feature_name,
                    metadata={"lineage_id": lineage_id, "error": str(exc)},
                )
            )
    return names


def _coerce_rollback_impact(impact: RollbackImpact | Mapping[str, Any]) -> RollbackImpact:
    """Coerce a rollback impact payload."""
    if isinstance(impact, RollbackImpact):
        return impact
    return RollbackImpact(
        feature_name=str(impact["feature_name"]),
        baseline_metric=float(impact["baseline_metric"]),
        rollback_metric=float(impact["rollback_metric"]),
        metric_name=str(impact.get("metric_name", "rmse")),
        max_allowed_degradation=float(impact.get("max_allowed_degradation", 0.0)),
    )


def _optional_str(value: Any) -> Optional[str]:
    """Return an optional string value."""
    if value is None:
        return None
    return str(value)


def _load_json_mapping(path: Path) -> Dict[str, Any]:
    """Load a JSON object from disk."""
    with Path(path).open("r", encoding="utf-8") as file_obj:
        payload = json.load(file_obj)
    if not isinstance(payload, dict):
        raise ValueError("lineage payload must be a JSON object")
    return payload
