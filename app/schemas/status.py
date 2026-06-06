"""Status and health response schemas."""

from datetime import datetime, timezone
from typing import Dict, List, Optional

from pydantic import BaseModel, Field


def utc_now() -> datetime:
    """Return the current UTC timestamp."""
    return datetime.now(timezone.utc)


class HealthResponse(BaseModel):
    """Basic liveness response."""

    status: str = Field(..., description="Service liveness status")
    service: str = Field(..., description="Service name")
    environment: str = Field(..., description="Runtime environment")
    timestamp: datetime = Field(default_factory=utc_now)


class ReadinessResponse(BaseModel):
    """Readiness response for Zone 2 inference."""

    ready: bool = Field(..., description="Whether inference can serve forecasts")
    status: str = Field(..., description="Human-readable readiness status")
    checks: Dict[str, bool] = Field(default_factory=dict)
    blockers: List[str] = Field(default_factory=list)
    timestamp: datetime = Field(default_factory=utc_now)


class ServiceStatusResponse(BaseModel):
    """Detailed API status response."""

    service: str
    environment: str
    active_subnet: str
    active_artifact_ready: bool
    active_artifact_path: Optional[str] = None
    zone2_security_isolated: bool
    rate_limit_enabled: bool
    rate_limit_requests_per_minute: int
    timestamp: datetime = Field(default_factory=utc_now)


class EndpointMetricsResponse(BaseModel):
    """Operational metrics for one API endpoint."""

    request_count: int
    status_counts: Dict[str, int]
    average_latency_ms: float
    max_latency_ms: float
    last_status_code: int


class MetricsResponse(BaseModel):
    """Operational API metrics response."""

    service: str
    environment: str
    total_requests: int
    endpoints: Dict[str, EndpointMetricsResponse]
    timestamp: datetime = Field(default_factory=utc_now)
