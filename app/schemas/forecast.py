"""Forecast request and response schemas."""

from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, validator


def utc_now() -> datetime:
    """Return the current UTC timestamp."""
    return datetime.now(timezone.utc)


class ForecastRequest(BaseModel):
    """Request payload for serving a forecast from a signed artifact."""

    target: str = Field(..., min_length=1, description="Forecast target, e.g. nfp")
    vintage_date: date = Field(..., description="Vintage date used for inference")
    horizon_months: int = Field(1, ge=1, le=12, description="Forecast horizon in months")
    as_of: Optional[datetime] = Field(
        None,
        description="Optional request timestamp representing the information cutoff",
    )
    features: Dict[str, float] = Field(
        default_factory=dict,
        description="Optional precomputed feature values for inference",
    )

    @validator("target")
    def normalize_target(cls, value: str) -> str:
        """Normalize target identifiers while preserving explicit validation."""
        normalized = value.strip().lower()
        if not normalized:
            raise ValueError("target must not be empty")
        return normalized


class ForecastInterval(BaseModel):
    """Prediction interval for a forecast."""

    level: float = Field(..., gt=0.0, lt=1.0)
    lower: float
    upper: float


class ForecastResponse(BaseModel):
    """Forecast response returned by a loaded signed artifact."""

    target: str
    vintage_date: date
    prediction: float
    intervals: List[ForecastInterval] = Field(default_factory=list)
    probabilities: Dict[str, float] = Field(default_factory=dict)
    model_id: str
    artifact_hash: str
    generated_at: datetime = Field(default_factory=utc_now)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ForecastUnavailableResponse(BaseModel):
    """Structured error body when no verified artifact can serve forecasts."""

    detail: str
    blockers: List[str] = Field(default_factory=list)
    timestamp: datetime = Field(default_factory=utc_now)
