"""SN41 adapter implementation for offline payload validation and dry runs."""

import hashlib
from typing import Any, Mapping, Sequence

from subnets.base_adapter import (
    BaseSubnetAdapter,
    SubmissionKeyPaths,
    SubmissionResult,
    SubnetConfig,
)
from subnets.payload_signing import PayloadSigningError, sign_payload, verify_payload_signature
from subnets.scoring_shim import SubnetScoringShim
from subnets.sn41.event_catalog import get_sn41_event_catalog
from subnets.sn41.payload_builder import build_sn41_payload, validate_sn41_payload


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
        return build_sn41_payload(self.config, predictions, self.scoring)

    def validate_payload(self, payload: bytes) -> bool:
        """Validate a deterministic JSON SN41 payload before submission."""
        return validate_sn41_payload(self.config, payload, self.scoring)

    def submit(self, payload: bytes, keys: SubmissionKeyPaths) -> SubmissionResult:
        """Return a dry-run submission result for validated SN41 payloads."""
        if not self.validate_payload(payload):
            raise ValueError("invalid SN41 payload")
        if not bool(self.config.submission.get("dry_run_supported", False)):
            raise ValueError("SN41 dry-run submission is not enabled in config")

        payload_hash = hashlib.sha256(payload).hexdigest()
        metadata: dict[str, Any] = {
            "hotkey_path": str(keys.hotkey_path),
            "payload_bytes": len(payload),
            "network_submission": False,
        }

        if bool(self.config.submission.get("requires_signature", False)):
            try:
                signature = sign_payload(payload, keys.hotkey_path)
            except PayloadSigningError as exc:
                raise ValueError(f"payload signing failed: {exc}") from exc
            if not verify_payload_signature(payload, signature, keys.hotkey_path):
                raise ValueError("payload signature verification failed")
            metadata["signature_algorithm"] = signature.algorithm
            metadata["signature_hex"] = signature.signature_hex
            metadata["key_fingerprint"] = signature.key_fingerprint

        return SubmissionResult(
            success=True,
            subnet_id=self.subnet_id,
            status="dry_run",
            payload_hash=payload_hash,
            transaction_hash=None,
            latency_ms=0,
            metadata=metadata,
        )
