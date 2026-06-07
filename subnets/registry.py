"""Adapter registry and active-subnet loading utilities."""

import os
from pathlib import Path
from typing import Callable, Dict, Sequence

from subnets.base_adapter import BaseSubnetAdapter, SubnetConfig
from subnets.config import DEFAULT_CONFIG_DIR, SubnetConfigError, load_subnet_config
from subnets.sn41.adapter import SN41Adapter


AdapterFactory = Callable[[SubnetConfig], BaseSubnetAdapter]


class AdapterRegistrationError(ValueError):
    """Raised when an adapter factory cannot be registered."""


class AdapterNotRegisteredError(KeyError):
    """Raised when a requested subnet has no registered adapter factory."""


class ActiveSubnetError(ValueError):
    """Raised when active subnet selection is missing or invalid."""


class SubnetRegistry:
    """Registry for loading subnet adapters from configuration."""

    def __init__(
        self,
        config_dir: Path = DEFAULT_CONFIG_DIR,
        active_subnet_env: str = "ACTIVE_SUBNET",
    ) -> None:
        """Initialize an empty registry.

        Args:
            config_dir: Directory containing ``<subnet_id>.yaml`` configuration files.
            active_subnet_env: Environment variable used by ``get_active_adapter``.
        """
        self.config_dir = config_dir
        self.active_subnet_env = active_subnet_env
        self._factories: Dict[str, AdapterFactory] = {}

    def register_adapter(self, subnet_id: str, factory: AdapterFactory) -> None:
        """Register an adapter factory for a subnet ID."""
        normalized_subnet_id = subnet_id.strip()
        if not normalized_subnet_id:
            raise AdapterRegistrationError("subnet_id is required")
        if not callable(factory):
            raise AdapterRegistrationError("factory must be callable")
        self._factories[normalized_subnet_id] = factory

    def get_adapter(self, subnet_id: str) -> BaseSubnetAdapter:
        """Load a configured adapter for the requested subnet ID."""
        normalized_subnet_id = subnet_id.strip()
        if not normalized_subnet_id:
            raise AdapterNotRegisteredError("subnet_id is required")
        factory = self._factories.get(normalized_subnet_id)
        if factory is None:
            raise AdapterNotRegisteredError(f"No adapter registered for subnet: {subnet_id}")

        config = load_subnet_config(normalized_subnet_id, config_dir=self.config_dir)
        adapter = factory(config)
        if not isinstance(adapter, BaseSubnetAdapter):
            raise AdapterRegistrationError(
                f"Adapter factory for {normalized_subnet_id!r} did not return BaseSubnetAdapter"
            )
        if adapter.subnet_id != normalized_subnet_id:
            raise SubnetConfigError(
                f"Adapter subnet_id {adapter.subnet_id!r} does not match requested "
                f"{normalized_subnet_id!r}"
            )
        return adapter

    def get_active_adapter(self) -> BaseSubnetAdapter:
        """Load the adapter selected by the active subnet environment variable."""
        active_subnet = os.environ.get(self.active_subnet_env, "").strip()
        if not active_subnet:
            raise ActiveSubnetError(f"{self.active_subnet_env} is not set")
        return self.get_adapter(active_subnet)

    def registered_subnets(self) -> Sequence[str]:
        """Return registered subnet IDs in deterministic order."""
        return tuple(sorted(self._factories))


def create_default_registry(
    config_dir: Path = DEFAULT_CONFIG_DIR,
    active_subnet_env: str = "ACTIVE_SUBNET",
) -> SubnetRegistry:
    """Create a registry with built-in subnet adapters registered."""
    registry = SubnetRegistry(config_dir=config_dir, active_subnet_env=active_subnet_env)
    registry.register_adapter("sn41", SN41Adapter)
    return registry
