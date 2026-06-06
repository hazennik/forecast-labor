"""Database contract tests for Phase 6A subnet logging scaffolding."""

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
INIT_SQL = REPO_ROOT / "infra" / "postgres" / "init.sql"


def _init_sql() -> str:
    """Load the PostgreSQL initialization script."""
    return INIT_SQL.read_text(encoding="utf-8")


def test_database_bootstrap_uses_subnet_schema_not_sn41_schema() -> None:
    """Bootstrap SQL should use subnet-agnostic tables before Phase 7 adapters."""
    sql = _init_sql()

    assert "CREATE SCHEMA IF NOT EXISTS subnets;" in sql
    assert "CREATE TABLE IF NOT EXISTS subnets.submission_log" in sql
    assert "CREATE TABLE IF NOT EXISTS subnets.event_catalog" in sql
    assert "GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA subnets" in sql
    assert "CREATE SCHEMA IF NOT EXISTS sn41;" not in sql
    assert "CREATE TABLE IF NOT EXISTS sn41." not in sql
    assert "GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA sn41" not in sql


def test_submission_log_has_multi_subnet_operational_fields() -> None:
    """Submission log should capture shared adapter metrics for any subnet."""
    sql = _init_sql()
    expected_columns = (
        "subnet_id VARCHAR(100) NOT NULL",
        "adapter_version VARCHAR(100)",
        "event_id VARCHAR(255)",
        "probability_vector JSONB",
        "payload_hash VARCHAR(128)",
        "submission_status VARCHAR(50) NOT NULL",
        "validator_response JSONB",
        "transaction_hash VARCHAR(255)",
        "latency_ms INTEGER",
        "metadata JSONB",
    )
    expected_indexes = (
        "idx_submission_log_subnet",
        "idx_submission_log_event",
        "idx_submission_log_status",
    )

    for expected_column in expected_columns:
        assert expected_column in sql
    for expected_index in expected_indexes:
        assert expected_index in sql


def test_event_catalog_discriminates_events_by_subnet() -> None:
    """Event catalog entries should be unique per subnet and external event id."""
    sql = _init_sql()

    assert "catalog_id SERIAL PRIMARY KEY" in sql
    assert "subnet_id VARCHAR(100) NOT NULL" in sql
    assert "external_event_id VARCHAR(255) NOT NULL" in sql
    assert "target VARCHAR(100)" in sql
    assert "UNIQUE (subnet_id, external_event_id)" in sql
    assert "idx_event_catalog_subnet" in sql
