"""Tests for SN41 payload builder extraction."""

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from subnets.config import load_subnet_config
from subnets.scoring_shim import SubnetScoringShim
from subnets.sn41.payload_builder import (
    build_event_payloads,
    build_sn41_payload,
    extract_event_probabilities,
    validate_sn41_payload,
)


REPO_ROOT = Path(__file__).resolve().parents[3]
CONFIG_DIR = REPO_ROOT / "configs" / "subnets"
FIXED_TIME = datetime(2026, 6, 6, 12, 0, tzinfo=timezone.utc)


def _probabilities() -> dict[str, float]:
    """Return a coherent SN41 probability vector fixture."""
    return {
        "below_0k": 0.05,
        "0k_to_50k": 0.10,
        "50k_to_100k": 0.15,
        "100k_to_150k": 0.25,
        "150k_to_200k": 0.20,
        "200k_to_300k": 0.15,
        "above_300k": 0.10,
    }


def test_extract_event_probabilities_supports_nested_events_key() -> None:
    """Payload builder should accept nested event probability mappings."""
    predictions = {"events": {"nfp_next_release": _probabilities()}}
    extracted = extract_event_probabilities(predictions, "nfp_next_release")
    assert extracted["100k_to_150k"] == 0.25


def test_extract_event_probabilities_requires_mapping() -> None:
    """Payload builder should reject missing probability mappings."""
    with pytest.raises(ValueError, match="Missing probability mapping"):
        extract_event_probabilities({}, "nfp_next_release")


def test_build_event_payloads_validates_probability_coherence() -> None:
    """Event payload construction should enforce scoring shim validation."""
    config = load_subnet_config("sn41", config_dir=CONFIG_DIR)
    scoring = SubnetScoringShim(config)
    invalid = {"nfp_next_release": {"below_0k": 1.0}}

    with pytest.raises(ValueError, match="Invalid probabilities"):
        build_event_payloads(config.events, invalid, scoring)


def test_build_sn41_payload_is_deterministic_with_fixed_timestamp() -> None:
    """SN41 payload builder should produce stable JSON for fixed timestamps."""
    config = load_subnet_config("sn41", config_dir=CONFIG_DIR)
    scoring = SubnetScoringShim(config)
    predictions = {"nfp_next_release": _probabilities()}

    first = build_sn41_payload(config, predictions, scoring, generated_at=FIXED_TIME)
    second = build_sn41_payload(config, predictions, scoring, generated_at=FIXED_TIME)

    assert first == second
    decoded = json.loads(first.decode("utf-8"))
    assert decoded["generated_at"] == FIXED_TIME.isoformat()
    assert decoded["events"][0]["total_probability"] == 1.0


def test_validate_sn41_payload_rejects_incoherent_probabilities() -> None:
    """SN41 payload validation should reject invalid probability vectors."""
    config = load_subnet_config("sn41", config_dir=CONFIG_DIR)
    scoring = SubnetScoringShim(config)
    payload = {
        "subnet_id": "sn41",
        "adapter_version": "0.1.0",
        "generated_at": FIXED_TIME.isoformat(),
        "events": [
            {
                "event_id": "nfp_next_release",
                "target": "NFP",
                "probabilities": {"below_0k": 1.0},
                "total_probability": 1.0,
            }
        ],
    }

    assert validate_sn41_payload(config, json.dumps(payload).encode("utf-8"), scoring) is False
