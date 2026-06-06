"""Submission window scheduling for subnet adapters."""

import re
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone, tzinfo
from typing import Any, Mapping, Optional, Sequence
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from subnets.base_adapter import BaseSubnetAdapter


WINDOW_OFFSET_PATTERN = re.compile(r"^T(?:(?P<sign>[+-])(?P<days>\d+)d)?$")


class SchedulerError(ValueError):
    """Raised when subnet scheduling configuration is invalid."""


@dataclass(frozen=True)
class SubmissionWindow:
    """A computed submission window for one subnet event."""

    subnet_id: str
    event_id: str
    event_name: str
    target: str
    opens_at: datetime
    closes_at: datetime
    release_at: datetime
    event: Mapping[str, Any]

    def contains(self, at: datetime) -> bool:
        """Return whether a timestamp falls inside this submission window."""
        normalized_at = _normalize_datetime(at)
        return self.opens_at <= normalized_at < self.closes_at


class SubnetScheduler:
    """Coordinate submission windows across configured subnet adapters."""

    def __init__(self, adapters: Sequence[BaseSubnetAdapter]) -> None:
        """Initialize scheduler with active subnet adapters."""
        if not adapters:
            raise SchedulerError("at least one adapter is required")
        self.adapters = tuple(adapters)

    def get_submission_windows(self) -> Sequence[SubmissionWindow]:
        """Return all configured submission windows in deterministic order."""
        windows = []
        for adapter in self.adapters:
            config = adapter.get_config()
            for event in adapter.get_event_catalog():
                windows.append(_build_submission_window(config.subnet_id, config.cadence, event))
        return tuple(sorted(windows, key=lambda window: (window.opens_at, window.subnet_id)))

    def get_open_windows(self, at: Optional[datetime] = None) -> Sequence[SubmissionWindow]:
        """Return submission windows open at the provided timestamp."""
        current_time = _normalize_datetime(at or datetime.now(timezone.utc))
        return tuple(
            window for window in self.get_submission_windows() if window.contains(current_time)
        )

    def should_submit(self, subnet_id: str, at: Optional[datetime] = None) -> bool:
        """Return whether a subnet has any open submission window."""
        normalized_subnet_id = subnet_id.strip()
        if not normalized_subnet_id:
            raise SchedulerError("subnet_id is required")
        return any(
            window.subnet_id == normalized_subnet_id for window in self.get_open_windows(at=at)
        )

    def get_next_submission_window(
        self, at: Optional[datetime] = None, subnet_id: Optional[str] = None
    ) -> Optional[SubmissionWindow]:
        """Return the next open or future submission window."""
        current_time = _normalize_datetime(at or datetime.now(timezone.utc))
        normalized_subnet_id = subnet_id.strip() if subnet_id is not None else None
        if subnet_id is not None and not normalized_subnet_id:
            raise SchedulerError("subnet_id is required")

        candidates = [
            window
            for window in self.get_submission_windows()
            if window.closes_at > current_time
            and (normalized_subnet_id is None or window.subnet_id == normalized_subnet_id)
        ]
        if not candidates:
            return None
        return min(
            candidates, key=lambda window: (max(window.opens_at, current_time), window.subnet_id)
        )


def _build_submission_window(
    subnet_id: str, cadence: Mapping[str, Any], event: Mapping[str, Any]
) -> SubmissionWindow:
    """Build a submission window from adapter cadence and event config."""
    event_id = _required_string(event, "event_id")
    release_at = _release_datetime(event=event, cadence=cadence)
    opens_at = release_at + _parse_window_offset(_required_string(cadence, "window_open"))
    closes_at = release_at + _parse_window_offset(_required_string(cadence, "window_close"))
    if opens_at >= closes_at:
        raise SchedulerError(f"submission window for {subnet_id}/{event_id} opens after it closes")

    return SubmissionWindow(
        subnet_id=subnet_id,
        event_id=event_id,
        event_name=str(event.get("event_name", event_id)),
        target=str(event.get("target", "")),
        opens_at=opens_at,
        closes_at=closes_at,
        release_at=release_at,
        event=event,
    )


def _release_datetime(event: Mapping[str, Any], cadence: Mapping[str, Any]) -> datetime:
    """Parse an event release timestamp with timezone information."""
    release_date = event.get("release_date")
    if release_date is None:
        raise SchedulerError("event.release_date is required")

    release_time = _parse_time(str(event.get("release_time", "00:00")))
    release_timezone = str(event.get("timezone", cadence.get("submission_timezone", "UTC")))
    tzinfo = _timezone(release_timezone)

    if isinstance(release_date, datetime):
        release_at = release_date
    elif isinstance(release_date, date):
        release_at = datetime.combine(release_date, release_time)
    elif isinstance(release_date, str):
        release_at = datetime.combine(date.fromisoformat(release_date), release_time)
    else:
        raise SchedulerError("event.release_date must be a date, datetime, or ISO date string")

    if release_at.tzinfo is None:
        return release_at.replace(tzinfo=tzinfo)
    return release_at.astimezone(tzinfo)


def _parse_window_offset(value: str) -> timedelta:
    """Parse cadence offsets such as T-5d, T-1d, T, or T+1d."""
    match = WINDOW_OFFSET_PATTERN.match(value.strip())
    if match is None:
        raise SchedulerError(f"Invalid submission window offset: {value}")
    days = int(match.group("days") or "0")
    sign = match.group("sign")
    if sign == "-":
        days = -days
    return timedelta(days=days)


def _parse_time(value: str) -> time:
    """Parse HH:MM release times."""
    try:
        return time.fromisoformat(value)
    except ValueError as exc:
        raise SchedulerError(f"Invalid release_time: {value}") from exc


def _timezone(value: str) -> tzinfo:
    """Load timezone by name, falling back only for explicit UTC."""
    if value == "UTC":
        return timezone.utc
    try:
        return ZoneInfo(value)
    except ZoneInfoNotFoundError as exc:
        raise SchedulerError(f"Invalid timezone: {value}") from exc


def _required_string(config: Mapping[str, Any], key: str) -> str:
    """Read a required non-empty string from config."""
    value = config.get(key)
    if not isinstance(value, str) or not value.strip():
        raise SchedulerError(f"{key} is required")
    return value.strip()


def _normalize_datetime(value: datetime) -> datetime:
    """Normalize naive datetimes to UTC-aware values."""
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value
