"""Health, readiness, and service status endpoints."""

from fastapi import APIRouter, Request

from app.config import ApiSettings
from app.schemas.status import HealthResponse, ReadinessResponse, ServiceStatusResponse
from app.services.artifacts import ArtifactRepository
from app.services.deployment import summarize_zone2_isolation

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
    settings = _settings(request)
    repository = _repository(request)
    artifact_status = repository.summarize_active_bundle()
    isolation_status = summarize_zone2_isolation(settings)
    ready = bool(artifact_status["active"]) and isolation_status.isolated
    blockers = list(artifact_status.get("blockers", []))
    blockers.extend(isolation_status.blockers)

    return ReadinessResponse(
        ready=ready,
        status="ready" if ready else "not_ready",
        checks={
            "active_signed_artifact": bool(artifact_status["active"]),
            "zone2_security_isolation": isolation_status.isolated,
        },
        blockers=blockers,
    )


@router.get("/status", response_model=ServiceStatusResponse)
def service_status(request: Request) -> ServiceStatusResponse:
    """Return detailed service status for dashboards and deployment checks."""
    settings = _settings(request)
    repository = _repository(request)
    isolation_status = summarize_zone2_isolation(settings)
    active_path = repository.get_active_bundle_path()
    return ServiceStatusResponse(
        service=settings.service_name,
        environment=settings.environment,
        active_subnet=settings.active_subnet,
        active_artifact_ready=repository.is_ready(),
        active_artifact_path=str(active_path) if active_path else None,
        zone2_security_isolated=isolation_status.isolated,
    )
