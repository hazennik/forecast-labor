"""Subnet payload signing boundary for offline validation before network submission."""

import hashlib
import hmac
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Mapping

SIGNATURE_ALGORITHM = "hmac-sha256"


class PayloadSigningError(ValueError):
    """Raised when subnet payload signing or verification fails."""


@dataclass(frozen=True)
class PayloadSignature:
    """Cryptographic signature metadata for a subnet payload."""

    payload_hash: str
    signature_hex: str
    algorithm: str
    key_fingerprint: str

    def to_dict(self) -> dict[str, str]:
        """Return a JSON-serializable signature envelope."""
        return asdict(self)


def payload_hash(payload: bytes) -> str:
    """Return the SHA256 hash of a subnet payload."""
    return hashlib.sha256(payload).hexdigest()


def key_fingerprint(hotkey_path: Path) -> str:
    """Return a stable fingerprint for a hotkey path without reading secret material."""
    normalized = str(hotkey_path.expanduser().resolve())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]


def load_signing_key(hotkey_path: Path) -> bytes:
    """Load signing key material from a hotkey file."""
    resolved = hotkey_path.expanduser()
    if not resolved.exists():
        raise PayloadSigningError(f"hotkey file not found: {resolved}")
    if not resolved.is_file():
        raise PayloadSigningError(f"hotkey path is not a file: {resolved}")

    key_text = resolved.read_text(encoding="utf-8").strip()
    if not key_text:
        raise PayloadSigningError(f"hotkey file is empty: {resolved}")

    try:
        return bytes.fromhex(key_text)
    except ValueError as exc:
        raise PayloadSigningError(
            f"hotkey file must contain hex-encoded key material: {resolved}"
        ) from exc


def sign_payload(payload: bytes, hotkey_path: Path) -> PayloadSignature:
    """Sign a subnet payload using key material from a hotkey file."""
    key_material = load_signing_key(hotkey_path)
    digest = payload_hash(payload)
    signature = hmac.new(key_material, payload, hashlib.sha256).hexdigest()
    return PayloadSignature(
        payload_hash=digest,
        signature_hex=signature,
        algorithm=SIGNATURE_ALGORITHM,
        key_fingerprint=key_fingerprint(hotkey_path),
    )


def verify_payload_signature(
    payload: bytes,
    signature: PayloadSignature,
    hotkey_path: Path,
) -> bool:
    """Verify a subnet payload signature against hotkey material."""
    if signature.algorithm != SIGNATURE_ALGORITHM:
        return False
    if signature.payload_hash != payload_hash(payload):
        return False
    if signature.key_fingerprint != key_fingerprint(hotkey_path):
        return False

    expected = sign_payload(payload, hotkey_path)
    return hmac.compare_digest(signature.signature_hex, expected.signature_hex)


def build_signed_envelope(payload: bytes, hotkey_path: Path) -> bytes:
    """Wrap a payload and signature in a deterministic JSON envelope."""
    payload_obj = json.loads(payload.decode("utf-8"))
    canonical_payload = json.dumps(payload_obj, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )
    signature = sign_payload(canonical_payload, hotkey_path)
    envelope: dict[str, Any] = {
        "payload": json.loads(canonical_payload.decode("utf-8")),
        "signature": signature.to_dict(),
    }
    return json.dumps(envelope, sort_keys=True, separators=(",", ":")).encode("utf-8")


def verify_signed_envelope(envelope_bytes: bytes, hotkey_path: Path) -> bool:
    """Verify a signed payload envelope."""
    try:
        envelope = json.loads(envelope_bytes.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return False

    payload_obj = envelope.get("payload")
    signature_obj = envelope.get("signature")
    if not isinstance(payload_obj, Mapping) or not isinstance(signature_obj, Mapping):
        return False

    payload = json.dumps(payload_obj, sort_keys=True, separators=(",", ":")).encode("utf-8")
    try:
        signature = PayloadSignature(
            payload_hash=str(signature_obj["payload_hash"]),
            signature_hex=str(signature_obj["signature_hex"]),
            algorithm=str(signature_obj["algorithm"]),
            key_fingerprint=str(signature_obj["key_fingerprint"]),
        )
    except (KeyError, TypeError, ValueError):
        return False

    return verify_payload_signature(payload, signature, hotkey_path)
