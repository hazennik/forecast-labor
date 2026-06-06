"""Forecast serving endpoints."""

from fastapi import APIRouter, HTTPException, Request, status

from app.schemas.forecast import ForecastRequest, ForecastResponse
from app.services.inference import InferenceService, InferenceUnavailableError
from app.services.rate_limit import InMemoryRateLimiter

router = APIRouter(prefix="/forecast", tags=["forecast"])


def _inference(request: Request) -> InferenceService:
    """Return the inference service from FastAPI state."""
    return request.app.state.inference


def _rate_limiter(request: Request) -> InMemoryRateLimiter:
    """Return the rate limiter from FastAPI state."""
    return request.app.state.rate_limiter


@router.post("", response_model=ForecastResponse)
def create_forecast(payload: ForecastRequest, request: Request) -> ForecastResponse:
    """Serve a forecast from a verified signed artifact.

    Forecasts are produced only from a verified signed model bundle.
    """
    rate_limit = _rate_limiter(request).check(request)
    if not rate_limit.allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Forecast request rate limit exceeded",
            headers={"Retry-After": str(rate_limit.retry_after_seconds)},
        )

    try:
        return _inference(request).predict(payload)
    except InferenceUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "message": "No verified signed model artifact is available for inference",
                "target": payload.target,
                "blockers": [str(exc)],
            },
        ) from exc
