"""Read-only artifact discovery for Zone 2 inference."""

from pathlib import Path
from typing import Any, Dict, List, Optional
import json
import zipfile

from loguru import logger

from app.config import ApiSettings


class ArtifactRepository:
    """Inspect signed model bundles available to the inference zone."""

    def __init__(self, settings: ApiSettings) -> None:
        """Initialize repository with runtime settings."""
        self.settings = settings

    def get_active_bundle_path(self) -> Optional[Path]:
        """Return the explicit or latest active bundle path, if one is available."""
        if self.settings.active_bundle_path is not None:
            return self.settings.active_bundle_path

        artifact_dir = self.settings.artifact_dir
        if not artifact_dir.exists():
            return None

        bundles = sorted(
            artifact_dir.glob("*.zip"),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )
        return bundles[0] if bundles else None

    def summarize_active_bundle(self) -> Dict[str, Any]:
        """Return verification-oriented metadata for the active signed bundle."""
        bundle_path = self.get_active_bundle_path()
        if bundle_path is None:
            return {
                "active": False,
                "artifact": None,
                "blockers": ["No active signed model bundle configured or found"],
            }

        issues: List[str] = []
        metadata: Dict[str, Any] = {}
        exists = bundle_path.exists()
        manifest_present = False

        if not exists:
            issues.append(f"Active model bundle does not exist: {bundle_path}")
        elif not zipfile.is_zipfile(bundle_path):
            issues.append(f"Active model bundle is not a valid zip file: {bundle_path}")
        else:
            try:
                with zipfile.ZipFile(bundle_path, "r") as archive:
                    manifest_present = "manifest.json" in archive.namelist()
                    if manifest_present:
                        metadata = json.loads(archive.read("manifest.json").decode("utf-8"))
                    else:
                        issues.append("Signed bundle is missing manifest.json")
            except (OSError, json.JSONDecodeError, zipfile.BadZipFile) as exc:
                logger.error("artifact_manifest_read_failed", path=str(bundle_path), error=str(exc))
                issues.append(f"Failed to read active model bundle manifest: {exc}")

        verified = exists and manifest_present and not issues
        return {
            "active": verified,
            "artifact": {
                "path": str(bundle_path),
                "exists": exists,
                "manifest_present": manifest_present,
                "verified": verified,
                "metadata": metadata,
                "issues": issues,
            },
            "blockers": issues,
        }

    def is_ready(self) -> bool:
        """Return whether the active artifact is ready for inference."""
        return bool(self.summarize_active_bundle()["active"])
