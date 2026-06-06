"""Tests for Phase 6A FastAPI serving boundary."""

from pathlib import Path

from fastapi.testclient import TestClient

from app.config import ApiSettings
from app.main import create_app
from models_src.utils.io import save_model
from models_src.utils.signing import create_signed_bundle


class FixedForecastModel:
    """Minimal picklable model used to exercise signed artifact inference."""

    def predict(self, features):
        """Return a deterministic prediction using a feature value."""
        claims_growth = float(features["claims_growth"].iloc[0])
        return {
            "prediction": 200.0 - (claims_growth * 10.0),
            "intervals": [{"level": 0.9, "lower": 150.0, "upper": 225.0}],
            "probabilities": {"below_150k": 0.2, "150k_to_250k": 0.7, "above_250k": 0.1},
        }


def _client(settings: ApiSettings) -> TestClient:
    """Create a test client with explicit API settings."""
    return TestClient(create_app(settings))


def _auth_headers() -> dict[str, str]:
    """Return valid API auth headers for protected endpoints."""
    return {"X-API-Key": "test-key"}


def _write_signed_model_bundle(path: Path, model_dir: Path) -> None:
    """Write a signed model bundle using production signing helpers."""
    model_path = model_dir / "model.joblib"
    save_model(FixedForecastModel(), model_path)
    create_signed_bundle(
        artifact_path=model_path,
        metadata={
            "model_id": "midas_v1",
            "model_type": "fixed_test_model",
            "vintage_date": "2025-11-29",
        },
        output_path=path,
    )


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
    _write_signed_model_bundle(bundle, tmp_path)
    client = _client(
        ApiSettings(
            artifact_dir=tmp_path,
            extraction_dir=tmp_path / "extracted",
            active_bundle_path=bundle,
            environment="test",
            api_key="test-key",
        )
    )

    response = client.get("/artifacts/active", headers=_auth_headers())

    assert response.status_code == 200
    payload = response.json()
    assert payload["active"] is True
    assert payload["artifact"]["verified"] is True
    assert payload["artifact"]["manifest_present"] is True
    assert payload["artifact"]["metadata"]["metadata"]["model_id"] == "midas_v1"
    assert payload["artifact"]["artifacts"] == ["artifact/model.joblib"]


def test_active_artifact_requires_api_key(tmp_path: Path) -> None:
    """Artifact status should require the configured API key."""
    bundle = tmp_path / "active_bundle.zip"
    _write_signed_model_bundle(bundle, tmp_path)
    client = _client(
        ApiSettings(
            artifact_dir=tmp_path,
            extraction_dir=tmp_path / "extracted",
            active_bundle_path=bundle,
            environment="test",
            api_key="test-key",
        )
    )

    response = client.get("/artifacts/active")

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid or missing API key"


def test_active_artifact_auth_requires_configured_key(tmp_path: Path) -> None:
    """Protected endpoints should fail closed if API auth is not configured."""
    client = _client(ApiSettings(artifact_dir=tmp_path, environment="test"))

    response = client.get("/artifacts/active", headers=_auth_headers())

    assert response.status_code == 503
    assert response.json()["detail"] == "API key authentication is not configured"


def test_export_active_artifact_requires_auth_and_verified_bundle(tmp_path: Path) -> None:
    """Artifact export should return the active verified signed bundle only with auth."""
    bundle = tmp_path / "active_bundle.zip"
    _write_signed_model_bundle(bundle, tmp_path)
    client = _client(
        ApiSettings(
            artifact_dir=tmp_path,
            extraction_dir=tmp_path / "extracted",
            active_bundle_path=bundle,
            environment="test",
            api_key="test-key",
        )
    )

    response = client.get("/artifacts/active/export", headers=_auth_headers())

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"
    assert response.headers["content-disposition"].startswith(
        'attachment; filename="active_bundle.zip"'
    )
    assert response.content[:2] == b"PK"


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


def test_forecast_serves_prediction_from_signed_artifact(tmp_path: Path) -> None:
    """Forecast endpoint should load a verified artifact and serve model output."""
    bundle = tmp_path / "active_bundle.zip"
    _write_signed_model_bundle(bundle, tmp_path)
    client = _client(
        ApiSettings(
            artifact_dir=tmp_path,
            extraction_dir=tmp_path / "extracted",
            active_bundle_path=bundle,
            environment="test",
        )
    )

    response = client.post(
        "/forecast",
        json={
            "target": "NFP",
            "vintage_date": "2025-11-29",
            "horizon_months": 1,
            "features": {"claims_growth": 0.5},
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["target"] == "nfp"
    assert payload["prediction"] == 195.0
    assert payload["model_id"] == "midas_v1"
    assert payload["intervals"][0]["level"] == 0.9
    assert payload["probabilities"]["150k_to_250k"] == 0.7
