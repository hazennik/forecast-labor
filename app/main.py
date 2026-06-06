"""FastAPI entrypoint for forecast serving and deployment health checks."""

from time import perf_counter
from typing import Awaitable, Callable, Optional
from uuid import uuid4

from fastapi import FastAPI, Request, Response

from app.config import ApiSettings
from app.routers import artifacts, forecast, status
from app.services.artifacts import ArtifactRepository
from app.services.inference import InferenceService
from app.services.metrics import ApiMetricsRecorder
from app.services.rate_limit import InMemoryRateLimiter

REQUEST_ID_HEADER = "X-Request-ID"


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
        """Record request metrics and attach correlation IDs to responses."""
        start_time = perf_counter()
        status_code = 500
        request_id = _request_id(request)
        request.state.request_id = request_id
        try:
            response = await call_next(request)
            status_code = response.status_code
            response.headers[REQUEST_ID_HEADER] = request_id
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


def _request_id(request: Request) -> str:
    """Return the incoming request ID or generate a new correlation ID."""
    request_id = request.headers.get(REQUEST_ID_HEADER, "").strip()
    return request_id or str(uuid4())


app = create_app()
