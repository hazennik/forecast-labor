"""Tests for subnet payload signing boundary."""

import json
import secrets
from pathlib import Path

import pytest

from subnets.payload_signing import (
    PayloadSignature,
    PayloadSigningError,
    build_signed_envelope,
    key_fingerprint,
    payload_hash,
    sign_payload,
    verify_payload_signature,
    verify_signed_envelope,
)


def _write_hotkey(path: Path) -> bytes:
    """Write a hex-encoded hotkey file for signing tests."""
    key_material = secrets.token_bytes(32)
    path.write_text(key_material.hex())
    return key_material


def test_payload_hash_is_stable() -> None:
    """Payload hash should be deterministic for identical bytes."""
    payload = b'{"subnet_id":"sn41"}'
    assert payload_hash(payload) == payload_hash(payload)


def test_key_fingerprint_does_not_read_secret_material(tmp_path: Path) -> None:
    """Key fingerprint should depend on path identity, not file contents."""
    hotkey_path = tmp_path / "hotkey"
    hotkey_path.write_text("secret-material")

    assert key_fingerprint(hotkey_path) == key_fingerprint(hotkey_path)
    assert len(key_fingerprint(hotkey_path)) == 16


def test_sign_and_verify_payload_round_trip(tmp_path: Path) -> None:
    """Signed payloads should verify with the same hotkey material."""
    hotkey_path = tmp_path / "hotkey"
    _write_hotkey(hotkey_path)
    payload = b'{"subnet_id":"sn41","events":[]}'

    signature = sign_payload(payload, hotkey_path)

    assert isinstance(signature, PayloadSignature)
    assert signature.payload_hash == payload_hash(payload)
    assert verify_payload_signature(payload, signature, hotkey_path) is True


def test_verify_payload_signature_rejects_tampered_payload(tmp_path: Path) -> None:
    """Tampered payloads should fail signature verification."""
    hotkey_path = tmp_path / "hotkey"
    _write_hotkey(hotkey_path)
    payload = b'{"subnet_id":"sn41"}'
    signature = sign_payload(payload, hotkey_path)
    tampered = b'{"subnet_id":"sn41","tampered":true}'

    assert verify_payload_signature(tampered, signature, hotkey_path) is False


def test_sign_payload_requires_existing_hotkey_file(tmp_path: Path) -> None:
    """Signing should fail closed when hotkey material is unavailable."""
    missing = tmp_path / "missing-hotkey"
    with pytest.raises(PayloadSigningError, match="hotkey file not found"):
        sign_payload(b"payload", missing)


def test_signed_envelope_round_trip(tmp_path: Path) -> None:
    """Signed envelopes should preserve payload integrity across verification."""
    hotkey_path = tmp_path / "hotkey"
    _write_hotkey(hotkey_path)
    payload = json.dumps({"subnet_id": "sn41", "events": []}, sort_keys=True).encode("utf-8")

    envelope = build_signed_envelope(payload, hotkey_path)

    assert verify_signed_envelope(envelope, hotkey_path) is True


def test_verify_signed_envelope_rejects_modified_signature(tmp_path: Path) -> None:
    """Modified signature metadata should fail envelope verification."""
    hotkey_path = tmp_path / "hotkey"
    _write_hotkey(hotkey_path)
    payload = json.dumps({"subnet_id": "sn41"}, sort_keys=True).encode("utf-8")
    envelope = json.loads(build_signed_envelope(payload, hotkey_path).decode("utf-8"))
    envelope["signature"]["signature_hex"] = "0" * 64
    modified = json.dumps(envelope, sort_keys=True).encode("utf-8")

    assert verify_signed_envelope(modified, hotkey_path) is False
