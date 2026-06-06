"""Configuration loading utilities for subnet adapters."""

from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

import yaml

from subnets.base_adapter import SubnetConfig


DEFAULT_CONFIG_DIR = Path("configs") / "subnets"


class SubnetConfigError(ValueError):
    """Raised when subnet configuration is missing or invalid."""


def load_subnet_config(subnet_id: str, config_dir: Path = DEFAULT_CONFIG_DIR) -> SubnetConfig:
    """Load a subnet configuration file by subnet ID.

    Args:
        subnet_id: Subnet identifier, such as ``sn41``.
        config_dir: Directory containing ``<subnet_id>.yaml`` files.

    Returns:
        Validated subnet configuration.

    Raises:
        SubnetConfigError: If the config file is missing, malformed, or mismatched.
    """
    normalized_subnet_id = subnet_id.strip()
    if not normalized_subnet_id:
        raise SubnetConfigError("subnet_id is required")

    config_path = config_dir / f"{normalized_subnet_id}.yaml"
    if not config_path.exists():
        raise SubnetConfigError(f"Subnet config not found: {config_path}")

    try:
        raw_config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise SubnetConfigError(f"Invalid YAML in subnet config: {config_path}") from exc

    config = subnet_config_from_mapping(raw_config, source=config_path)
    if config.subnet_id != normalized_subnet_id:
        raise SubnetConfigError(
            f"Config subnet_id {config.subnet_id!r} does not match requested "
            f"{normalized_subnet_id!r}"
        )
    return config


def subnet_config_from_mapping(raw_config: object, source: Optional[Path] = None) -> SubnetConfig:
    """Create a validated ``SubnetConfig`` from parsed YAML data."""
    source_label = str(source) if source is not None else "subnet config"
    config = _expect_mapping(raw_config, source_label)

    try:
        return SubnetConfig(
            subnet_id=_expect_string(config, "subnet_id", source_label),
            name=_expect_string(config, "name", source_label),
            netuid=_expect_int(config, "netuid", source_label),
            adapter_version=_expect_string(config, "adapter_version", source_label),
            events=_expect_sequence_of_mappings(config, "events", source_label),
            cadence=_expect_mapping(config.get("cadence"), f"{source_label}.cadence"),
            scoring=_expect_mapping(config.get("scoring"), f"{source_label}.scoring"),
            network=_expect_mapping(config.get("network"), f"{source_label}.network"),
            submission=_optional_mapping(config.get("submission"), f"{source_label}.submission"),
            metadata=_optional_mapping(config.get("metadata"), f"{source_label}.metadata"),
        )
    except ValueError as exc:
        raise SubnetConfigError(str(exc)) from exc


def _expect_mapping(value: object, label: str) -> Mapping[str, Any]:
    """Validate that a parsed YAML value is a mapping."""
    if not isinstance(value, Mapping):
        raise SubnetConfigError(f"{label} must be a mapping")
    return value


def _optional_mapping(value: object, label: str) -> Mapping[str, Any]:
    """Validate an optional mapping value."""
    if value is None:
        return {}
    return _expect_mapping(value, label)


def _expect_string(config: Mapping[str, Any], key: str, source_label: str) -> str:
    """Read a required string value from a mapping."""
    value = config.get(key)
    if not isinstance(value, str):
        raise SubnetConfigError(f"{source_label}.{key} must be a string")
    return value


def _expect_int(config: Mapping[str, Any], key: str, source_label: str) -> int:
    """Read a required integer value from a mapping."""
    value = config.get(key)
    if not isinstance(value, int) or isinstance(value, bool):
        raise SubnetConfigError(f"{source_label}.{key} must be an integer")
    return value


def _expect_sequence_of_mappings(
    config: Mapping[str, Any], key: str, source_label: str
) -> Sequence[Mapping[str, Any]]:
    """Read a required sequence of mapping values from a mapping."""
    value = config.get(key)
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise SubnetConfigError(f"{source_label}.{key} must be a sequence")
    if not all(isinstance(item, Mapping) for item in value):
        raise SubnetConfigError(f"{source_label}.{key} must contain mappings")
    return value
