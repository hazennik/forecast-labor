"""Tests for the Phase 7 base subnet adapter contract."""

from pathlib import Path
from typing import Any, Mapping, Sequence

import pytest
import yaml

from subnets.base_adapter import (
    BaseSubnetAdapter,
    SubmissionKeyPaths,
    SubmissionResult,
    SubnetConfig,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
TEMPLATE_CONFIG = REPO_ROOT / "configs" / "subnets" / "template.yaml"


class MockSubnetAdapter(BaseSubnetAdapter):
    """Minimal adapter implementation for contract tests."""

    def __init__(self) -> None:
        """Initialize the mock adapter with deterministic configuration."""
        self.config = SubnetConfig(
            subnet_id="mock",
            name="Mock Subnet",
            netuid=999,
            adapter_version="0.1.0",
            events=[{"event_id": "mock_event", "target": "NFP"}],
            cadence={"type": "monthly"},
            scoring={"metric": "log_score"},
            network={"endpoint": "mock://localhost"},
        )

    def get_config(self) -> SubnetConfig:
        """Return mock configuration."""
        return self.config

    def get_event_catalog(self) -> Sequence[Mapping[str, Any]]:
        """Return mock events."""
        return self.config.events

    def build_payload(self, predictions: Mapping[str, Any]) -> bytes:
        """Build a deterministic mock payload."""
        if not predictions:
            raise ValueError("predictions cannot be empty")
        return b'{"mock": true}'

    def validate_payload(self, payload: bytes) -> bool:
        """Validate the mock payload shape."""
        return payload == b'{"mock": true}'

    def submit(self, payload: bytes, keys: SubmissionKeyPaths) -> SubmissionResult:
        """Return a deterministic dry-run submission result."""
        if not self.validate_payload(payload):
            raise ValueError("invalid payload")
        return SubmissionResult(
            success=True,
            subnet_id=self.subnet_id,
            status="dry_run",
            payload_hash="mock_payload_hash",
            transaction_hash="0xMOCK",
            latency_ms=1,
            metadata={"hotkey_path": str(keys.hotkey_path)},
        )


def test_base_subnet_adapter_is_abstract() -> None:
    """BaseSubnetAdapter should not be instantiable directly."""
    with pytest.raises(TypeError):
        BaseSubnetAdapter()


def test_mock_adapter_implements_required_contract() -> None:
    """Concrete adapters should expose config, catalog, payload, validation, and submit methods."""
    adapter = MockSubnetAdapter()
    payload = adapter.build_payload({"probabilities": {"above_100k": 1.0}})
    result = adapter.submit(payload, SubmissionKeyPaths(hotkey_path=Path("subnets/keys/hotkey")))

    assert adapter.subnet_id == "mock"
    assert adapter.get_event_catalog() == [{"event_id": "mock_event", "target": "NFP"}]
    assert adapter.validate_payload(payload) is True
    assert result.success is True
    assert result.subnet_id == "mock"
    assert result.status == "dry_run"
    assert result.transaction_hash == "0xMOCK"
    assert result.metadata["hotkey_path"] == "subnets/keys/hotkey"


def test_subnet_config_validates_required_fields() -> None:
    """SubnetConfig should fail fast on incomplete adapter configuration."""
    with pytest.raises(ValueError, match="subnet_id is required"):
        SubnetConfig(
            subnet_id="",
            name="Mock Subnet",
            netuid=1,
            adapter_version="0.1.0",
            events=[{"event_id": "mock"}],
            cadence={"type": "monthly"},
            scoring={"metric": "log_score"},
            network={"endpoint": "mock://localhost"},
        )

    with pytest.raises(ValueError, match="events cannot be empty"):
        SubnetConfig(
            subnet_id="mock",
            name="Mock Subnet",
            netuid=1,
            adapter_version="0.1.0",
            events=[],
            cadence={"type": "monthly"},
            scoring={"metric": "log_score"},
            network={"endpoint": "mock://localhost"},
        )


def test_submission_result_validates_operational_metadata() -> None:
    """SubmissionResult should enforce shared telemetry invariants."""
    with pytest.raises(ValueError, match="payload_hash is required"):
        SubmissionResult(success=True, subnet_id="mock", status="submitted", payload_hash="")

    with pytest.raises(ValueError, match="latency_ms must be non-negative"):
        SubmissionResult(
            success=False,
            subnet_id="mock",
            status="failed",
            payload_hash="payload_hash",
            latency_ms=-1,
        )


def test_subnet_template_contains_required_adapter_sections() -> None:
    """Template config should include the sections needed by the adapter framework."""
    template = yaml.safe_load(TEMPLATE_CONFIG.read_text(encoding="utf-8"))
    required_top_level_keys = {
        "subnet_id",
        "name",
        "netuid",
        "adapter_version",
        "events",
        "cadence",
        "scoring",
        "network",
        "submission",
        "metadata",
    }

    assert required_top_level_keys.issubset(template)
    assert template["events"][0]["event_id"]
    assert template["events"][0]["bins"]
    assert template["scoring"]["probability_tolerance"] == 0.001
    assert template["submission"]["requires_signature"] is True
