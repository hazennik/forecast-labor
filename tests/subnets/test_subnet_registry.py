"""Tests for subnet adapter registry and active subnet loading."""

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
from subnets.config import SubnetConfigError
from subnets.registry import (
    ActiveSubnetError,
    AdapterNotRegisteredError,
    AdapterRegistrationError,
    SubnetRegistry,
)


class ConfigBackedAdapter(BaseSubnetAdapter):
    """Minimal adapter that receives configuration from the registry."""

    def __init__(self, config: SubnetConfig) -> None:
        """Initialize the adapter with registry-loaded configuration."""
        self.config = config

    def get_config(self) -> SubnetConfig:
        """Return adapter configuration."""
        return self.config

    def get_event_catalog(self) -> Sequence[Mapping[str, Any]]:
        """Return configured events."""
        return self.config.events

    def build_payload(self, predictions: Mapping[str, Any]) -> bytes:
        """Build a deterministic payload for registry tests."""
        if not predictions:
            raise ValueError("predictions cannot be empty")
        return b'{"configured": true}'

    def validate_payload(self, payload: bytes) -> bool:
        """Validate the deterministic registry-test payload."""
        return payload == b'{"configured": true}'

    def submit(self, payload: bytes, keys: SubmissionKeyPaths) -> SubmissionResult:
        """Return a deterministic submission result."""
        if not self.validate_payload(payload):
            raise ValueError("invalid payload")
        return SubmissionResult(
            success=True,
            subnet_id=self.subnet_id,
            status="dry_run",
            payload_hash="configured_payload_hash",
            metadata={"hotkey_path": str(keys.hotkey_path)},
        )


def _write_config(config_dir: Path, subnet_id: str = "mock") -> None:
    """Write a valid registry config fixture."""
    config = {
        "subnet_id": subnet_id,
        "name": "Mock Subnet",
        "netuid": 999,
        "adapter_version": "0.1.0",
        "events": [{"event_id": "mock_event", "target": "NFP"}],
        "cadence": {"type": "monthly"},
        "scoring": {"metric": "log_score"},
        "network": {"endpoint": "mock://localhost"},
    }
    (config_dir / f"{subnet_id}.yaml").write_text(yaml.safe_dump(config), encoding="utf-8")


def test_registry_loads_registered_adapter_from_config(tmp_path: Path) -> None:
    """Registry should load config and instantiate registered adapter factories."""
    _write_config(tmp_path)
    registry = SubnetRegistry(config_dir=tmp_path)
    registry.register_adapter("mock", ConfigBackedAdapter)

    adapter = registry.get_adapter("mock")

    assert isinstance(adapter, ConfigBackedAdapter)
    assert adapter.subnet_id == "mock"
    assert adapter.get_config().name == "Mock Subnet"
    assert adapter.get_event_catalog() == [{"event_id": "mock_event", "target": "NFP"}]
    assert registry.registered_subnets() == ("mock",)


def test_registry_loads_active_adapter_from_environment(tmp_path: Path, monkeypatch) -> None:
    """Registry should resolve ACTIVE_SUBNET for runtime subnet selection."""
    _write_config(tmp_path)
    registry = SubnetRegistry(config_dir=tmp_path)
    registry.register_adapter("mock", ConfigBackedAdapter)
    monkeypatch.setenv("ACTIVE_SUBNET", "mock")

    adapter = registry.get_active_adapter()

    assert adapter.subnet_id == "mock"


def test_registry_rejects_missing_active_subnet(tmp_path: Path, monkeypatch) -> None:
    """Registry should fail fast when ACTIVE_SUBNET is unset."""
    registry = SubnetRegistry(config_dir=tmp_path)
    monkeypatch.delenv("ACTIVE_SUBNET", raising=False)

    with pytest.raises(ActiveSubnetError, match="ACTIVE_SUBNET is not set"):
        registry.get_active_adapter()


def test_registry_rejects_unregistered_adapter(tmp_path: Path) -> None:
    """Registry should not load configs for unregistered adapters."""
    _write_config(tmp_path)
    registry = SubnetRegistry(config_dir=tmp_path)

    with pytest.raises(AdapterNotRegisteredError, match="No adapter registered"):
        registry.get_adapter("mock")


def test_registry_rejects_invalid_factory_return_type(tmp_path: Path) -> None:
    """Registered factories must return BaseSubnetAdapter instances."""
    _write_config(tmp_path)
    registry = SubnetRegistry(config_dir=tmp_path)
    registry.register_adapter("mock", lambda config: object())  # type: ignore[arg-type]

    with pytest.raises(AdapterRegistrationError, match="did not return BaseSubnetAdapter"):
        registry.get_adapter("mock")


def test_registry_rejects_adapter_config_mismatch(tmp_path: Path) -> None:
    """Adapter factories should not return adapters for a different subnet ID."""
    _write_config(tmp_path, subnet_id="mock")
    _write_config(tmp_path, subnet_id="other")
    registry = SubnetRegistry(config_dir=tmp_path)
    registry.register_adapter(
        "mock", lambda config: ConfigBackedAdapter(config=load_other(tmp_path))
    )

    with pytest.raises(SubnetConfigError, match="does not match requested"):
        registry.get_adapter("mock")


def load_other(config_dir: Path) -> SubnetConfig:
    """Load the secondary config fixture for mismatch tests."""
    registry = SubnetRegistry(config_dir=config_dir)
    registry.register_adapter("other", ConfigBackedAdapter)
    return registry.get_adapter("other").get_config()
