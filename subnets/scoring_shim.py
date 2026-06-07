"""Subnet-agnostic probability validation and scoring utilities."""

import math
from dataclasses import dataclass, field
from typing import Any, Dict, Mapping, Optional, Sequence

from subnets.base_adapter import SubnetConfig


DEFAULT_PROBABILITY_FLOOR = 1e-12


class ScoringError(ValueError):
    """Raised when subnet scoring inputs or configuration are invalid."""


@dataclass(frozen=True)
class ProbabilityValidationResult:
    """Validation result for a subnet probability vector."""

    is_valid: bool
    total_probability: float
    tolerance: float
    missing_bins: Sequence[str] = field(default_factory=tuple)
    extra_bins: Sequence[str] = field(default_factory=tuple)
    negative_bins: Sequence[str] = field(default_factory=tuple)

    @property
    def total_error(self) -> float:
        """Return absolute error from a coherent probability sum."""
        return abs(self.total_probability - 1.0)


@dataclass(frozen=True)
class ScoringResult:
    """Result of scoring one observed outcome against a probability vector."""

    metric: str
    score: float
    event_id: str
    observed_bin_label: str
    observed_probability: float
    metadata: Mapping[str, Any] = field(default_factory=dict)


class SubnetScoringShim:
    """Validate and score probability forecasts for one subnet config."""

    def __init__(self, config: SubnetConfig) -> None:
        """Initialize scoring shim with validated subnet configuration."""
        self.config = config

    def validate_probabilities(
        self, event_id: str, probabilities: Mapping[str, float]
    ) -> ProbabilityValidationResult:
        """Validate probability labels, non-negativity, and coherence."""
        event = self._event(event_id)
        expected_labels = set(_bin_labels(event))
        provided_labels = set(probabilities)
        missing_bins = tuple(sorted(expected_labels - provided_labels))
        extra_bins = tuple(sorted(provided_labels - expected_labels))
        negative_bins = tuple(
            sorted(label for label, probability in probabilities.items() if probability < 0.0)
        )
        total_probability = float(sum(probabilities.values()))
        tolerance = self._probability_tolerance()
        is_valid = (
            not missing_bins
            and not extra_bins
            and not negative_bins
            and math.isfinite(total_probability)
            and abs(total_probability - 1.0) <= tolerance
        )
        return ProbabilityValidationResult(
            is_valid=is_valid,
            total_probability=total_probability,
            tolerance=tolerance,
            missing_bins=missing_bins,
            extra_bins=extra_bins,
            negative_bins=negative_bins,
        )

    def normalize_probabilities(
        self, event_id: str, probabilities: Mapping[str, float]
    ) -> Dict[str, float]:
        """Return a normalized probability vector after validating labels and signs."""
        validation = self.validate_probabilities(event_id, probabilities)
        if validation.missing_bins or validation.extra_bins or validation.negative_bins:
            raise ScoringError("probability vector labels and values must be valid to normalize")
        if validation.total_probability <= 0.0 or not math.isfinite(validation.total_probability):
            raise ScoringError("total_probability must be positive and finite")
        return {
            label: float(probability) / validation.total_probability
            for label, probability in probabilities.items()
        }

    def score_observation(
        self, event_id: str, probabilities: Mapping[str, float], observed_value: float
    ) -> ScoringResult:
        """Score one observed numeric outcome against an event probability vector."""
        validation = self.validate_probabilities(event_id, probabilities)
        if not validation.is_valid:
            raise ScoringError("probability vector is not valid for scoring")

        metric = str(self.config.scoring.get("metric", "")).strip()
        if metric != "log_score":
            raise ScoringError(f"Unsupported scoring metric: {metric}")

        event = self._event(event_id)
        observed_bin_label = _observed_bin_label(event, observed_value)
        observed_probability = float(probabilities[observed_bin_label])
        probability_floor = self._probability_floor()
        score = math.log(max(observed_probability, probability_floor))
        return ScoringResult(
            metric=metric,
            score=score,
            event_id=event_id,
            observed_bin_label=observed_bin_label,
            observed_probability=observed_probability,
            metadata={
                "probability_floor": probability_floor,
                "total_probability": validation.total_probability,
            },
        )

    def _event(self, event_id: str) -> Mapping[str, Any]:
        """Return a configured event by ID."""
        normalized_event_id = event_id.strip()
        if not normalized_event_id:
            raise ScoringError("event_id is required")
        for event in self.config.events:
            if event.get("event_id") == normalized_event_id:
                return event
        raise ScoringError(f"Unknown event_id: {event_id}")

    def _probability_tolerance(self) -> float:
        """Return configured probability coherence tolerance."""
        tolerance = float(self.config.scoring.get("probability_tolerance", 0.001))
        if tolerance < 0.0:
            raise ScoringError("probability_tolerance must be non-negative")
        return tolerance

    def _probability_floor(self) -> float:
        """Return configured probability floor for log scoring."""
        probability_floor = float(
            self.config.scoring.get("probability_floor", DEFAULT_PROBABILITY_FLOOR)
        )
        if probability_floor <= 0.0 or probability_floor >= 1.0:
            raise ScoringError("probability_floor must be between 0 and 1")
        return probability_floor


def _bin_labels(event: Mapping[str, Any]) -> Sequence[str]:
    """Return bin labels from an event definition."""
    bins = _event_bins(event)
    labels = []
    for bin_definition in bins:
        label = bin_definition.get("label")
        if not isinstance(label, str) or not label.strip():
            raise ScoringError("each bin requires a non-empty label")
        labels.append(label)
    return tuple(labels)


def _observed_bin_label(event: Mapping[str, Any], observed_value: float) -> str:
    """Return the bin label containing a numeric observed value."""
    if not math.isfinite(observed_value):
        raise ScoringError("observed_value must be finite")
    for bin_definition in _event_bins(event):
        label = str(bin_definition["label"])
        lower = bin_definition.get("lower")
        upper = bin_definition.get("upper")
        if _lower_matches(observed_value, lower) and _upper_matches(observed_value, upper):
            return label
    raise ScoringError(f"observed_value {observed_value} does not fall into any configured bin")


def _event_bins(event: Mapping[str, Any]) -> Sequence[Mapping[str, Any]]:
    """Return event bins after validating their shape."""
    bins = event.get("bins")
    if not isinstance(bins, Sequence) or isinstance(bins, (str, bytes)) or not bins:
        raise ScoringError("event.bins must be a non-empty sequence")
    if not all(isinstance(bin_definition, Mapping) for bin_definition in bins):
        raise ScoringError("event.bins must contain mappings")
    return bins


def _lower_matches(observed_value: float, lower: Optional[object]) -> bool:
    """Return whether observed value satisfies a lower bin bound."""
    if lower is None:
        return True
    return observed_value >= float(lower)


def _upper_matches(observed_value: float, upper: Optional[object]) -> bool:
    """Return whether observed value satisfies an upper bin bound."""
    if upper is None:
        return True
    return observed_value < float(upper)
