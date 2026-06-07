"""SN41 probability payload construction and validation."""

import json
from datetime import datetime, timezone
from typing import Any, Mapping, Optional, Sequence

from subnets.base_adapter import SubnetConfig
from subnets.scoring_shim import SubnetScoringShim


def extract_event_probabilities(
    predictions: Mapping[str, Any], event_id: str
) -> Mapping[str, float]:
    """Extract an event probability vector from a prediction mapping."""
    raw_probabilities = predictions.get(event_id)
    if raw_probabilities is None and "events" in predictions:
        raw_events = predictions["events"]
        if isinstance(raw_events, Mapping):
            raw_probabilities = raw_events.get(event_id)
    if not isinstance(raw_probabilities, Mapping):
        raise ValueError(f"Missing probability mapping for event_id={event_id}")
    return {str(label): float(probability) for label, probability in raw_probabilities.items()}


def build_event_payloads(
    events: Sequence[Mapping[str, Any]],
    predictions: Mapping[str, Any],
    scoring: SubnetScoringShim,
) -> list[dict[str, Any]]:
    """Build validated SN41 event payload entries from predictions."""
    event_payloads: list[dict[str, Any]] = []
    for event in events:
        event_id = str(event["event_id"])
        probabilities = extract_event_probabilities(predictions, event_id)
        validation = scoring.validate_probabilities(event_id, probabilities)
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
    return event_payloads


def build_sn41_payload(
    config: SubnetConfig,
    predictions: Mapping[str, Any],
    scoring: SubnetScoringShim,
    generated_at: Optional[datetime] = None,
) -> bytes:
    """Build a deterministic JSON SN41 payload from event probability predictions."""
    timestamp = generated_at or datetime.now(timezone.utc)
    event_payloads = build_event_payloads(config.events, predictions, scoring)
    payload = {
        "subnet_id": config.subnet_id,
        "adapter_version": config.adapter_version,
        "generated_at": timestamp.isoformat(),
        "events": event_payloads,
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


def validate_sn41_payload(
    config: SubnetConfig,
    payload: bytes,
    scoring: SubnetScoringShim,
) -> bool:
    """Validate a deterministic JSON SN41 payload before submission."""
    try:
        decoded = json.loads(payload.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return False
    if decoded.get("subnet_id") != config.subnet_id:
        return False
    events = decoded.get("events")
    if not isinstance(events, list) or len(events) != len(config.events):
        return False
    configured_event_ids = {str(event["event_id"]) for event in config.events}
    for event_payload in events:
        if not isinstance(event_payload, Mapping):
            return False
        event_id = event_payload.get("event_id")
        probabilities = event_payload.get("probabilities")
        if event_id not in configured_event_ids or not isinstance(probabilities, Mapping):
            return False
        validation = scoring.validate_probabilities(str(event_id), probabilities)
        if not validation.is_valid:
            return False
    return True
