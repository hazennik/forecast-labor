"""In-process API metrics for Phase 6A operational visibility."""

from dataclasses import dataclass, field
from threading import Lock
from typing import Dict


@dataclass
class EndpointMetrics:
    """Mutable aggregate metrics for one HTTP method and path."""

    request_count: int = 0
    status_counts: Dict[str, int] = field(default_factory=dict)
    total_latency_ms: float = 0.0
    max_latency_ms: float = 0.0
    last_status_code: int = 0

    def record(self, status_code: int, latency_ms: float) -> None:
        """Record one completed request."""
        status_key = str(status_code)
        self.request_count += 1
        self.status_counts[status_key] = self.status_counts.get(status_key, 0) + 1
        self.total_latency_ms += latency_ms
        self.max_latency_ms = max(self.max_latency_ms, latency_ms)
        self.last_status_code = status_code

    def snapshot(self) -> Dict[str, object]:
        """Return a serializable metrics snapshot."""
        average_latency_ms = (
            self.total_latency_ms / self.request_count if self.request_count else 0.0
        )
        return {
            "request_count": self.request_count,
            "status_counts": dict(self.status_counts),
            "average_latency_ms": round(average_latency_ms, 3),
            "max_latency_ms": round(self.max_latency_ms, 3),
            "last_status_code": self.last_status_code,
        }


class ApiMetricsRecorder:
    """Thread-safe in-memory metrics recorder for a single API process."""

    def __init__(self) -> None:
        """Initialize the recorder."""
        self._lock = Lock()
        self._endpoints: Dict[str, EndpointMetrics] = {}
        self._total_requests = 0

    def record(self, method: str, path: str, status_code: int, latency_ms: float) -> None:
        """Record a completed HTTP request."""
        endpoint_key = f"{method.upper()} {path}"
        with self._lock:
            metrics = self._endpoints.setdefault(endpoint_key, EndpointMetrics())
            metrics.record(status_code=status_code, latency_ms=latency_ms)
            self._total_requests += 1

    def snapshot(self) -> Dict[str, object]:
        """Return a serializable snapshot of all collected metrics."""
        with self._lock:
            return {
                "total_requests": self._total_requests,
                "endpoints": {
                    endpoint: metrics.snapshot()
                    for endpoint, metrics in sorted(self._endpoints.items())
                },
            }
