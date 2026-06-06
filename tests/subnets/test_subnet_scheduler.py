"""Tests for subnet submission window scheduling."""

from datetime import datetime, timezone
from typing import Any, Mapping, Sequence

import pytest

from subnets.base_adapter import (
    BaseSubnetAdapter,
    SubmissionKeyPaths,
    SubmissionResult,
    SubnetConfig,
)
from subnets.scheduler import SchedulerError, SubnetScheduler


class ScheduledAdapter(BaseSubnetAdapter):
    """Minimal adapter for scheduler tests."""

    def __init__(self, config: SubnetConfig) -> None:
        """Initialize adapter with deterministic config."""
        self.config = config

    def get_config(self) -> SubnetConfig:
        """Return scheduler test config."""
        return self.config

    def get_event_catalog(self) -> Sequence[Mapping[str, Any]]:
        """Return configured scheduler test events."""
        return self.config.events

    def build_payload(self, predictions: Mapping[str, Any]) -> bytes:
        """Build a deterministic test payload."""
        if not predictions:
            raise ValueError("predictions cannot be empty")
        return b"{}"

    def validate_payload(self, payload: bytes) -> bool:
        """Validate deterministic test payload."""
        return payload == b"{}"

    def submit(self, payload: bytes, keys: SubmissionKeyPaths) -> SubmissionResult:
        """Return deterministic dry-run result."""
        return SubmissionResult(
            success=True,
            subnet_id=self.subnet_id,
            status="dry_run",
            payload_hash="scheduler_payload_hash",
            metadata={"hotkey_path": str(keys.hotkey_path)},
        )


def _adapter(
    subnet_id: str = "mock",
    release_date: str = "2026-01-10",
    window_open: str = "T-5d",
    window_close: str = "T-1d",
) -> ScheduledAdapter:
    """Create a configured scheduler adapter."""
    return ScheduledAdapter(
        SubnetConfig(
            subnet_id=subnet_id,
            name=f"{subnet_id} Subnet",
            netuid=999,
            adapter_version="0.1.0",
            events=[
                {
                    "event_id": f"{subnet_id}_event",
                    "event_name": f"{subnet_id} Event",
                    "target": "NFP",
                    "release_date": release_date,
                    "release_time": "08:30",
                    "timezone": "UTC",
                }
            ],
            cadence={
                "type": "monthly",
                "window_open": window_open,
                "window_close": window_close,
                "submission_timezone": "UTC",
            },
            scoring={"metric": "log_score"},
            network={"endpoint": "mock://localhost"},
        )
    )


def test_scheduler_computes_submission_windows_from_cadence() -> None:
    """Scheduler should convert T-relative cadence into concrete windows."""
    scheduler = SubnetScheduler([_adapter()])

    (window,) = scheduler.get_submission_windows()

    assert window.subnet_id == "mock"
    assert window.event_id == "mock_event"
    assert window.event_name == "mock Event"
    assert window.target == "NFP"
    assert window.release_at == datetime(2026, 1, 10, 8, 30, tzinfo=timezone.utc)
    assert window.opens_at == datetime(2026, 1, 5, 8, 30, tzinfo=timezone.utc)
    assert window.closes_at == datetime(2026, 1, 9, 8, 30, tzinfo=timezone.utc)


def test_scheduler_reports_open_windows_and_submit_status() -> None:
    """Scheduler should report when a subnet is inside its submission window."""
    scheduler = SubnetScheduler([_adapter()])
    inside_window = datetime(2026, 1, 7, 12, 0, tzinfo=timezone.utc)
    after_window = datetime(2026, 1, 9, 9, 0, tzinfo=timezone.utc)

    open_windows = scheduler.get_open_windows(at=inside_window)

    assert len(open_windows) == 1
    assert scheduler.should_submit("mock", at=inside_window) is True
    assert scheduler.should_submit("mock", at=after_window) is False


def test_scheduler_returns_next_window_across_subnets() -> None:
    """Scheduler should select the next open or future window across adapters."""
    scheduler = SubnetScheduler(
        [
            _adapter(subnet_id="later", release_date="2026-02-10"),
            _adapter(subnet_id="earlier", release_date="2026-01-10"),
        ]
    )

    next_window = scheduler.get_next_submission_window(
        at=datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc)
    )
    later_window = scheduler.get_next_submission_window(
        at=datetime(2026, 1, 10, 0, 0, tzinfo=timezone.utc), subnet_id="later"
    )

    assert next_window is not None
    assert next_window.subnet_id == "earlier"
    assert later_window is not None
    assert later_window.subnet_id == "later"


def test_scheduler_returns_none_after_all_windows_close() -> None:
    """Scheduler should return None when no current or future windows remain."""
    scheduler = SubnetScheduler([_adapter()])

    next_window = scheduler.get_next_submission_window(
        at=datetime(2026, 1, 12, 0, 0, tzinfo=timezone.utc)
    )

    assert next_window is None


def test_scheduler_rejects_invalid_window_order() -> None:
    """Scheduler should fail when a window closes before it opens."""
    scheduler = SubnetScheduler([_adapter(window_open="T-1d", window_close="T-5d")])

    with pytest.raises(SchedulerError, match="opens after it closes"):
        scheduler.get_submission_windows()


def test_scheduler_rejects_missing_adapters() -> None:
    """Scheduler should require at least one adapter."""
    with pytest.raises(SchedulerError, match="at least one adapter is required"):
        SubnetScheduler([])


def test_scheduler_rejects_invalid_offset() -> None:
    """Scheduler should validate cadence offset syntax."""
    scheduler = SubnetScheduler([_adapter(window_open="five_days_before")])

    with pytest.raises(SchedulerError, match="Invalid submission window offset"):
        scheduler.get_submission_windows()
