"""Deployment contract tests for the Phase 6A API service."""

from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
COMPOSE_PATH = REPO_ROOT / "docker-compose.yml"
API_DOCKERFILE = REPO_ROOT / "infra" / "api" / "Dockerfile"


def _compose_config() -> dict:
    """Load the Docker Compose configuration."""
    return yaml.safe_load(COMPOSE_PATH.read_text(encoding="utf-8"))


def test_api_compose_service_is_profiled_for_zone2_serving() -> None:
    """API service should be opt-in and use the dedicated API Dockerfile."""
    api_service = _compose_config()["services"]["api"]

    assert api_service["build"]["dockerfile"] == "./infra/api/Dockerfile"
    assert "api" in api_service["profiles"]
    assert "zone2" in api_service["profiles"]
    assert api_service["ports"] == ["8000:8000"]
    assert api_service["healthcheck"]["test"] == [
        "CMD",
        "curl",
        "-f",
        "http://localhost:8000/health",
    ]


def test_api_compose_service_mounts_only_zone2_runtime_paths() -> None:
    """API service must not mount raw data, Zone 1, or training code paths."""
    api_service = _compose_config()["services"]["api"]
    volumes = api_service["volumes"]
    forbidden_prefixes = (
        "./data",
        "./zone1",
        "./etl",
        "./features",
        "./models_src",
        "./backtests",
        "./scripts",
    )

    assert volumes == [
        "./zone2/runner/artifacts:/app/zone2/runner/artifacts:ro",
        "./zone2/runner/extracted:/app/zone2/runner/extracted",
    ]
    for volume in volumes:
        assert not volume.startswith(forbidden_prefixes)


def test_api_dockerfile_runs_uvicorn_without_training_mounts() -> None:
    """API image should run the FastAPI app and avoid raw-data bootstrap paths."""
    dockerfile = API_DOCKERFILE.read_text(encoding="utf-8")

    assert 'CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]' in dockerfile
    assert "http://localhost:8000/health" in dockerfile
    assert "/app/zone2/runner/artifacts" in dockerfile
    assert "/app/data" not in dockerfile
    assert "/app/zone1" not in dockerfile
