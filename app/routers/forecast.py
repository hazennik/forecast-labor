"""Forecast serving endpoints."""

from fastapi import APIRouter, HTTPException, Request, status

from app.schemas.forecast import ForecastRequest, ForecastResponse
from app.services.artifacts import ArtifactRepository

router = APIRouter(prefix="/forecast", tags=["forecast"])


def _repository(request: Request) -> ArtifactRepository:
    """Return the artifact repository from FastAPI state."""
    return request.app.state.artifacts


@router.post("", response_model=ForecastResponse)
def create_forecast(payload: ForecastRequest, request: Request) -> ForecastResponse:
    """Serve a forecast from a verified signed artifact.

    Phase 6A intentionally refuses to emit placeholder predictions. Inference
    should be implemented only after Zone 2 can load a signed model bundle.
    """
    artifact_status = _repository(request).summarize_active_bundle()
    if not artifact_status["active"]:
        blockers = artifact_status.get("blockers", [])
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "message": "No verified signed model artifact is available for inference",
                "target": payload.target,
                "blockers": blockers,
            },
        )

    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail={
            "message": "Signed artifact loading is available, but model inference is not wired yet",
            "target": payload.target,
        },
    )
