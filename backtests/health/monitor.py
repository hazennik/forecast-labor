"""Health monitoring for model backtest execution.

Phase 6 backtests need fast, explicit checks for known Phase 5 risks:
unrealistic DFM magnitudes, MIDAS convergence failures, poor calibration
coverage, non-finite forecasts, and weak accuracy. This module provides a small
pure-Python monitor that can be called after each model run or fold.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Iterable, List, Mapping, Optional

import numpy as np
from loguru import logger

from models_src.utils.metrics import prediction_interval_coverage, smape


class HealthCheckSeverity(str, Enum):
    """Severity levels for model health findings."""

    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


@dataclass(frozen=True)
class HealthThresholds:
    """Thresholds used by model health checks."""

    max_abs_forecast: float = 1_000_000.0
    max_abs_forecast_hard: float = 2_000_000.0
    min_coverage_90: float = 85.0
    max_coverage_90: float = 95.0
    max_smape: float = 20.0

    def __post_init__(self) -> None:
        """Validate threshold ordering."""
        if self.max_abs_forecast <= 0.0:
            raise ValueError("max_abs_forecast must be positive")
        if self.max_abs_forecast_hard < self.max_abs_forecast:
            raise ValueError("max_abs_forecast_hard must be >= max_abs_forecast")
        if not 0.0 <= self.min_coverage_90 <= self.max_coverage_90 <= 100.0:
            raise ValueError("coverage thresholds must satisfy 0 <= min <= max <= 100")
        if self.max_smape <= 0.0:
            raise ValueError("max_smape must be positive")


@dataclass(frozen=True)
class HealthCheckIssue:
    """A single model health finding."""

    check_name: str
    severity: HealthCheckSeverity
    message: str
    observed_value: Optional[float] = None
    threshold: Optional[float] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ModelHealthReport:
    """Health report for one model run or fold."""

    model_name: str
    issues: List[HealthCheckIssue]
    metrics: Dict[str, float]
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def passed(self) -> bool:
        """Return True when no critical issues were found."""
        return not any(issue.severity == HealthCheckSeverity.CRITICAL for issue in self.issues)

    @property
    def has_warnings(self) -> bool:
        """Return True when any warning or critical issue was found."""
        return any(
            issue.severity in {HealthCheckSeverity.WARNING, HealthCheckSeverity.CRITICAL}
            for issue in self.issues
        )

    def to_dict(self) -> Dict[str, Any]:
        """Return a JSON-serializable report payload."""
        return {
            "model_name": self.model_name,
            "passed": self.passed,
            "has_warnings": self.has_warnings,
            "metrics": self.metrics,
            "metadata": self.metadata,
            "issues": [
                {
                    "check_name": issue.check_name,
                    "severity": issue.severity.value,
                    "message": issue.message,
                    "observed_value": issue.observed_value,
                    "threshold": issue.threshold,
                    "metadata": issue.metadata,
                }
                for issue in self.issues
            ],
        }


class ModelHealthMonitor:
    """Run model health checks during Phase 6 backtest execution."""

    def __init__(self, thresholds: Optional[HealthThresholds] = None) -> None:
        """Initialize the monitor with optional custom thresholds."""
        self.thresholds = thresholds or HealthThresholds()

    def evaluate_model_run(
        self,
        model_name: str,
        predictions: Iterable[float],
        *,
        actuals: Optional[Iterable[float]] = None,
        prediction_intervals: Optional[Iterable[Iterable[float]]] = None,
        convergence_warnings: Optional[Iterable[str]] = None,
        metadata: Optional[Mapping[str, Any]] = None,
    ) -> ModelHealthReport:
        """Evaluate one model run for Phase 6 health risks.

        Args:
            model_name: Name of the model being checked.
            predictions: Forecast vector.
            actuals: Optional realized target values for accuracy checks.
            prediction_intervals: Optional lower/upper interval matrix.
            convergence_warnings: Optional optimizer/convergence warning messages.
            metadata: Optional report metadata such as fold or vintage date.

        Returns:
            Health report with issues and measured metrics.
        """
        model_key = model_name.lower()
        y_pred = np.asarray(list(predictions), dtype=float)
        y_true = None if actuals is None else np.asarray(list(actuals), dtype=float)
        intervals = (
            None
            if prediction_intervals is None
            else np.asarray(list(prediction_intervals), dtype=float)
        )
        warnings = list(convergence_warnings or [])

        issues: List[HealthCheckIssue] = []
        metrics: Dict[str, float] = {}

        issues.extend(self._check_prediction_shape(y_pred))
        issues.extend(self._check_forecast_magnitude(model_key, y_pred, metrics))
        issues.extend(self._check_convergence(model_key, warnings, metrics))

        if y_true is not None:
            issues.extend(self._check_actuals_shape(y_true, y_pred))
            if len(y_true) == len(y_pred):
                issues.extend(self._check_accuracy(y_true, y_pred, metrics))

        if y_true is not None and intervals is not None:
            issues.extend(self._check_interval_coverage(y_true, intervals, metrics))

        report = ModelHealthReport(
            model_name=model_name,
            issues=issues,
            metrics=metrics,
            metadata=dict(metadata or {}),
        )
        logger.info(
            "model_health_evaluated",
            model_name=model_name,
            passed=report.passed,
            n_issues=len(report.issues),
            metrics=metrics,
        )
        return report

    def _check_prediction_shape(self, y_pred: np.ndarray) -> List[HealthCheckIssue]:
        """Validate prediction vector shape and finite values."""
        issues: List[HealthCheckIssue] = []
        if y_pred.ndim != 1:
            issues.append(
                HealthCheckIssue(
                    check_name="prediction_shape",
                    severity=HealthCheckSeverity.CRITICAL,
                    message="Predictions must be a one-dimensional vector",
                    observed_value=float(y_pred.ndim),
                    threshold=1.0,
                )
            )
            return issues
        if y_pred.size == 0:
            issues.append(
                HealthCheckIssue(
                    check_name="prediction_empty",
                    severity=HealthCheckSeverity.CRITICAL,
                    message="Predictions cannot be empty",
                    observed_value=0.0,
                    threshold=1.0,
                )
            )
            return issues
        non_finite = int((~np.isfinite(y_pred)).sum())
        if non_finite > 0:
            issues.append(
                HealthCheckIssue(
                    check_name="prediction_finite",
                    severity=HealthCheckSeverity.CRITICAL,
                    message="Predictions contain NaN or infinite values",
                    observed_value=float(non_finite),
                    threshold=0.0,
                )
            )
        return issues

    def _check_forecast_magnitude(
        self,
        model_key: str,
        y_pred: np.ndarray,
        metrics: Dict[str, float],
    ) -> List[HealthCheckIssue]:
        """Flag unrealistic forecast magnitudes."""
        if y_pred.size == 0 or not np.isfinite(y_pred).any():
            return []
        max_abs = float(np.nanmax(np.abs(y_pred)))
        metrics["max_abs_forecast"] = max_abs

        if max_abs > self.thresholds.max_abs_forecast_hard:
            return [
                HealthCheckIssue(
                    check_name="forecast_magnitude_hard_gate",
                    severity=HealthCheckSeverity.CRITICAL,
                    message="Forecast magnitude exceeds hard stability gate",
                    observed_value=max_abs,
                    threshold=self.thresholds.max_abs_forecast_hard,
                    metadata={"model_type": model_key},
                )
            ]
        if model_key == "dfm" and max_abs > self.thresholds.max_abs_forecast:
            return [
                HealthCheckIssue(
                    check_name="dfm_instability",
                    severity=HealthCheckSeverity.WARNING,
                    message="DFM forecast magnitude exceeds Phase 6 instability watch threshold",
                    observed_value=max_abs,
                    threshold=self.thresholds.max_abs_forecast,
                    metadata={"model_type": model_key},
                )
            ]
        return []

    def _check_convergence(
        self,
        model_key: str,
        warnings: List[str],
        metrics: Dict[str, float],
    ) -> List[HealthCheckIssue]:
        """Flag model convergence warnings captured during execution."""
        metrics["convergence_warning_count"] = float(len(warnings))
        if not warnings:
            return []

        severity = HealthCheckSeverity.WARNING
        if model_key == "midas":
            check_name = "midas_convergence"
            message = "MIDAS optimization emitted convergence warnings"
        else:
            check_name = "model_convergence"
            message = "Model emitted convergence warnings"

        return [
            HealthCheckIssue(
                check_name=check_name,
                severity=severity,
                message=message,
                observed_value=float(len(warnings)),
                threshold=0.0,
                metadata={"warnings": warnings[:5], "model_type": model_key},
            )
        ]

    def _check_actuals_shape(self, y_true: np.ndarray, y_pred: np.ndarray) -> List[HealthCheckIssue]:
        """Validate actuals align with predictions."""
        if y_true.shape != y_pred.shape:
            return [
                HealthCheckIssue(
                    check_name="actuals_shape",
                    severity=HealthCheckSeverity.CRITICAL,
                    message="Actual values must have the same shape as predictions",
                    observed_value=float(y_true.size),
                    threshold=float(y_pred.size),
                )
            ]
        if not np.all(np.isfinite(y_true)):
            return [
                HealthCheckIssue(
                    check_name="actuals_finite",
                    severity=HealthCheckSeverity.CRITICAL,
                    message="Actual values contain NaN or infinite values",
                )
            ]
        return []

    def _check_accuracy(
        self,
        y_true: np.ndarray,
        y_pred: np.ndarray,
        metrics: Dict[str, float],
    ) -> List[HealthCheckIssue]:
        """Check sMAPE against the Phase 6 accuracy gate."""
        if not np.all(np.isfinite(y_pred)) or not np.all(np.isfinite(y_true)):
            return []
        observed_smape = float(smape(y_true, y_pred))
        metrics["smape"] = observed_smape
        if observed_smape > self.thresholds.max_smape:
            return [
                HealthCheckIssue(
                    check_name="smape_gate",
                    severity=HealthCheckSeverity.WARNING,
                    message="sMAPE exceeds Phase 6 deployment gate",
                    observed_value=observed_smape,
                    threshold=self.thresholds.max_smape,
                )
            ]
        return []

    def _check_interval_coverage(
        self,
        y_true: np.ndarray,
        intervals: np.ndarray,
        metrics: Dict[str, float],
    ) -> List[HealthCheckIssue]:
        """Check 90% prediction interval coverage gate."""
        if intervals.ndim != 2 or intervals.shape[1] != 2 or intervals.shape[0] != y_true.size:
            return [
                HealthCheckIssue(
                    check_name="interval_shape",
                    severity=HealthCheckSeverity.CRITICAL,
                    message="Prediction intervals must be shaped (n_samples, 2)",
                    observed_value=float(intervals.size),
                    threshold=float(y_true.size * 2),
                )
            ]
        if not np.all(np.isfinite(intervals)):
            return [
                HealthCheckIssue(
                    check_name="interval_finite",
                    severity=HealthCheckSeverity.CRITICAL,
                    message="Prediction intervals contain NaN or infinite values",
                )
            ]

        coverage = float(prediction_interval_coverage(y_true, intervals[:, 0], intervals[:, 1]))
        metrics["coverage_90"] = coverage
        if coverage < self.thresholds.min_coverage_90:
            return [
                HealthCheckIssue(
                    check_name="coverage_low",
                    severity=HealthCheckSeverity.WARNING,
                    message="90% prediction interval coverage is below the Phase 6 gate",
                    observed_value=coverage,
                    threshold=self.thresholds.min_coverage_90,
                )
            ]
        if coverage > self.thresholds.max_coverage_90:
            return [
                HealthCheckIssue(
                    check_name="coverage_high",
                    severity=HealthCheckSeverity.WARNING,
                    message="90% prediction interval coverage is above the Phase 6 gate",
                    observed_value=coverage,
                    threshold=self.thresholds.max_coverage_90,
                )
            ]
        return []
