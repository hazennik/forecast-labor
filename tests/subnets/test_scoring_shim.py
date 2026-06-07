"""Tests for subnet-agnostic scoring shim behavior."""

import math
from typing import Any, Dict

import pytest

from subnets.base_adapter import SubnetConfig
from subnets.scoring_shim import ScoringError, SubnetScoringShim


def _config(**overrides: Any) -> SubnetConfig:
    """Create a scoring config fixture."""
    scoring: Dict[str, Any] = {
        "metric": "log_score",
        "probability_tolerance": 0.001,
        "probability_floor": 1e-9,
    }
    scoring.update(overrides.pop("scoring", {}))
    return SubnetConfig(
        subnet_id="mock",
        name="Mock Subnet",
        netuid=999,
        adapter_version="0.1.0",
        events=[
            {
                "event_id": "nfp_release",
                "target": "NFP",
                "bins": [
                    {"label": "below_0k", "lower": None, "upper": 0},
                    {"label": "0k_to_100k", "lower": 0, "upper": 100000},
                    {"label": "above_100k", "lower": 100000, "upper": None},
                ],
            }
        ],
        cadence={"type": "monthly"},
        scoring=scoring,
        network={"endpoint": "mock://localhost"},
    )


def test_scoring_shim_validates_coherent_probability_vector() -> None:
    """Probability vectors should match configured bins and sum within tolerance."""
    shim = SubnetScoringShim(_config())

    validation = shim.validate_probabilities(
        "nfp_release",
        {"below_0k": 0.1, "0k_to_100k": 0.7, "above_100k": 0.2},
    )

    assert validation.is_valid is True
    assert validation.total_probability == pytest.approx(1.0)
    assert validation.total_error == pytest.approx(0.0)
    assert validation.missing_bins == ()
    assert validation.extra_bins == ()
    assert validation.negative_bins == ()


def test_scoring_shim_reports_probability_label_and_value_errors() -> None:
    """Validation should report missing, extra, negative, and incoherent probabilities."""
    shim = SubnetScoringShim(_config())

    validation = shim.validate_probabilities(
        "nfp_release",
        {"below_0k": 0.5, "0k_to_100k": -0.1, "unexpected": 0.7},
    )

    assert validation.is_valid is False
    assert validation.missing_bins == ("above_100k",)
    assert validation.extra_bins == ("unexpected",)
    assert validation.negative_bins == ("0k_to_100k",)
    assert validation.total_probability == pytest.approx(1.1)


def test_scoring_shim_normalizes_valid_labeled_vector() -> None:
    """Normalization should preserve labels and scale probabilities to one."""
    shim = SubnetScoringShim(_config(scoring={"probability_tolerance": 0.5}))

    normalized = shim.normalize_probabilities(
        "nfp_release",
        {"below_0k": 2.0, "0k_to_100k": 6.0, "above_100k": 2.0},
    )

    assert normalized == {
        "below_0k": pytest.approx(0.2),
        "0k_to_100k": pytest.approx(0.6),
        "above_100k": pytest.approx(0.2),
    }
    assert sum(normalized.values()) == pytest.approx(1.0)


def test_scoring_shim_scores_observed_value_with_log_score() -> None:
    """Observed numeric outcomes should be assigned to the matching configured bin."""
    shim = SubnetScoringShim(_config())

    result = shim.score_observation(
        "nfp_release",
        {"below_0k": 0.1, "0k_to_100k": 0.7, "above_100k": 0.2},
        observed_value=125000,
    )

    assert result.metric == "log_score"
    assert result.event_id == "nfp_release"
    assert result.observed_bin_label == "above_100k"
    assert result.observed_probability == pytest.approx(0.2)
    assert result.score == pytest.approx(math.log(0.2))
    assert result.metadata["total_probability"] == pytest.approx(1.0)


def test_scoring_shim_uses_probability_floor_for_zero_observed_probability() -> None:
    """Log scoring should remain finite when observed bin probability is zero."""
    shim = SubnetScoringShim(_config())

    result = shim.score_observation(
        "nfp_release",
        {"below_0k": 0.0, "0k_to_100k": 0.8, "above_100k": 0.2},
        observed_value=-1000,
    )

    assert result.observed_bin_label == "below_0k"
    assert result.observed_probability == 0.0
    assert result.score == pytest.approx(math.log(1e-9))


def test_scoring_shim_rejects_unsupported_metric() -> None:
    """Scoring shim should fail fast on unsupported subnet metrics."""
    shim = SubnetScoringShim(_config(scoring={"metric": "unsupported"}))

    with pytest.raises(ScoringError, match="Unsupported scoring metric"):
        shim.score_observation(
            "nfp_release",
            {"below_0k": 0.1, "0k_to_100k": 0.7, "above_100k": 0.2},
            observed_value=10,
        )


def test_scoring_shim_rejects_observed_value_outside_bins() -> None:
    """Outcomes outside configured bins should not be silently scored."""
    config = _config()
    event = dict(config.events[0])
    event["bins"] = [{"label": "narrow", "lower": 0, "upper": 10}]
    shim = SubnetScoringShim(
        SubnetConfig(
            subnet_id=config.subnet_id,
            name=config.name,
            netuid=config.netuid,
            adapter_version=config.adapter_version,
            events=[event],
            cadence=config.cadence,
            scoring=config.scoring,
            network=config.network,
        )
    )

    with pytest.raises(ScoringError, match="does not fall into any configured bin"):
        shim.score_observation("nfp_release", {"narrow": 1.0}, observed_value=100)


def test_scoring_shim_rejects_invalid_bin_definitions() -> None:
    """Every event bin should have a non-empty label."""
    config = _config()
    event = dict(config.events[0])
    event["bins"] = [{"lower": None, "upper": None}]
    shim = SubnetScoringShim(
        SubnetConfig(
            subnet_id=config.subnet_id,
            name=config.name,
            netuid=config.netuid,
            adapter_version=config.adapter_version,
            events=[event],
            cadence=config.cadence,
            scoring=config.scoring,
            network=config.network,
        )
    )

    with pytest.raises(ScoringError, match="each bin requires"):
        shim.validate_probabilities("nfp_release", {"missing_label": 1.0})
