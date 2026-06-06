"""Artifact inspection endpoints."""

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import FileResponse

from app.schemas.artifacts import ActiveArtifactResponse
from app.security import require_api_key
from app.services.artifacts import ArtifactRepository

router = APIRouter(prefix="/artifacts", tags=["artifacts"])


def _repository(request: Request) -> ArtifactRepository:
    """Return the artifact repository from FastAPI state."""
    return request.app.state.artifacts


@router.get(
    "/active",
    response_model=ActiveArtifactResponse,
    dependencies=[Depends(require_api_key)],
)
def active_artifact(request: Request) -> ActiveArtifactResponse:
    """Return the active signed artifact bundle metadata if one is available."""
    status = _repository(request).summarize_active_bundle()
    return ActiveArtifactResponse(active=bool(status["active"]), artifact=status["artifact"])


@router.get(
    "/active/export",
    response_class=FileResponse,
    dependencies=[Depends(require_api_key)],
)
def export_active_artifact(request: Request) -> FileResponse:
    """Export the active verified signed artifact bundle."""
    repository = _repository(request)
    artifact_status = repository.summarize_active_bundle()
    if not artifact_status["active"]:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "message": "No verified signed model artifact is available for export",
                "blockers": artifact_status.get("blockers", []),
            },
        )

    bundle_path = repository.get_active_bundle_path()
    if bundle_path is None or not bundle_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Active signed model bundle was not found",
        )

    return FileResponse(
        path=bundle_path,
        media_type="application/zip",
        filename=bundle_path.name,
    )
