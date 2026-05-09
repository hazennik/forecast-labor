"""Model selection and accuracy gate validation for Phase 6.4.2.

This module compares candidate forecast paths against the production deployment
gates used by Phase 6 reporting. It intentionally accepts plain mappings so it
can consume vintage backtest outputs, synthetic fixtures, or future orchestrator
payloads without binding to one runner implementation.
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

from models_src.utils.metrics import (
    expected_calibration_error,
    prediction_interval_coverage,
    rmse,
    smape,
    turning_point_accuracy,
)


class AccuracyGateSeverity(str, Enum):
    """Severity levels for model-selection findings."""

    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


@dataclass(frozen=True)
class AccuracyGateThresholds:
    """Production accuracy thresholds for NFP deployment gates."""

    max_smape: float = 20.0
    max_rmse: float = 50_000.0
    min_coverage_90: float = 85.0
    max_coverage_90: float = 95.0
    max_abs_forecast: float = 2_000_000.0
    max_reconciliation_error: float = 100.0
    max_probability_sum_error: float = 0.001
    max_revision_mae: float = 30_000.0
    min_revision_direction_accuracy: float = 50.0
    min_turning_point_precision: float = 55.0
    max_state_mae: float = 12_000.0
    min_states_passing: int = 3
    max_probability_change: float = 0.15
    max_ece: float = 0.05

    def __post_init__(self) -> None:
        """Validate threshold ranges."""
        if self.max_smape <= 0.0:
            raise ValueError("max_smape must be positive")
        if self.max_rmse <= 0.0:
            raise ValueError("max_rmse must be positive")
        if not 0.0 <= self.min_coverage_90 <= self.max_coverage_90 <= 100.0:
            raise ValueError("coverage thresholds must satisfy 0 <= min <= max <= 100")
        if self.max_abs_forecast <= 0.0:
            raise ValueError("max_abs_forecast must be positive")
        if self.max_reconciliation_error < 0.0:
            raise ValueError("max_reconciliation_error must be non-negative")
        if self.max_probability_sum_error < 0.0:
            raise ValueError("max_probability_sum_error must be non-negative")
        if self.max_revision_mae <= 0.0:
            raise ValueError("max_revision_mae must be positive")
        if not 0.0 <= self.min_revision_direction_accuracy <= 100.0:
            raise ValueError("min_revision_direction_accuracy must be in [0, 100]")
        if not 0.0 <= self.min_turning_point_precision <= 100.0:
            raise ValueError("min_turning_point_precision must be in [0, 100]")
        if self.max_state_mae <= 0.0:
            raise ValueError("max_state_mae must be positive")
        if self.min_states_passing <= 0:
            raise ValueError("min_states_passing must be positive")
        if self.max_probability_change < 0.0:
            raise ValueError("max_probability_change must be non-negative")
        if self.max_ece <= 0.0:
            raise ValueError("max_ece must be positive")


@dataclass(frozen=True)
class AccuracyGateResult:
    """A single accuracy or composition gate result."""

    name: str
    model_name: str
    severity: AccuracyGateSeverity
    passed: bool
    observed: Optional[float] = None
    threshold: Optional[str] = None
    message: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Return a JSON-serializable gate result."""
        return {
            "name": self.name,
            "model_name": self.model_name,
            "severity": self.severity.value,
            "passed": self.passed,
            "observed": self.observed,
            "threshold": self.threshold,
            "message": self.message,
            "metadata": self.metadata,
        }


@dataclass(frozen=True)
class ModelCandidateScore:
    """Accuracy metrics and ranking state for one candidate model path."""

    model_name: str
    metrics: Dict[str, float]
    gates: List[AccuracyGateResult]
    eligible: bool
    selection_score: float
    rank: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        """Return a JSON-serializable candidate score."""
        return {
            "model_name": self.model_name,
            "metrics": self.metrics,
            "gates": [gate.to_dict() for gate in self.gates],
            "eligible": self.eligible,
            "selection_score": self.selection_score,
            "rank": self.rank,
        }


