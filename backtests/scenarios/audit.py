"""What-if scenario testing for Phase 6.4.3 backtest audits.

The scenario engine applies deterministic shocks to feature payloads and uses
explicit feature sensitivities to estimate forecast impact. It is intentionally
small and payload-driven so future vintage backtest runners can reuse it without
coupling to one model implementation.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence
import json

import numpy as np
from loguru import logger


class ShockOperation(str, Enum):
    """Supported scenario shock operations."""

    ADD = "add"
    MULTIPLY = "multiply"
    SET = "set"


class ScenarioSeverity(str, Enum):
    """Severity levels for scenario audit findings."""

    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


@dataclass(frozen=True)
class ScenarioShock:
    """A deterministic feature shock in a scenario."""

    feature_name: str
    operation: ShockOperation
    value: float

    def __post_init__(self) -> None:
        """Validate shock fields."""
        if not self.feature_name.strip():
            raise ValueError("feature_name cannot be empty")
        if not np.isfinite(self.value):
            raise ValueError("shock value must be finite")


@dataclass(frozen=True)
class ScenarioDefinition:
    """A named stress scenario for audit reporting."""

    name: str
    category: str
    shocks: List[ScenarioShock]
    expected_direction: str
    description: str = ""

    def __post_init__(self) -> None:
        """Validate scenario definition."""
        if not self.name.strip():
            raise ValueError("scenario name cannot be empty")
        if not self.category.strip():
            raise ValueError("scenario category cannot be empty")
        if not self.shocks:
            raise ValueError("scenario shocks cannot be empty")
        if self.expected_direction not in {"increase", "decrease", "neutral"}:
            raise ValueError("expected_direction must be increase, decrease, or neutral")


@dataclass(frozen=True)
class ScenarioThresholds:
    """Scenario audit thresholds."""

    max_abs_forecast: float = 2_000_000.0
    min_material_impact: float = 1_000.0
    neutral_tolerance: float = 500.0

    def __post_init__(self) -> None:
        """Validate threshold values."""
        if self.max_abs_forecast <= 0.0:
            raise ValueError("max_abs_forecast must be positive")
        if self.min_material_impact < 0.0:
            raise ValueError("min_material_impact must be non-negative")
        if self.neutral_tolerance < 0.0:
            raise ValueError("neutral_tolerance must be non-negative")


@dataclass(frozen=True)
class ScenarioFinding:
    """A single scenario audit finding."""

    check_name: str
    severity: ScenarioSeverity
    message: str
    observed_value: Optional[float] = None
    threshold: Optional[float] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Return a JSON-serializable finding."""
        return {
            "check_name": self.check_name,
            "severity": self.severity.value,
            "message": self.message,
            "observed_value": self.observed_value,
            "threshold": self.threshold,
            "metadata": self.metadata,
        }


@dataclass(frozen=True)
class ScenarioResult:
    """Result of applying one scenario."""

    scenario_name: str
    category: str
    baseline_forecast: float
    shocked_forecast: float
    forecast_delta: float
    shocked_features: Dict[str, float]
    findings: List[ScenarioFinding]

    @property
    def passed(self) -> bool:
        """Return True when no critical scenario findings are present."""
        return not any(finding.severity == ScenarioSeverity.CRITICAL for finding in self.findings)

    def to_dict(self) -> Dict[str, Any]:
        """Return a JSON-serializable result."""
        return {
            "scenario_name": self.scenario_name,
            "category": self.category,
            "baseline_forecast": self.baseline_forecast,
            "shocked_forecast": self.shocked_forecast,
            "forecast_delta": self.forecast_delta,
            "shocked_features": self.shocked_features,
            "passed": self.passed,
            "findings": [finding.to_dict() for finding in self.findings],
        }


