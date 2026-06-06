"""Tests for subnet adapter configuration loading."""

from pathlib import Path

import pytest
import yaml

from subnets.config import SubnetConfigError, load_subnet_config, subnet_config_from_mapping


def _write_config(config_dir: Path, subnet_id: str = "mock", filename: str = "mock") -> Path:
    """Write a valid subnet config fixture."""
    config = {
        "subnet_id": subnet_id,
        "name": "Mock Subnet",
        "netuid": 999,
        "adapter_version": "0.1.0",
        "events": [{"event_id": "mock_event", "target": "NFP"}],
        "cadence": {"type": "monthly"},
        "scoring": {"metric": "log_score"},
        "network": {"endpoint": "mock://localhost"},
        "submission": {"payload_format": "json"},
        "metadata": {"owner": "tests"},
    }
    config_path = config_dir / f"{filename}.yaml"
    config_path.write_text(yaml.safe_dump(config), encoding="utf-8")
    return config_path


def test_load_subnet_config_reads_valid_yaml(tmp_path: Path) -> None:
    """Config loader should parse YAML into a validated SubnetConfig."""
    _write_config(tmp_path)

    config = load_subnet_config("mock", config_dir=tmp_path)

    assert config.subnet_id == "mock"
    assert config.name == "Mock Subnet"
    assert config.netuid == 999
    assert config.adapter_version == "0.1.0"
    assert config.events == [{"event_id": "mock_event", "target": "NFP"}]
    assert config.submission == {"payload_format": "json"}
    assert config.metadata == {"owner": "tests"}


def test_load_subnet_config_rejects_missing_file(tmp_path: Path) -> None:
    """Config loader should fail fast when a subnet file is absent."""
    with pytest.raises(SubnetConfigError, match="Subnet config not found"):
        load_subnet_config("missing", config_dir=tmp_path)


def test_load_subnet_config_rejects_subnet_id_mismatch(tmp_path: Path) -> None:
    """Config files should not be loaded for the wrong subnet ID."""
    _write_config(tmp_path, subnet_id="other", filename="mock")

    with pytest.raises(SubnetConfigError, match="does not match requested"):
        load_subnet_config("mock", config_dir=tmp_path)


def test_subnet_config_from_mapping_rejects_invalid_types() -> None:
    """Parsed YAML must contain the required config sections with expected types."""
    raw_config = {
        "subnet_id": "mock",
        "name": "Mock Subnet",
        "netuid": "999",
        "adapter_version": "0.1.0",
        "events": [{"event_id": "mock_event"}],
        "cadence": {"type": "monthly"},
        "scoring": {"metric": "log_score"},
        "network": {"endpoint": "mock://localhost"},
    }

    with pytest.raises(SubnetConfigError, match="netuid must be an integer"):
        subnet_config_from_mapping(raw_config)


def test_subnet_config_from_mapping_rejects_non_mapping_root() -> None:
    """Config roots must be YAML mappings."""
    with pytest.raises(SubnetConfigError, match="subnet config must be a mapping"):
        subnet_config_from_mapping(["not", "a", "mapping"])
