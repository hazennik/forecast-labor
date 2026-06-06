"""FastAPI entrypoint for forecast serving and deployment health checks."""

from typing import Optional

from fastapi import FastAPI

from app.config import ApiSettings
from app.routers import artifacts, forecast, status
from app.services.artifacts import ArtifactRepository
from app.services.inference import InferenceService
from app.services.rate_limit import InMemoryRateLimiter


def create_app(settings: Optional[ApiSettings] = None) -> FastAPI:
    """Create and configure the FastAPI application."""
    resolved_settings = settings or ApiSettings.from_env()
    app = FastAPI(
        title="Forecast Labor API",
        description="Forecast serving and Phase 6A deployment boundary API.",
        version="0.1.0",
    )
    app.state.settings = resolved_settings
    app.state.artifacts = ArtifactRepository(resolved_settings)
    app.state.inference = InferenceService(app.state.artifacts)
    app.state.rate_limiter = InMemoryRateLimiter(resolved_settings)
    app.include_router(status.router)
    app.include_router(artifacts.router)
    app.include_router(forecast.router)
    return app


app = create_app()