@dataclass(frozen=True)
class ModelSelectionReport:
    """Phase 6.4.2 model selection and accuracy-gate report."""

    passed: bool
    selected_model: Optional[str]
    candidate_scores: List[ModelCandidateScore]
    gates: List[AccuracyGateResult]
    thresholds: AccuracyGateThresholds
    generated_at: str
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Return a JSON-serializable report payload."""
        return {
            "passed": self.passed,
            "selected_model": self.selected_model,
            "generated_at": self.generated_at,
            "metadata": self.metadata,
            "thresholds": asdict(self.thresholds),
            "candidate_scores": [score.to_dict() for score in self.candidate_scores],
            "gates": [gate.to_dict() for gate in self.gates],
        }


def evaluate_model_selection(
    candidates: Mapping[str, Mapping[str, Any]],
    *,
    thresholds: Optional[AccuracyGateThresholds] = None,
    production_candidates: Optional[Iterable[str]] = None,
    excluded_models: Optional[Iterable[str]] = None,
    metadata: Optional[Mapping[str, Any]] = None,
) -> ModelSelectionReport:
    """Evaluate model candidates and select the best eligible forecast path.

    Args:
        candidates: Mapping from model name to payloads containing at least
            ``actuals`` and ``predictions`` arrays. Optional keys include
            ``prediction_intervals``, ``probabilities``, ``binary_actuals``,
            ``revision_actuals``, and ``revision_predictions``.
        thresholds: Optional gate threshold overrides.
        production_candidates: Expected production candidate names.
        excluded_models: Models that must not be selected for production.
        metadata: Optional report metadata.

    Returns:
        ModelSelectionReport with ranked candidates and gate details.
    """
    if not candidates:
        raise ValueError("candidates cannot be empty")

    active_thresholds = thresholds or AccuracyGateThresholds()
    expected_candidates = set(production_candidates or ("midas", "xgboost", "lightgbm"))
    excluded = set(excluded_models or ("dfm",))

    missing_expected = sorted(expected_candidates - set(candidates))
    report_gates: List[AccuracyGateResult] = []
    if missing_expected:
        report_gates.append(
            AccuracyGateResult(
                name="production_candidate_coverage",
                model_name="portfolio",
                severity=AccuracyGateSeverity.CRITICAL,
                passed=False,
                message="Missing expected production candidate model results",
                metadata={"missing": missing_expected, "expected": sorted(expected_candidates)},
            )
        )
    else:
        report_gates.append(
            AccuracyGateResult(
                name="production_candidate_coverage",
                model_name="portfolio",
                severity=AccuracyGateSeverity.INFO,
                passed=True,
                message="All expected production candidate model results are present",
                metadata={"expected": sorted(expected_candidates)},
            )
        )

    scores = [
        _score_candidate(name, payload, active_thresholds, excluded)
        for name, payload in candidates.items()
    ]
    ranked_scores = _rank_scores(scores)
    all_gates = report_gates + [gate for score in ranked_scores for gate in score.gates]
    eligible_scores = [
        score for score in ranked_scores if score.eligible and score.model_name not in excluded
    ]
    selected_model = eligible_scores[0].model_name if eligible_scores else None

    if selected_model is None:
        report_gates.append(
            AccuracyGateResult(
                name="model_selection",
                model_name="portfolio",
                severity=AccuracyGateSeverity.CRITICAL,
                passed=False,
                message="No eligible production model passed accuracy gates",
            )
        )
    else:
        report_gates.append(
            AccuracyGateResult(
                name="model_selection",
                model_name=selected_model,
                severity=AccuracyGateSeverity.INFO,
                passed=True,
                observed=eligible_scores[0].selection_score,
                message="Selected best eligible production model by accuracy score",
            )
        )

    all_gates = report_gates + [gate for score in ranked_scores for gate in score.gates]
    selected_score = next(
        (score for score in ranked_scores if score.model_name == selected_model),
        None,
    )
    selected_has_critical_failure = selected_score is not None and any(
        gate.severity == AccuracyGateSeverity.CRITICAL and not gate.passed
        for gate in selected_score.gates
    )
    portfolio_has_critical_failure = any(
        gate.severity == AccuracyGateSeverity.CRITICAL and not gate.passed for gate in report_gates
    )
    passed = (
        selected_model is not None
        and not selected_has_critical_failure
        and not portfolio_has_critical_failure
    )

    report = ModelSelectionReport(
        passed=passed,
        selected_model=selected_model,
        candidate_scores=ranked_scores,
        gates=all_gates,
        thresholds=active_thresholds,
        generated_at=datetime.now(timezone.utc).isoformat(),
        metadata=dict(metadata or {}),
    )
    logger.info(
        "model_selection_evaluated",
        passed=report.passed,
        selected_model=selected_model,
        n_candidates=len(ranked_scores),
    )
    return report


def evaluate_model_selection_file(
    input_path: Path,
    *,
    report_path: Optional[Path] = None,
) -> ModelSelectionReport:
    """Evaluate a JSON candidate payload and optionally write a report."""
    payload = _load_json_mapping(input_path)
    candidates = payload.get("candidates", payload)
    if not isinstance(candidates, Mapping):
        raise ValueError("selection payload must contain a candidates mapping")

    thresholds_payload = payload.get("thresholds", {})
    thresholds = (
        AccuracyGateThresholds(**thresholds_payload)
        if isinstance(thresholds_payload, Mapping) and thresholds_payload
        else None
    )
    report = evaluate_model_selection(
        candidates,
        thresholds=thresholds,
        production_candidates=payload.get("production_candidates"),
        excluded_models=payload.get("excluded_models"),
        metadata=payload.get("metadata"),
    )
    if report_path is not None:
        report_path = Path(report_path)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report.to_dict(), indent=2) + "\n", encoding="utf-8")
        logger.info("model_selection_report_written", path=str(report_path))
    return report


def _score_candidate(
    model_name: str,
    payload: Mapping[str, Any],
    thresholds: AccuracyGateThresholds,
    excluded_models: set[str],
) -> ModelCandidateScore:
    """Compute metrics and gates for one candidate."""
    y_true = _array(payload, "actuals")
    y_pred = _array(payload, "predictions")
    if y_true.shape != y_pred.shape:
        raise ValueError(f"{model_name}: actuals and predictions must have matching shapes")

    metrics = {
        "smape": smape(y_true, y_pred),
        "rmse": rmse(y_true, y_pred),
    }
    gates = [
        _gate(
            "smape",
            model_name,
            metrics["smape"] <= thresholds.max_smape,
            metrics["smape"],
            f"<= {thresholds.max_smape}",
            "sMAPE deployment gate",
        ),
        _gate(
            "rmse",
            model_name,
            metrics["rmse"] <= thresholds.max_rmse,
            metrics["rmse"],
            f"<= {thresholds.max_rmse}",
            "RMSE deployment gate",
        ),
    ]
    metrics["max_abs_forecast"] = float(np.max(np.abs(y_pred)))
    gates.append(
        _gate(
            "forecast_stability",
            model_name,
            metrics["max_abs_forecast"] <= thresholds.max_abs_forecast,
            metrics["max_abs_forecast"],
            f"<= {thresholds.max_abs_forecast}",
            "Forecast magnitude stability gate",
        )
    )

    reconciliation_errors = payload.get("reconciliation_errors")
    component_sum_predictions = payload.get("component_sum_predictions")
    if reconciliation_errors is not None:
        reconciliation_array = np.asarray(reconciliation_errors, dtype=float)
    elif component_sum_predictions is not None:
        component_sum = np.asarray(component_sum_predictions, dtype=float)
        if component_sum.shape != y_pred.shape:
            raise ValueError(f"{model_name}: component_sum_predictions must match predictions")
        reconciliation_array = y_pred - component_sum
    else:
        reconciliation_array = None
    if reconciliation_array is not None:
        if reconciliation_array.size == 0 or not np.all(np.isfinite(reconciliation_array)):
            raise ValueError(f"{model_name}: reconciliation errors must be finite and non-empty")
        metrics["max_reconciliation_error"] = float(np.max(np.abs(reconciliation_array)))
        gates.append(
            _gate(
                "hierarchical_coherence",
                model_name,
                metrics["max_reconciliation_error"] <= thresholds.max_reconciliation_error,
                metrics["max_reconciliation_error"],
                f"<= {thresholds.max_reconciliation_error}",
                "Hierarchical reconciliation coherence gate",
            )
        )

    intervals = payload.get("prediction_intervals")
    if intervals is not None:
        interval_array = np.asarray(intervals, dtype=float)
        if interval_array.ndim != 2 or interval_array.shape[1] != 2:
            raise ValueError(f"{model_name}: prediction_intervals must be an n x 2 array")
        metrics["coverage_90"] = prediction_interval_coverage(
            y_true,
            interval_array[:, 0],
            interval_array[:, 1],
            confidence_level=90.0,
        )
        gates.append(
            _gate(
                "coverage_90",
                model_name,
                thresholds.min_coverage_90 <= metrics["coverage_90"] <= thresholds.max_coverage_90,
                metrics["coverage_90"],
                f"{thresholds.min_coverage_90} <= coverage <= {thresholds.max_coverage_90}",
                "90% prediction interval coverage gate",
            )
        )

    probabilities = payload.get("probabilities")
    if probabilities is not None:
        probability_matrix = np.asarray(probabilities, dtype=float)
        if probability_matrix.ndim == 1:
            probability_matrix = probability_matrix.reshape(1, -1)
        if probability_matrix.ndim != 2:
            raise ValueError(f"{model_name}: probabilities must be a vector or matrix")
        probability_sum_error = float(np.max(np.abs(probability_matrix.sum(axis=1) - 1.0)))
        metrics["probability_sum_error"] = probability_sum_error
        gates.append(
            _gate(
                "probability_coherence",
                model_name,
                probability_sum_error <= thresholds.max_probability_sum_error,
                probability_sum_error,
                f"<= {thresholds.max_probability_sum_error}",
                "Probability vector coherence gate",
            )
        )

    probability_history = payload.get("probability_history")
    if probability_history is not None:
        history = np.asarray(probability_history, dtype=float)
        if history.ndim != 2 or history.shape[0] < 2:
            raise ValueError(f"{model_name}: probability_history must be a 2D array with 2+ rows")
        probability_change = float(np.mean(np.abs(np.diff(history, axis=0))))
        metrics["avg_probability_change"] = probability_change
        gates.append(
            _gate(
                "probability_stability",
                model_name,
                probability_change <= thresholds.max_probability_change,
                probability_change,
                f"<= {thresholds.max_probability_change}",
                "SN41 probability stability gate",
            )
        )

    binary_actuals = payload.get("binary_actuals")
    if binary_actuals is not None and probabilities is not None:
        probability_matrix = np.asarray(probabilities, dtype=float)
        event_probs = (
            probability_matrix[:, -1] if probability_matrix.ndim == 2 else probability_matrix
        )
        metrics["ece"] = expected_calibration_error(binary_actuals, event_probs)
        gates.append(
            _gate(
                "ece",
                model_name,
                metrics["ece"] <= thresholds.max_ece,
                metrics["ece"],
                f"<= {thresholds.max_ece}",
                "Expected calibration error gate",
            )
        )

    revision_actuals = payload.get("revision_actuals")
    revision_predictions = payload.get("revision_predictions")
    if revision_actuals is not None and revision_predictions is not None:
        revision_true = np.asarray(revision_actuals, dtype=float)
        revision_pred = np.asarray(revision_predictions, dtype=float)
        if revision_true.shape != revision_pred.shape:
            raise ValueError(f"{model_name}: revision arrays must have matching shapes")
        metrics["revision_mae"] = float(np.mean(np.abs(revision_true - revision_pred)))
        metrics["revision_direction_accuracy"] = _direction_accuracy(revision_true, revision_pred)
        gates.append(
            _gate(
                "revision_mae",
                model_name,
                metrics["revision_mae"] <= thresholds.max_revision_mae,
                metrics["revision_mae"],
                f"<= {thresholds.max_revision_mae}",
                "Revision error deployment gate",
            )
        )
        gates.append(
            _gate(
                "revision_direction_accuracy",
                model_name,
                metrics["revision_direction_accuracy"]
                >= thresholds.min_revision_direction_accuracy,
                metrics["revision_direction_accuracy"],
                f">= {thresholds.min_revision_direction_accuracy}",
                "Revision direction accuracy gate",
            )
        )

    turning_actuals = payload.get("turning_point_actuals")
    turning_predictions = payload.get("turning_point_predictions")
    if turning_actuals is not None and turning_predictions is not None:
        metrics["turning_point_precision"] = turning_point_accuracy(
            turning_actuals,
            turning_predictions,
        )
        gates.append(
            _gate(
                "turning_point_precision",
                model_name,
                metrics["turning_point_precision"] >= thresholds.min_turning_point_precision,
                metrics["turning_point_precision"],
                f">= {thresholds.min_turning_point_precision}",
                "Turning point detection gate",
            )
        )

    state_actuals = payload.get("state_actuals")
    state_predictions = payload.get("state_predictions")
    if state_actuals is not None and state_predictions is not None:
        state_mae = _state_mae(state_actuals, state_predictions)
        states_passing = sum(1 for value in state_mae.values() if value <= thresholds.max_state_mae)
        metrics["states_passing_accuracy"] = float(states_passing)
        gates.append(
            AccuracyGateResult(
                name="state_level_accuracy",
                model_name=model_name,
                severity=(
                    AccuracyGateSeverity.INFO
                    if states_passing >= thresholds.min_states_passing
                    else AccuracyGateSeverity.CRITICAL
                ),
                passed=states_passing >= thresholds.min_states_passing,
                observed=float(states_passing),
                threshold=f">= {thresholds.min_states_passing} states <= {thresholds.max_state_mae} MAE",
                message="State-level accuracy gate",
                metadata={"state_mae": state_mae},
            )
        )

    if model_name in excluded_models:
        gates.append(
            AccuracyGateResult(
                name="model_exclusion",
                model_name=model_name,
                severity=AccuracyGateSeverity.WARNING,
                passed=False,
                message="Model is excluded from current production selection",
                metadata={"excluded_models": sorted(excluded_models)},
            )
        )

    eligible = not any(
        gate.severity == AccuracyGateSeverity.CRITICAL and not gate.passed for gate in gates
    )
    if model_name in excluded_models:
        eligible = False

    return ModelCandidateScore(
        model_name=model_name,
        metrics=metrics,
        gates=gates,
        eligible=eligible,
        selection_score=_selection_score(metrics),
    )


def _rank_scores(scores: Sequence[ModelCandidateScore]) -> List[ModelCandidateScore]:
    """Rank candidates by eligibility and selection score."""
    ordered = sorted(
        scores, key=lambda score: (not score.eligible, score.selection_score, score.model_name)
    )
    return [
        ModelCandidateScore(
            model_name=score.model_name,
            metrics=score.metrics,
            gates=score.gates,
            eligible=score.eligible,
            selection_score=score.selection_score,
            rank=index,
        )
        for index, score in enumerate(ordered, start=1)
    ]


def _direction_accuracy(actuals: np.ndarray, predictions: np.ndarray) -> float:
    """Calculate percentage of matching non-zero revision directions."""
    if actuals.size == 0:
        raise ValueError("revision arrays cannot be empty")
    actual_sign = np.sign(actuals)
    predicted_sign = np.sign(predictions)
    return float(np.mean(actual_sign == predicted_sign) * 100.0)


def _state_mae(
    state_actuals: Mapping[str, Iterable[float]],
    state_predictions: Mapping[str, Iterable[float]],
) -> Dict[str, float]:
    """Calculate per-state MAE for state-level gate validation."""
    if not state_actuals:
        raise ValueError("state_actuals cannot be empty")
    missing_states = sorted(set(state_actuals) - set(state_predictions))
    if missing_states:
        raise ValueError(f"state_predictions missing states: {missing_states}")

    values: Dict[str, float] = {}
    for state, actual_values in state_actuals.items():
        actual_array = np.asarray(list(actual_values), dtype=float)
        predicted_array = np.asarray(list(state_predictions[state]), dtype=float)
        if actual_array.shape != predicted_array.shape or actual_array.size == 0:
            raise ValueError(
                f"{state}: state actuals and predictions must be non-empty matching arrays"
            )
        values[state] = round(float(np.mean(np.abs(actual_array - predicted_array))), 6)
    return values


def _selection_score(metrics: Mapping[str, float]) -> float:
    """Combine accuracy metrics into a deterministic lower-is-better ranking score."""
    coverage_penalty = 0.0
    if "coverage_90" in metrics:
        coverage_penalty = abs(metrics["coverage_90"] - 90.0)
    ece_penalty = metrics.get("ece", 0.0) * 100.0
    coherence_penalty = metrics.get("probability_sum_error", 0.0) * 1000.0
    revision_penalty = metrics.get("revision_mae", 0.0) / 1000.0
    reconciliation_penalty = metrics.get("max_reconciliation_error", 0.0) / 100.0
    probability_stability_penalty = metrics.get("avg_probability_change", 0.0) * 10.0
    return round(
        metrics["smape"]
        + metrics["rmse"] / 1000.0
        + coverage_penalty
        + ece_penalty
        + coherence_penalty
        + revision_penalty
        + reconciliation_penalty
        + probability_stability_penalty,
        6,
    )


def _gate(
    name: str,
    model_name: str,
    passed: bool,
    observed: float,
    threshold: str,
    message: str,
) -> AccuracyGateResult:
    """Build a gate result with critical severity on failure."""
    return AccuracyGateResult(
        name=name,
        model_name=model_name,
        severity=AccuracyGateSeverity.INFO if passed else AccuracyGateSeverity.CRITICAL,
        passed=passed,
        observed=round(float(observed), 6),
        threshold=threshold,
        message=message,
    )


def _array(payload: Mapping[str, Any], key: str) -> np.ndarray:
    """Read a required one-dimensional numeric array from a payload."""
    if key not in payload:
        raise ValueError(f"candidate payload must contain {key}")
    values = np.asarray(payload[key], dtype=float)
    if values.ndim != 1 or values.size == 0:
        raise ValueError(f"{key} must be a non-empty one-dimensional array")
    if not np.all(np.isfinite(values)):
        raise ValueError(f"{key} must contain only finite values")
    return values


def _load_json_mapping(path: Path) -> Dict[str, Any]:
    """Load a JSON object from disk."""
    with Path(path).open("r", encoding="utf-8") as file_obj:
        payload = json.load(file_obj)
    if not isinstance(payload, dict):
        raise ValueError("selection payload must be a JSON object")
    return payload
