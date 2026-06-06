"""Artifact inspection endpoints."""

from fastapi import APIRouter, Request

from app.schemas.artifacts import ActiveArtifactResponse
from app.services.artifacts import ArtifactRepository

router = APIRouter(prefix="/artifacts", tags=["artifacts"])


def _repository(request: Request) -> ArtifactRepository:
    """Return the artifact repository from FastAPI state."""
    return request.app.state.artifacts


@router.get("/active", response_model=ActiveArtifactResponse)
def active_artifact(request: Request) -> ActiveArtifactResponse:
    """Return the active signed artifact bundle metadata if one is available."""
    status = _repository(request).summarize_active_bundle()
    return ActiveArtifactResponse(active=bool(status["active"]), artifact=status["artifact"])
