"""Health, readiness, and service status endpoints."""

from fastapi import APIRouter, Request

from app.config import ApiSettings
from app.schemas.status import HealthResponse, ReadinessResponse, ServiceStatusResponse
from app.services.artifacts import ArtifactRepository

router = APIRouter(tags=["status"])


def _settings(request: Request) -> ApiSettings:
    """Return application settings from FastAPI state."""
    return request.app.state.settings


def _repository(request: Request) -> ArtifactRepository:
    """Return the artifact repository from FastAPI state."""
    return request.app.state.artifacts


@router.get("/health", response_model=HealthResponse)
def health(request: Request) -> HealthResponse:
    """Return process liveness without requiring an active model artifact."""
    settings = _settings(request)
    return HealthResponse(
        status="ok",
        service=settings.service_name,
        environment=settings.environment,
    )


@router.get("/ready", response_model=ReadinessResponse)
def readiness(request: Request) -> ReadinessResponse:
    """Return whether the inference zone can serve forecasts."""
    repository = _repository(request)
    artifact_status = repository.summarize_active_bundle()
    ready = bool(artifact_status["active"])
    blockers = list(artifact_status.get("blockers", []))

    return ReadinessResponse(
        ready=ready,
        status="ready" if ready else "not_ready",
        checks={"active_signed_artifact": ready},
        blockers=blockers,
    )


@router.get("/status", response_model=ServiceStatusResponse)
def service_status(request: Request) -> ServiceStatusResponse:
    """Return detailed service status for dashboards and deployment checks."""
    settings = _settings(request)
    repository = _repository(request)
    active_path = repository.get_active_bundle_path()
    return ServiceStatusResponse(
        service=settings.service_name,
        environment=settings.environment,
        active_subnet=settings.active_subnet,
        active_artifact_ready=repository.is_ready(),
        active_artifact_path=str(active_path) if active_path else None,
    )
