"""SN41 event catalog helpers."""

from typing import Any, Mapping, Sequence

from subnets.base_adapter import SubnetConfig


SN41_EVENT_CATALOG = "sn41"


def get_sn41_event_catalog(config: SubnetConfig) -> Sequence[Mapping[str, Any]]:
    """Return SN41 events from validated adapter configuration."""
    if config.subnet_id != SN41_EVENT_CATALOG:
        raise ValueError("SN41 event catalog requires sn41 config")
    return config.events
