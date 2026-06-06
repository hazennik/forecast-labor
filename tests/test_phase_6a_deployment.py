"""Deployment contract tests for the Phase 6A API service."""

from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
COMPOSE_PATH = REPO_ROOT / "docker-compose.yml"
API_DOCKERFILE = REPO_ROOT / "infra" / "api" / "Dockerfile"
DEPLOY_GATES_PATH = REPO_ROOT / "docs" / "ops" / "DEPLOY_GATES.md"
DOCS_README_PATH = REPO_ROOT / "docs" / "README.md"
IMPLEMENTATION_STATUS_PATH = REPO_ROOT / "docs" / "planning" / "IMPLEMENTATION_STATUS.md"
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


def test_phase_6a_deploy_gates_document_hard_blockers() -> None:
    """Deployment gates should document model, artifact, API, and rollback blockers."""
    deploy_gates = DEPLOY_GATES_PATH.read_text(encoding="utf-8")
    required_snippets = (
        "GATE_SMAPE_MAX",
        "GATE_COVERAGE_MIN",
        "GATE_COVERAGE_MAX",
        "GATE_COHERENCE_ERROR_MAX",
        "Calibration ECE must remain below `0.05`",
        "Revision error must remain below `30K`",
        "MIDAS, XGBoost, and LightGBM",
        "DFM is diagnostic-only",
        "docker compose exec etl pytest tests/test_phase_6a_api.py -q",
        "docker compose exec etl pytest tests/test_phase_6a_deployment.py -q",
        "docker compose --profile api config",
        "docker compose --profile api up -d api",
        "curl -fsS http://localhost:8000/ready",
        "curl -fsS http://localhost:8000/metrics",
        "`/forecast` fails closed with `503`",
        "`/forecast` fails closed with `429` and `Retry-After`",
        "Every response includes `X-Request-ID`",
        "docker compose exec etl pytest -q",
        "ACTIVE_MODEL_BUNDLE=zone2/runner/artifacts/previous_bundle.zip",
    )
    forbidden_roots = ("data", "zone1", "etl", "features", "models_src", "backtests", "scripts")

    for snippet in required_snippets:
        assert snippet in deploy_gates
    for forbidden_root in forbidden_roots:
        assert forbidden_root in deploy_gates


def test_phase_6a_final_status_points_to_phase_7_adapter_work() -> None:
    """Status docs should record Phase 6A closure and active Phase 7 adapter work."""
    status_doc = IMPLEMENTATION_STATUS_PATH.read_text(encoding="utf-8")
    docs_readme = DOCS_README_PATH.read_text(encoding="utf-8")

    assert "PHASE 7 IN PROGRESS: Subnet Integration (Adapter Pattern)" in status_doc
    assert (
        "Phase 7.1 base adapter interface, Phase 7.2 registry/configuration loading, "
        "and Phase 7.3 scheduler" in status_doc
    )
    assert "PHASE 6A COMPLETE: API & Two-Zone Architecture" in status_doc
    assert "**Completion:** Phase 6A 100%" in status_doc
    assert "Continue **Phase 7.4: Scoring Shim**" in status_doc
    assert "**Current Phase:** Phase 7 in progress" in docs_readme
    assert "**Phase 6A:** API & Two-Zone Architecture (100%)" in docs_readme
    assert "**Phase 7:** Subnet Integration (Adapter Pattern)" in docs_readme
    assert "### 🚧 In Progress\n- **Phase 4:** Feature Engineering" not in docs_readme
    assert "Phase 3 Complete" not in docs_readme
