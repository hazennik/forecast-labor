"""In-process request rate limiting for operational API hardening."""

from collections import defaultdict, deque
from dataclasses import dataclass
from time import monotonic
from typing import Callable, Deque, DefaultDict

from fastapi import Request

from app.config import ApiSettings


@dataclass(frozen=True)
class RateLimitDecision:
    """Decision returned by the rate limiter for a request."""

    allowed: bool
    retry_after_seconds: int


class InMemoryRateLimiter:
    """Sliding-window in-memory rate limiter for a single API process."""

    def __init__(
        self,
        settings: ApiSettings,
        clock: Callable[[], float] = monotonic,
        window_seconds: int = 60,
    ) -> None:
        """Initialize the limiter with runtime settings."""
        self.settings = settings
        self.clock = clock
        self.window_seconds = window_seconds
        self._requests: DefaultDict[str, Deque[float]] = defaultdict(deque)

    def check(self, request: Request) -> RateLimitDecision:
        """Return whether a request should be accepted."""
        if not self.settings.rate_limit_enabled:
            return RateLimitDecision(allowed=True, retry_after_seconds=0)

        now = self.clock()
        key = self._request_key(request)
        history = self._requests[key]
        while history and now - history[0] >= self.window_seconds:
            history.popleft()

        limit = self.settings.rate_limit_requests_per_minute
        if len(history) >= limit:
            retry_after = max(1, int(self.window_seconds - (now - history[0])))
            return RateLimitDecision(allowed=False, retry_after_seconds=retry_after)

        history.append(now)
        return RateLimitDecision(allowed=True, retry_after_seconds=0)

    @staticmethod
    def _request_key(request: Request) -> str:
        """Build a stable rate limit key from client and path."""
        client_host = request.client.host if request.client else "unknown"
        return f"{client_host}:{request.url.path}"
