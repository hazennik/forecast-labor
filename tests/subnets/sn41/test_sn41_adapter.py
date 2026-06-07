"""Tests for the first SN41 adapter slice."""

import hashlib
import json
import secrets
from pathlib import Path

import pytest

from subnets import create_default_registry
from subnets.base_adapter import SubmissionKeyPaths
from subnets.config import load_subnet_config
from subnets.sn41 import SN41Adapter, get_sn41_event_catalog


REPO_ROOT = Path(__file__).resolve().parents[3]
CONFIG_DIR = REPO_ROOT / "configs" / "subnets"


def _probabilities() -> dict:
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


def test_sn41_config_loads_event_catalog() -> None:
    """SN41 config should load through the generic config loader."""
    config = load_subnet_config("sn41", config_dir=CONFIG_DIR)
    catalog = get_sn41_event_catalog(config)

    assert config.subnet_id == "sn41"
    assert config.netuid == 41
    assert config.scoring["metric"] == "log_score"
    assert len(catalog) == 1
    assert catalog[0]["event_id"] == "nfp_next_release"
    assert len(catalog[0]["bins"]) == 7


def test_sn41_adapter_builds_deterministic_valid_payload() -> None:
    """SN41 adapter should build JSON payloads that validate offline."""
    adapter = SN41Adapter(load_subnet_config("sn41", config_dir=CONFIG_DIR))

    payload = adapter.build_payload({"nfp_next_release": _probabilities()})
    decoded = json.loads(payload.decode("utf-8"))

    assert adapter.validate_payload(payload) is True
    assert decoded["subnet_id"] == "sn41"
    assert decoded["adapter_version"] == "0.1.0"
    assert decoded["events"][0]["event_id"] == "nfp_next_release"
    assert decoded["events"][0]["probabilities"]["100k_to_150k"] == 0.25
    assert decoded["events"][0]["total_probability"] == 1.0


def test_sn41_adapter_rejects_invalid_payload_probabilities() -> None:
    """SN41 payload validation should reject incoherent probability vectors."""
    adapter = SN41Adapter(load_subnet_config("sn41", config_dir=CONFIG_DIR))
    payload = {
        "subnet_id": "sn41",
        "adapter_version": "0.1.0",
        "generated_at": "2026-06-06T00:00:00+00:00",
        "events": [
            {
                "event_id": "nfp_next_release",
                "target": "NFP",
                "probabilities": {"below_0k": 1.0},
                "total_probability": 1.0,
            }
        ],
    }

    assert adapter.validate_payload(json.dumps(payload).encode("utf-8")) is False


def test_sn41_adapter_dry_run_submit_returns_payload_hash(tmp_path: Path) -> None:
    """SN41 dry-run submit should validate payloads and return shared telemetry."""
    hotkey_path = tmp_path / "hotkey"
    hotkey_path.write_text(secrets.token_bytes(32).hex())
    adapter = SN41Adapter(load_subnet_config("sn41", config_dir=CONFIG_DIR))
    payload = adapter.build_payload({"events": {"nfp_next_release": _probabilities()}})

    result = adapter.submit(payload, SubmissionKeyPaths(hotkey_path=hotkey_path))

    assert result.success is True
    assert result.subnet_id == "sn41"
    assert result.status == "dry_run"
    assert result.payload_hash == hashlib.sha256(payload).hexdigest()
    assert result.metadata["network_submission"] is False
    assert result.metadata["hotkey_path"] == str(hotkey_path)
    assert "signature_hex" in result.metadata
    assert result.metadata["signature_algorithm"] == "hmac-sha256"


def test_default_registry_loads_active_sn41_adapter(monkeypatch) -> None:
    """Default registry should wire ACTIVE_SUBNET=sn41 to SN41Adapter."""
    registry = create_default_registry(config_dir=CONFIG_DIR)
    monkeypatch.setenv("ACTIVE_SUBNET", "sn41")

    adapter = registry.get_active_adapter()

    assert isinstance(adapter, SN41Adapter)
    assert adapter.subnet_id == "sn41"


def test_sn41_adapter_requires_sn41_config() -> None:
    """SN41Adapter should fail fast when given another subnet config."""
    config = load_subnet_config("sn41", config_dir=CONFIG_DIR)
    wrong_config = type(config)(
        subnet_id="other",
        name=config.name,
        netuid=config.netuid,
        adapter_version=config.adapter_version,
        events=config.events,
        cadence=config.cadence,
        scoring=config.scoring,
        network=config.network,
        submission=config.submission,
        metadata=config.metadata,
    )

    with pytest.raises(ValueError, match="requires sn41 config"):
        SN41Adapter(wrong_config)
