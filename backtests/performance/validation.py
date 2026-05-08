"""Comprehensive performance validation for Phase 6.3.2.

This module validates measured model performance baselines against production
SLAs and identifies bottlenecks across the candidate forecasting pipeline. It is
designed to consume the Phase 6.3.1b fixture produced by
``measure_performance_baselines.py``.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence
import json

from loguru import logger

DEFAULT_BASELINE_PATH = Path("tests/fixtures/performance_baselines.json")


class PerformanceSeverity(str, Enum):
    """Severity levels for performance validation findings."""

    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


@dataclass(frozen=True)
class PerformanceSLA:
    """Production performance service-level assumptions."""

    full_pipeline_max_minutes: float = 30.0
    prediction_latency_max_ms: float = 1000.0
    memory_limit_mb: float = 4096.0
    bottleneck_warning_share: float = 0.50

    def __post_init__(self) -> None:
        """Validate SLA values."""
        if self.full_pipeline_max_minutes <= 0.0:
            raise ValueError("full_pipeline_max_minutes must be positive")
        if self.prediction_latency_max_ms <= 0.0:
            raise ValueError("prediction_latency_max_ms must be positive")
        if self.memory_limit_mb <= 0.0:
            raise ValueError("memory_limit_mb must be positive")
        if not 0.0 < self.bottleneck_warning_share <= 1.0:
            raise ValueError("bottleneck_warning_share must be in (0, 1]")


@dataclass(frozen=True)
class PerformanceFinding:
    """A single performance validation finding."""

    check_name: str
    severity: PerformanceSeverity
    message: str
    observed_value: Optional[float] = None
    threshold: Optional[float] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ComponentProfile:
    """Performance profile for one model component."""

    model_name: str
    training_time_sec: float
    prediction_time_sec: float
    memory_mb: float
    training_share: float
    prediction_share: float
    memory_share: float


@dataclass(frozen=True)
class PerformanceValidationReport:
    """Validated performance report for Phase 6.3.2."""

    passed: bool
    findings: List[PerformanceFinding]
    component_profiles: List[ComponentProfile]
    pipeline_summary: Dict[str, Any]
    slas: PerformanceSLA
    generated_at: str

    def to_dict(self) -> Dict[str, Any]:
        """Return a JSON-serializable report."""
        return {
            "passed": self.passed,
            "generated_at": self.generated_at,
            "slas": asdict(self.slas),
            "pipeline_summary": self.pipeline_summary,
            "component_profiles": [asdict(profile) for profile in self.component_profiles],
            "findings": [
                {
                    "check_name": finding.check_name,
                    "severity": finding.severity.value,
                    "message": finding.message,
                    "observed_value": finding.observed_value,
                    "threshold": finding.threshold,
                    "metadata": finding.metadata,
                }
                for finding in self.findings
            ],
        }


def load_performance_baseline(path: Path = DEFAULT_BASELINE_PATH) -> Dict[str, Any]:
    """Load a performance baseline fixture from disk."""
    with Path(path).open("r", encoding="utf-8") as file_obj:
        return json.load(file_obj)


def validate_performance_baseline(
    baseline_payload: Mapping[str, Any],
    *,
    sla: Optional[PerformanceSLA] = None,
) -> PerformanceValidationReport:
    """Validate measured performance baselines against Phase 6.3.2 requirements.

    Args:
        baseline_payload: Parsed performance baseline fixture.
        sla: Optional SLA overrides.

    Returns:
        Performance validation report with bottleneck rankings and findings.
    """
    active_sla = sla or _sla_from_payload(baseline_payload)
    real_models = baseline_payload.get("real_models")
    if not isinstance(real_models, Mapping):
        raise ValueError("baseline_payload must contain a real_models mapping")

    full_pipeline = real_models.get("full_pipeline")
    if not isinstance(full_pipeline, Mapping):
        raise ValueError("real_models must contain full_pipeline measurements")

    included_models = list(full_pipeline.get("included_models", []))
    if not included_models:
        raise ValueError("full_pipeline must list included_models")

    component_profiles = _build_component_profiles(real_models, included_models)
    findings = _validate_slas(full_pipeline, active_sla)
    findings.extend(_validate_model_composition(full_pipeline))
    findings.extend(_identify_bottlenecks(component_profiles, active_sla))

    passed = not any(finding.severity == PerformanceSeverity.CRITICAL for finding in findings)
    pipeline_summary = {
        "training_time_sec": float(full_pipeline["training_time_sec"]),
        "prediction_time_sec": float(full_pipeline["prediction_time_sec"]),
        "prediction_latency_ms": round(float(full_pipeline["prediction_time_sec"]) * 1000.0, 3),
        "memory_mb": float(full_pipeline["memory_mb"]),
        "throughput_pred_per_sec": float(full_pipeline["throughput_pred_per_sec"]),
        "included_models": included_models,
        "excluded_models": list(full_pipeline.get("excluded_models", [])),
        "dominant_training_component": component_profiles[0].model_name,
        "dominant_prediction_component": max(
            component_profiles, key=lambda profile: profile.prediction_time_sec
        ).model_name,
        "dominant_memory_component": max(
            component_profiles, key=lambda profile: profile.memory_mb
        ).model_name,
    }

    logger.info(
        "performance_baseline_validated",
        passed=passed,
        n_findings=len(findings),
        pipeline_summary=pipeline_summary,
    )
    return PerformanceValidationReport(
        passed=passed,
        findings=findings,
        component_profiles=component_profiles,
        pipeline_summary=pipeline_summary,
        slas=active_sla,
        generated_at=datetime.now(timezone.utc).isoformat(),
    )


def validate_performance_baseline_file(
    baseline_path: Path = DEFAULT_BASELINE_PATH,
    *,
    report_path: Optional[Path] = None,
) -> PerformanceValidationReport:
    """Validate a baseline fixture and optionally persist a JSON report."""
    payload = load_performance_baseline(baseline_path)
    report = validate_performance_baseline(payload)
    if report_path is not None:
        report_path = Path(report_path)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        with report_path.open("w", encoding="utf-8") as file_obj:
            json.dump(report.to_dict(), file_obj, indent=2)
            file_obj.write("\n")
        logger.info("performance_validation_report_written", path=str(report_path))
    return report


def _sla_from_payload(payload: Mapping[str, Any]) -> PerformanceSLA:
    """Build SLA configuration from fixture metadata."""
    slas = payload.get("slas", {})
    if not isinstance(slas, Mapping):
        slas = {}
    return PerformanceSLA(
        full_pipeline_max_minutes=float(slas.get("full_pipeline_max_minutes", 30.0)),
        prediction_latency_max_ms=float(slas.get("prediction_latency_max_ms", 1000.0)),
        memory_limit_mb=float(slas.get("memory_limit_mb", 4096.0)),
    )


def _build_component_profiles(
    real_models: Mapping[str, Any],
    included_models: Sequence[str],
) -> List[ComponentProfile]:
    """Build sorted component profiles for included model candidates."""
    total_training = sum(float(real_models[name]["training_time_sec"]) for name in included_models)
    total_prediction = sum(float(real_models[name]["prediction_time_sec"]) for name in included_models)
    total_memory = sum(float(real_models[name]["memory_mb"]) for name in included_models)

    profiles: List[ComponentProfile] = []
    for model_name in included_models:
        model = real_models[model_name]
        training_time = float(model["training_time_sec"])
        prediction_time = float(model["prediction_time_sec"])
        memory_mb = float(model["memory_mb"])
        profiles.append(
            ComponentProfile(
                model_name=model_name,
                training_time_sec=training_time,
                prediction_time_sec=prediction_time,
                memory_mb=memory_mb,
                training_share=_safe_share(training_time, total_training),
                prediction_share=_safe_share(prediction_time, total_prediction),
                memory_share=_safe_share(memory_mb, total_memory),
            )
        )
    return sorted(profiles, key=lambda profile: profile.training_time_sec, reverse=True)


def _validate_slas(
    full_pipeline: Mapping[str, Any],
    sla: PerformanceSLA,
) -> List[PerformanceFinding]:
    """Validate full-pipeline performance against production SLA gates."""
    findings: List[PerformanceFinding] = []
    training_time = float(full_pipeline["training_time_sec"])
    prediction_latency_ms = float(full_pipeline["prediction_time_sec"]) * 1000.0
    memory_mb = float(full_pipeline["memory_mb"])

    max_training_seconds = sla.full_pipeline_max_minutes * 60.0
    if training_time > max_training_seconds:
        findings.append(
            PerformanceFinding(
                check_name="full_pipeline_training_sla",
                severity=PerformanceSeverity.CRITICAL,
                message="Full-pipeline training time exceeds SLA",
                observed_value=training_time,
                threshold=max_training_seconds,
            )
        )
    else:
        findings.append(
            PerformanceFinding(
                check_name="full_pipeline_training_sla",
                severity=PerformanceSeverity.INFO,
                message="Full-pipeline training time is within SLA",
                observed_value=training_time,
                threshold=max_training_seconds,
            )
        )

    if prediction_latency_ms > sla.prediction_latency_max_ms:
        findings.append(
            PerformanceFinding(
                check_name="prediction_latency_sla",
                severity=PerformanceSeverity.CRITICAL,
                message="Full-pipeline prediction latency exceeds SLA",
                observed_value=prediction_latency_ms,
                threshold=sla.prediction_latency_max_ms,
            )
        )
    else:
        findings.append(
            PerformanceFinding(
                check_name="prediction_latency_sla",
                severity=PerformanceSeverity.INFO,
                message="Full-pipeline prediction latency is within SLA",
                observed_value=prediction_latency_ms,
                threshold=sla.prediction_latency_max_ms,
            )
        )

    if memory_mb > sla.memory_limit_mb:
        findings.append(
            PerformanceFinding(
                check_name="memory_sla",
                severity=PerformanceSeverity.CRITICAL,
                message="Full-pipeline memory usage exceeds SLA",
                observed_value=memory_mb,
                threshold=sla.memory_limit_mb,
            )
        )
    else:
        findings.append(
            PerformanceFinding(
                check_name="memory_sla",
                severity=PerformanceSeverity.INFO,
                message="Full-pipeline memory usage is within SLA",
                observed_value=memory_mb,
                threshold=sla.memory_limit_mb,
            )
        )
    return findings


def _validate_model_composition(full_pipeline: Mapping[str, Any]) -> List[PerformanceFinding]:
    """Confirm Phase 6 production-candidate composition is explicit."""
    included_models = set(full_pipeline.get("included_models", []))
    excluded_models = set(full_pipeline.get("excluded_models", []))
    expected_candidates = {"midas", "xgboost", "lightgbm", "revision"}
    findings: List[PerformanceFinding] = []

    if not expected_candidates.issubset(included_models):
        findings.append(
            PerformanceFinding(
                check_name="pipeline_candidate_composition",
                severity=PerformanceSeverity.CRITICAL,
                message="Full pipeline is missing expected production candidate models",
                metadata={
                    "expected": sorted(expected_candidates),
                    "included": sorted(included_models),
                },
            )
        )
    else:
        findings.append(
            PerformanceFinding(
                check_name="pipeline_candidate_composition",
                severity=PerformanceSeverity.INFO,
                message="Full pipeline includes expected production candidate models",
                metadata={"included": sorted(included_models)},
            )
        )

    if "dfm" not in excluded_models:
        findings.append(
            PerformanceFinding(
                check_name="dfm_exclusion",
                severity=PerformanceSeverity.WARNING,
                message="DFM exclusion from production candidates is not recorded",
                metadata={"excluded": sorted(excluded_models)},
            )
        )
    else:
        findings.append(
            PerformanceFinding(
                check_name="dfm_exclusion",
                severity=PerformanceSeverity.INFO,
                message="DFM exclusion is recorded for current production candidates",
                metadata={"excluded": sorted(excluded_models)},
            )
        )
    return findings


def _identify_bottlenecks(
    profiles: Sequence[ComponentProfile],
    sla: PerformanceSLA,
) -> List[PerformanceFinding]:
    """Create warning findings for components dominating one performance dimension."""
    findings: List[PerformanceFinding] = []
    dimensions = (
        ("training_bottleneck", "training_share"),
        ("prediction_bottleneck", "prediction_share"),
        ("memory_bottleneck", "memory_share"),
    )
    for check_name, attr_name in dimensions:
        dominant = max(profiles, key=lambda profile: getattr(profile, attr_name))
        share = float(getattr(dominant, attr_name))
        if share >= sla.bottleneck_warning_share:
            findings.append(
                PerformanceFinding(
                    check_name=check_name,
                    severity=PerformanceSeverity.WARNING,
                    message=f"{dominant.model_name} dominates {check_name.replace('_', ' ')}",
                    observed_value=share,
                    threshold=sla.bottleneck_warning_share,
                    metadata={"model_name": dominant.model_name},
                )
            )
        else:
            findings.append(
                PerformanceFinding(
                    check_name=check_name,
                    severity=PerformanceSeverity.INFO,
                    message=f"No single component dominates {check_name.replace('_', ' ')}",
                    observed_value=share,
                    threshold=sla.bottleneck_warning_share,
                    metadata={"model_name": dominant.model_name},
                )
            )
    return findings


def _safe_share(value: float, total: float) -> float:
    """Compute a stable share value."""
    if total <= 0.0:
        return 0.0
    return round(value / total, 6)
