"""Deployment contract tests for the Phase 6A API service."""

from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
COMPOSE_PATH = REPO_ROOT / "docker-compose.yml"
API_DOCKERFILE = REPO_ROOT / "infra" / "api" / "Dockerfile"
RUNBOOK_PATH = REPO_ROOT / "docs" / "ops" / "RUNBOOK.md"


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


def test_phase_6a_runbook_documents_api_operational_workflow() -> None:
    """Runbook should preserve deployment, smoke, observability, and rollback steps."""
    runbook = RUNBOOK_PATH.read_text(encoding="utf-8")
    required_snippets = (
        "docker compose --profile api config",
        "docker compose exec etl pytest tests/test_phase_6a_deployment.py -q",
        "docker compose --profile api up -d api",
        "curl -fsS http://localhost:8000/health",
        "curl -fsS http://localhost:8000/ready",
        "curl -fsS http://localhost:8000/status",
        "curl -fsS http://localhost:8000/metrics",
        "X-API-Key: ${ZONE2_API_KEY}",
        "X-Request-ID",
        "ACTIVE_MODEL_BUNDLE=zone2/runner/artifacts/previous_bundle.zip",
        "docker compose --profile api stop api",
    )
    required_failure_modes = (
        "`/forecast` returns `503`",
        "`/forecast` returns `429` with `Retry-After`",
        "`/artifacts/active` and `/artifacts/active/export` return `503`",
    )
    forbidden_roots = ("data", "zone1", "etl", "features", "models_src", "backtests", "scripts")

    for snippet in required_snippets:
        assert snippet in runbook
    for failure_mode in required_failure_modes:
        assert failure_mode in runbook
    for forbidden_root in forbidden_roots:
        assert forbidden_root in runbook
