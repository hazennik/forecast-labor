"""Runtime configuration for the forecast serving API."""

from dataclasses import dataclass
from pathlib import Path
from typing import Optional
import os


@dataclass(frozen=True)
class ApiSettings:
    """Configuration values for the FastAPI serving surface.

    The defaults are safe for local development and Zone 2 inference: no forecast
    is served unless an explicit signed artifact bundle is available.
    """

    environment: str = "local"
    service_name: str = "forecast-labor-api"
    active_subnet: str = "sn41"
    artifact_dir: Path = Path("zone2/runner/artifacts")
    extraction_dir: Path = Path("zone2/runner/extracted")
    active_bundle_path: Optional[Path] = None
    api_key: Optional[str] = None

    @classmethod
    def from_env(cls) -> "ApiSettings":
        """Build settings from environment variables."""
        active_bundle = os.getenv("ACTIVE_MODEL_BUNDLE")
        return cls(
            environment=os.getenv("ENVIRONMENT", "local"),
            service_name=os.getenv("API_SERVICE_NAME", "forecast-labor-api"),
            active_subnet=os.getenv("ACTIVE_SUBNET", "sn41"),
            artifact_dir=Path(os.getenv("ZONE2_ARTIFACT_DIR", "zone2/runner/artifacts")),
            extraction_dir=Path(os.getenv("ZONE2_EXTRACT_DIR", "zone2/runner/extracted")),
            active_bundle_path=Path(active_bundle) if active_bundle else None,
            api_key=os.getenv("ZONE2_API_KEY") or os.getenv("API_KEY"),
        )
