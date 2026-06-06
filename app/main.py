"""FastAPI entrypoint for forecast serving and deployment health checks."""

from time import perf_counter
from typing import Awaitable, Callable, Optional

from fastapi import FastAPI, Request, Response

from app.config import ApiSettings
from app.routers import artifacts, forecast, status
from app.services.artifacts import ArtifactRepository
from app.services.inference import InferenceService
from app.services.metrics import ApiMetricsRecorder
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
    app.state.metrics = ApiMetricsRecorder()

    @app.middleware("http")
    async def record_request_metrics(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        """Record request counts, status codes, and latency for operational visibility."""
        start_time = perf_counter()
        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
            return response
        finally:
            latency_ms = (perf_counter() - start_time) * 1000
            app.state.metrics.record(
                method=request.method,
                path=request.url.path,
                status_code=status_code,
                latency_ms=latency_ms,
            )

    app.include_router(status.router)
    app.include_router(artifacts.router)
    app.include_router(forecast.router)
    return app


app = create_app()
