"""Base interface for subnet-specific forecast submission adapters."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence


@dataclass(frozen=True)
class SubnetConfig:
    """Runtime configuration for a subnet adapter."""

    subnet_id: str
    name: str
    netuid: int
    adapter_version: str
    events: Sequence[Mapping[str, Any]]
    cadence: Mapping[str, Any]
    scoring: Mapping[str, Any]
    network: Mapping[str, Any]
    submission: Mapping[str, Any] = field(default_factory=dict)
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Validate required adapter configuration fields."""
        if not self.subnet_id.strip():
            raise ValueError("subnet_id is required")
        if not self.name.strip():
            raise ValueError("name is required")
        if self.netuid < 0:
            raise ValueError("netuid must be non-negative")
        if not self.adapter_version.strip():
            raise ValueError("adapter_version is required")
        if not self.events:
            raise ValueError("events cannot be empty")
        if not self.cadence:
            raise ValueError("cadence cannot be empty")
        if not self.scoring:
            raise ValueError("scoring cannot be empty")
        if not self.network:
            raise ValueError("network cannot be empty")


@dataclass(frozen=True)
class SubmissionKeyPaths:
    """Filesystem paths for subnet submission keys."""

    hotkey_path: Path
    coldkey_path: Optional[Path] = None

    def __post_init__(self) -> None:
        """Validate key path configuration without reading secret material."""
        if not str(self.hotkey_path).strip():
            raise ValueError("hotkey_path is required")


@dataclass(frozen=True)
class SubmissionResult:
    """Result returned after attempting a subnet submission."""

    success: bool
    subnet_id: str
    status: str
    payload_hash: str
    submitted_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    transaction_hash: Optional[str] = None
    latency_ms: Optional[int] = None
    validator_response: Mapping[str, Any] = field(default_factory=dict)
    error_message: Optional[str] = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Validate result metadata shared by all adapters."""
        if not self.subnet_id.strip():
            raise ValueError("subnet_id is required")
        if not self.status.strip():
            raise ValueError("status is required")
        if not self.payload_hash.strip():
            raise ValueError("payload_hash is required")
        if self.latency_ms is not None and self.latency_ms < 0:
            raise ValueError("latency_ms must be non-negative")


class BaseSubnetAdapter(ABC):
    """Abstract interface that every subnet adapter must implement."""

    @abstractmethod
    def get_config(self) -> SubnetConfig:
        """Return the adapter's validated subnet configuration."""

    @abstractmethod
    def get_event_catalog(self) -> Sequence[Mapping[str, Any]]:
        """Return subnet-specific event definitions."""

    @abstractmethod
    def build_payload(self, predictions: Mapping[str, Any]) -> bytes:
        """Convert model predictions into the subnet-specific payload format."""

    @abstractmethod
    def validate_payload(self, payload: bytes) -> bool:
        """Validate a payload before submission."""

    @abstractmethod
    def submit(self, payload: bytes, keys: SubmissionKeyPaths) -> SubmissionResult:
        """Submit a validated payload to the subnet."""

    @property
    def subnet_id(self) -> str:
        """Return the adapter's subnet identifier."""
        return self.get_config().subnet_id
