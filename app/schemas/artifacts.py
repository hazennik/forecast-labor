"""Artifact status schemas for the Zone 2 serving boundary."""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


def utc_now() -> datetime:
    """Return the current UTC timestamp."""
    return datetime.now(timezone.utc)


class ArtifactSummary(BaseModel):
    """Summary of a signed model artifact bundle."""

    path: str
    exists: bool
    manifest_present: bool
    verified: bool
    metadata: Dict[str, Any] = Field(default_factory=dict)
    extract_dir: Optional[str] = None
    artifacts: List[str] = Field(default_factory=list)
    issues: List[str] = Field(default_factory=list)


class ActiveArtifactResponse(BaseModel):
    """Response describing the active serving artifact."""

    active: bool
    artifact: Optional[ArtifactSummary] = None
    timestamp: datetime = Field(default_factory=utc_now)
