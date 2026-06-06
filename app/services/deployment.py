"""Deployment boundary checks for the Zone 2 inference service."""

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional, Tuple

from app.config import ApiSettings


FORBIDDEN_ZONE2_ROOTS: Tuple[Path, ...] = (
    Path("data"),
    Path("zone1"),
    Path("etl"),
    Path("features"),
    Path("models_src"),
    Path("backtests"),
    Path("scripts"),
)


@dataclass(frozen=True)
class IsolationStatus:
    """Result of a Zone 2 deployment isolation check."""

    isolated: bool
    blockers: List[str]


def summarize_zone2_isolation(settings: ApiSettings) -> IsolationStatus:
    """Validate that Zone 2 runtime paths do not point at forbidden project roots."""
    blockers: List[str] = []
    forbidden_roots = tuple(_resolve_path(path) for path in FORBIDDEN_ZONE2_ROOTS)
    configured_paths = (
        ("artifact_dir", settings.artifact_dir),
        ("extraction_dir", settings.extraction_dir),
        ("active_bundle_path", settings.active_bundle_path),
    )

    for role, configured_path in configured_paths:
        if configured_path is None:
            continue
        resolved_path = _resolve_path(configured_path)
        forbidden_role = _matching_forbidden_role(resolved_path, forbidden_roots)
        if forbidden_role is not None:
            blockers.append(
                f"Zone 2 {role} must not point inside forbidden project root: {forbidden_role}"
            )

    return IsolationStatus(isolated=not blockers, blockers=blockers)


def _resolve_path(path: Path) -> Path:
    """Resolve a path without requiring it to exist."""
    return path.expanduser().resolve(strict=False)


def _matching_forbidden_role(path: Path, forbidden_roots: Iterable[Path]) -> Optional[str]:
    """Return the forbidden root name containing a path, if any."""
    for forbidden_root in forbidden_roots:
        if path == forbidden_root or forbidden_root in path.parents:
            return forbidden_root.name
    return None
