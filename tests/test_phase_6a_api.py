"""Tests for Phase 6A FastAPI serving boundary."""

from pathlib import Path
from typing import Any, Dict
import json
import zipfile

from fastapi.testclient import TestClient

from app.config import ApiSettings
from app.main import create_app


def _client(settings: ApiSettings) -> TestClient:
    """Create a test client with explicit API settings."""
    return TestClient(create_app(settings))


def _write_bundle(path: Path, manifest: Dict[str, Any]) -> None:
    """Write a minimal signed-bundle-like zip with a manifest."""
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("manifest.json", json.dumps(manifest))
        archive.writestr("artifact/model.joblib", b"placeholder")


def test_health_endpoint_does_not_require_artifact(tmp_path: Path) -> None:
    """Liveness should pass even before a signed model bundle is deployed."""
    client = _client(ApiSettings(artifact_dir=tmp_path, environment="test"))

    response = client.get("/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["environment"] == "test"


def test_readiness_blocks_without_signed_artifact(tmp_path: Path) -> None:
    """Readiness should expose the missing artifact as a deployment blocker."""
    client = _client(ApiSettings(artifact_dir=tmp_path, environment="test"))

    response = client.get("/ready")

    assert response.status_code == 200
    payload = response.json()
    assert payload["ready"] is False
    assert payload["status"] == "not_ready"
    assert payload["checks"]["active_signed_artifact"] is False
    assert "No active signed model bundle" in payload["blockers"][0]


def test_active_artifact_reads_manifest(tmp_path: Path) -> None:
    """Artifact endpoint should report manifest metadata from the active bundle."""
    bundle = tmp_path / "active_bundle.zip"
    manifest = {
        "artifact_path": "artifact/model.joblib",
        "signature": "abc123",
        "metadata": {"model_id": "midas_v1", "vintage_date": "2025-11-29"},
    }
    _write_bundle(bundle, manifest)
    client = _client(
        ApiSettings(artifact_dir=tmp_path, active_bundle_path=bundle, environment="test")
    )

    response = client.get("/artifacts/active")

    assert response.status_code == 200
    payload = response.json()
    assert payload["active"] is True
    assert payload["artifact"]["verified"] is True
    assert payload["artifact"]["manifest_present"] is True
    assert payload["artifact"]["metadata"]["metadata"]["model_id"] == "midas_v1"


def test_forecast_refuses_placeholder_predictions_without_artifact(tmp_path: Path) -> None:
    """Forecast endpoint should not emit fake predictions before artifact deployment."""
    client = _client(ApiSettings(artifact_dir=tmp_path, environment="test"))

    response = client.post(
        "/forecast",
        json={
            "target": "NFP",
            "vintage_date": "2025-11-29",
            "horizon_months": 1,
            "features": {"claims_growth": 0.1},
        },
    )

    assert response.status_code == 503
    assert response.json()["detail"]["target"] == "nfp"
    assert "No verified signed model artifact" in response.json()["detail"]["message"]