@dataclass(frozen=True)
class ScenarioReport:
    """Scenario testing report for Phase 6.4.3."""

    passed: bool
    results: List[ScenarioResult]
    thresholds: ScenarioThresholds
    generated_at: str
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Return a JSON-serializable report."""
        return {
            "passed": self.passed,
            "generated_at": self.generated_at,
            "metadata": self.metadata,
            "thresholds": asdict(self.thresholds),
            "results": [result.to_dict() for result in self.results],
        }


DEFAULT_SCENARIOS: tuple[ScenarioDefinition, ...] = (
    ScenarioDefinition(
        name="major_hurricane_labor_disruption",
        category="storm",
        description="Large weather disruption raising storm severity and reducing hours worked.",
        expected_direction="decrease",
        shocks=[
            ScenarioShock("storm_severity_index", ShockOperation.ADD, 2.5),
            ScenarioShock("weekly_hours_growth", ShockOperation.ADD, -0.8),
        ],
    ),
    ScenarioDefinition(
        name="large_transport_strike",
        category="strike",
        description="Strike shock increasing workers affected and reducing payroll diffusion.",
        expected_direction="decrease",
        shocks=[
            ScenarioShock("strike_workers", ShockOperation.ADD, 50_000.0),
            ScenarioShock("payroll_diffusion_index", ShockOperation.ADD, -3.0),
        ],
    ),
    ScenarioDefinition(
        name="policy_uncertainty_jump",
        category="policy",
        description="Policy uncertainty jump paired with weaker withholding growth.",
        expected_direction="decrease",
        shocks=[
            ScenarioShock("policy_uncertainty_index", ShockOperation.MULTIPLY, 1.5),
            ScenarioShock("withholding_growth", ShockOperation.ADD, -1.0),
        ],
    ),
)


def evaluate_scenarios(
    *,
    baseline_features: Mapping[str, float],
    baseline_forecast: float,
    feature_sensitivities: Mapping[str, float],
    scenarios: Optional[Iterable[ScenarioDefinition | Mapping[str, Any]]] = None,
    thresholds: Optional[ScenarioThresholds] = None,
    metadata: Optional[Mapping[str, Any]] = None,
) -> ScenarioReport:
    """Evaluate what-if scenarios against a baseline forecast.

    Args:
        baseline_features: Baseline feature values available at forecast time.
        baseline_forecast: Baseline forecast in jobs.
        feature_sensitivities: Linear forecast sensitivities per feature.
        scenarios: Optional scenario definitions; defaults to storm, strike, and policy shocks.
        thresholds: Optional scenario audit threshold overrides.
        metadata: Optional report metadata.

    Returns:
        ScenarioReport with one result per scenario.
    """
    clean_features = _validate_numeric_mapping(baseline_features, "baseline_features")
    clean_sensitivities = _validate_numeric_mapping(feature_sensitivities, "feature_sensitivities")
    if not np.isfinite(baseline_forecast):
        raise ValueError("baseline_forecast must be finite")

    active_thresholds = thresholds or ScenarioThresholds()
    definitions = [_coerce_scenario(definition) for definition in (scenarios or DEFAULT_SCENARIOS)]
    if not definitions:
        raise ValueError("at least one scenario is required")

    results = [
        _evaluate_one_scenario(
            scenario=definition,
            baseline_features=clean_features,
            baseline_forecast=float(baseline_forecast),
            feature_sensitivities=clean_sensitivities,
            thresholds=active_thresholds,
        )
        for definition in definitions
    ]
    report = ScenarioReport(
        passed=all(result.passed for result in results),
        results=results,
        thresholds=active_thresholds,
        generated_at=datetime.now(timezone.utc).isoformat(),
        metadata=dict(metadata or {}),
    )
    logger.info(
        "scenario_report_generated",
        passed=report.passed,
        n_scenarios=len(results),
        metadata=report.metadata,
    )
    return report


def evaluate_scenario_file(
    input_path: Path,
    *,
    report_path: Optional[Path] = None,
) -> ScenarioReport:
    """Evaluate a JSON scenario payload and optionally write a JSON report."""
    payload = _load_json_mapping(input_path)
    thresholds_payload = payload.get("thresholds", {})
    thresholds = (
        ScenarioThresholds(**thresholds_payload)
        if isinstance(thresholds_payload, Mapping) and thresholds_payload
        else None
    )
    report = evaluate_scenarios(
        baseline_features=payload["baseline_features"],
        baseline_forecast=float(payload["baseline_forecast"]),
        feature_sensitivities=payload["feature_sensitivities"],
        scenarios=payload.get("scenarios"),
        thresholds=thresholds,
        metadata=payload.get("metadata"),
    )
    if report_path is not None:
        report_path = Path(report_path)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report.to_dict(), indent=2) + "\n", encoding="utf-8")
        logger.info("scenario_report_written", path=str(report_path))
    return report


def _evaluate_one_scenario(
    *,
    scenario: ScenarioDefinition,
    baseline_features: Mapping[str, float],
    baseline_forecast: float,
    feature_sensitivities: Mapping[str, float],
    thresholds: ScenarioThresholds,
) -> ScenarioResult:
    """Evaluate one scenario definition."""
    shocked_features = dict(baseline_features)
    for shock in scenario.shocks:
        if shock.feature_name not in shocked_features:
            raise ValueError(f"scenario {scenario.name} references missing feature {shock.feature_name}")
        shocked_features[shock.feature_name] = _apply_shock(shocked_features[shock.feature_name], shock)

    forecast_delta = 0.0
    missing_sensitivities = []
    for feature_name, shocked_value in shocked_features.items():
        baseline_value = baseline_features[feature_name]
        if shocked_value == baseline_value:
            continue
        if feature_name not in feature_sensitivities:
            missing_sensitivities.append(feature_name)
            continue
        forecast_delta += (shocked_value - baseline_value) * feature_sensitivities[feature_name]

    shocked_forecast = baseline_forecast + forecast_delta
    findings = _scenario_findings(
        scenario=scenario,
        shocked_forecast=shocked_forecast,
        forecast_delta=forecast_delta,
        thresholds=thresholds,
        missing_sensitivities=missing_sensitivities,
    )
    return ScenarioResult(
        scenario_name=scenario.name,
        category=scenario.category,
        baseline_forecast=round(baseline_forecast, 6),
        shocked_forecast=round(float(shocked_forecast), 6),
        forecast_delta=round(float(forecast_delta), 6),
        shocked_features={key: round(float(value), 6) for key, value in shocked_features.items()},
        findings=findings,
    )


def _scenario_findings(
    *,
    scenario: ScenarioDefinition,
    shocked_forecast: float,
    forecast_delta: float,
    thresholds: ScenarioThresholds,
    missing_sensitivities: Sequence[str],
) -> List[ScenarioFinding]:
    """Build audit findings for one scenario."""
    findings: List[ScenarioFinding] = []
    if missing_sensitivities:
        findings.append(
            ScenarioFinding(
                check_name="scenario_sensitivity_coverage",
                severity=ScenarioSeverity.CRITICAL,
                message="Scenario shock features are missing forecast sensitivities",
                metadata={"missing_features": sorted(missing_sensitivities)},
            )
        )

    if not np.isfinite(shocked_forecast):
        findings.append(
            ScenarioFinding(
                check_name="scenario_forecast_finite",
                severity=ScenarioSeverity.CRITICAL,
                message="Scenario forecast is not finite",
            )
        )
    elif abs(shocked_forecast) > thresholds.max_abs_forecast:
        findings.append(
            ScenarioFinding(
                check_name="scenario_forecast_magnitude",
                severity=ScenarioSeverity.CRITICAL,
                message="Scenario forecast exceeds hard magnitude gate",
                observed_value=abs(float(shocked_forecast)),
                threshold=thresholds.max_abs_forecast,
            )
        )
    else:
        findings.append(
            ScenarioFinding(
                check_name="scenario_forecast_magnitude",
                severity=ScenarioSeverity.INFO,
                message="Scenario forecast remains within hard magnitude gate",
                observed_value=abs(float(shocked_forecast)),
                threshold=thresholds.max_abs_forecast,
            )
        )

    direction_passed = _direction_matches(forecast_delta, scenario.expected_direction, thresholds)
    findings.append(
        ScenarioFinding(
            check_name="scenario_direction",
            severity=ScenarioSeverity.INFO if direction_passed else ScenarioSeverity.CRITICAL,
            message=f"Scenario impact direction expected to {scenario.expected_direction}",
            observed_value=round(float(forecast_delta), 6),
            metadata={"expected_direction": scenario.expected_direction},
        )
    )

    if (
        scenario.expected_direction != "neutral"
        and abs(forecast_delta) < thresholds.min_material_impact
    ):
        findings.append(
            ScenarioFinding(
                check_name="scenario_materiality",
                severity=ScenarioSeverity.WARNING,
                message="Scenario impact is directionally correct but below materiality threshold",
                observed_value=abs(float(forecast_delta)),
                threshold=thresholds.min_material_impact,
            )
        )
    return findings


def _direction_matches(
    forecast_delta: float,
    expected_direction: str,
    thresholds: ScenarioThresholds,
) -> bool:
    """Check whether the forecast delta matches the expected scenario direction."""
    if expected_direction == "increase":
        return forecast_delta > 0.0
    if expected_direction == "decrease":
        return forecast_delta < 0.0
    return abs(forecast_delta) <= thresholds.neutral_tolerance


def _apply_shock(value: float, shock: ScenarioShock) -> float:
    """Apply one shock to a baseline value."""
    if shock.operation == ShockOperation.ADD:
        return value + shock.value
    if shock.operation == ShockOperation.MULTIPLY:
        return value * shock.value
    if shock.operation == ShockOperation.SET:
        return shock.value
    raise ValueError(f"Unsupported shock operation: {shock.operation}")


def _coerce_scenario(definition: ScenarioDefinition | Mapping[str, Any]) -> ScenarioDefinition:
    """Coerce a mapping payload into a scenario definition."""
    if isinstance(definition, ScenarioDefinition):
        return definition
    shocks = [
        ScenarioShock(
            feature_name=str(shock["feature_name"]),
            operation=ShockOperation(str(shock["operation"])),
            value=float(shock["value"]),
        )
        for shock in definition["shocks"]
    ]
    return ScenarioDefinition(
        name=str(definition["name"]),
        category=str(definition["category"]),
        shocks=shocks,
        expected_direction=str(definition["expected_direction"]),
        description=str(definition.get("description", "")),
    )


def _validate_numeric_mapping(payload: Mapping[str, Any], name: str) -> Dict[str, float]:
    """Validate a mapping of numeric values."""
    if not payload:
        raise ValueError(f"{name} cannot be empty")
    clean: Dict[str, float] = {}
    for key, value in payload.items():
        numeric_value = float(value)
        if not np.isfinite(numeric_value):
            raise ValueError(f"{name}.{key} must be finite")
        clean[str(key)] = numeric_value
    return clean


def _load_json_mapping(path: Path) -> Dict[str, Any]:
    """Load a JSON object from disk."""
    with Path(path).open("r", encoding="utf-8") as file_obj:
        payload = json.load(file_obj)
    if not isinstance(payload, dict):
        raise ValueError("scenario payload must be a JSON object")
    return payload
