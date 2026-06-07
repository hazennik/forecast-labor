"""SN41 adapter implementation for offline payload validation and dry runs."""

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Mapping, Sequence

from subnets.base_adapter import (
    BaseSubnetAdapter,
    SubmissionKeyPaths,
    SubmissionResult,
    SubnetConfig,
)
from subnets.scoring_shim import SubnetScoringShim
from subnets.sn41.event_catalog import get_sn41_event_catalog


class SN41Adapter(BaseSubnetAdapter):
    """SN41 adapter with config-driven payload building and dry-run submission."""

    def __init__(self, config: SubnetConfig) -> None:
        """Initialize the SN41 adapter."""
        if config.subnet_id != "sn41":
            raise ValueError("SN41Adapter requires sn41 config")
        self.config = config
        self.scoring = SubnetScoringShim(config)

    def get_config(self) -> SubnetConfig:
        """Return the SN41 adapter configuration."""
        return self.config

    def get_event_catalog(self) -> Sequence[Mapping[str, Any]]:
        """Return configured SN41 event definitions."""
        return get_sn41_event_catalog(self.config)

    def build_payload(self, predictions: Mapping[str, Any]) -> bytes:
        """Build a deterministic JSON payload from event probability predictions."""
        event_payloads = []
        for event in self.get_event_catalog():
            event_id = str(event["event_id"])
            probabilities = _event_probabilities(predictions, event_id)
            validation = self.scoring.validate_probabilities(event_id, probabilities)
            if not validation.is_valid:
                raise ValueError(f"Invalid probabilities for event_id={event_id}")
            event_payloads.append(
                {
                    "event_id": event_id,
                    "target": event.get("target"),
                    "probabilities": dict(sorted(probabilities.items())),
                    "total_probability": round(validation.total_probability, 12),
                }
            )

        payload = {
            "subnet_id": self.config.subnet_id,
            "adapter_version": self.config.adapter_version,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "events": event_payloads,
        }
        return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")

    def validate_payload(self, payload: bytes) -> bool:
        """Validate a deterministic JSON SN41 payload before submission."""
        try:
            decoded = json.loads(payload.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            return False
        if decoded.get("subnet_id") != self.config.subnet_id:
            return False
        events = decoded.get("events")
        if not isinstance(events, list) or len(events) != len(self.config.events):
            return False
        configured_event_ids = {str(event["event_id"]) for event in self.config.events}
        for event_payload in events:
            if not isinstance(event_payload, Mapping):
                return False
            event_id = event_payload.get("event_id")
            probabilities = event_payload.get("probabilities")
            if event_id not in configured_event_ids or not isinstance(probabilities, Mapping):
                return False
            validation = self.scoring.validate_probabilities(str(event_id), probabilities)
            if not validation.is_valid:
                return False
        return True

    def submit(self, payload: bytes, keys: SubmissionKeyPaths) -> SubmissionResult:
        """Return a dry-run submission result for validated SN41 payloads."""
        if not self.validate_payload(payload):
            raise ValueError("invalid SN41 payload")
        if not bool(self.config.submission.get("dry_run_supported", False)):
            raise ValueError("SN41 dry-run submission is not enabled in config")

        payload_hash = hashlib.sha256(payload).hexdigest()
        return SubmissionResult(
            success=True,
            subnet_id=self.subnet_id,
            status="dry_run",
            payload_hash=payload_hash,
            transaction_hash=None,
            latency_ms=0,
            metadata={
                "hotkey_path": str(keys.hotkey_path),
                "payload_bytes": len(payload),
                "network_submission": False,
            },
        )


def _event_probabilities(predictions: Mapping[str, Any], event_id: str) -> Mapping[str, float]:
    """Extract an event probability vector from a prediction mapping."""
    raw_probabilities = predictions.get(event_id)
    if raw_probabilities is None and "events" in predictions:
        raw_events = predictions["events"]
        if isinstance(raw_events, Mapping):
            raw_probabilities = raw_events.get(event_id)
    if not isinstance(raw_probabilities, Mapping):
        raise ValueError(f"Missing probability mapping for event_id={event_id}")
    return {str(label): float(probability) for label, probability in raw_probabilities.items()}
