"""
Pytest configuration and shared fixtures for forecast-labor tests.

This module provides:
- Common test fixtures
- Mock configurations
- Test data generators
- Shared test utilities
"""

import os
import tempfile
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Dict, Any, Generator
from unittest.mock import Mock, MagicMock

import numpy as np
import pandas as pd
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Import common utilities (will be created)
from etl.common.base import ETLConfig, IngestionMetadata
from etl.common.storage import StorageClient


# =====================
# DIRECTORY FIXTURES
# =====================

@pytest.fixture(scope="session")
def project_root() -> Path:
    """Return the project root directory."""
    return Path(__file__).parent.parent


@pytest.fixture(scope="session")
def test_data_dir(project_root: Path) -> Path:
    """Return the test data directory."""
    test_dir = project_root / "tests" / "fixtures" / "data"
    test_dir.mkdir(parents=True, exist_ok=True)
    return test_dir


@pytest.fixture(scope="session")
def golden_baseline_dir(project_root: Path) -> Path:
    """Return the golden baseline directory for regression tests."""
    baseline_dir = project_root / "tests" / "fixtures" / "golden_baselines"
    baseline_dir.mkdir(parents=True, exist_ok=True)
    return baseline_dir


@pytest.fixture
def temp_dir() -> Generator[Path, None, None]:
    """Create a temporary directory for test outputs."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


# =====================
# TIME & DATE FIXTURES
# =====================

@pytest.fixture
def test_vintage_date() -> date:
    """
    Pinned vintage date for deterministic testing.
    
    This date is used for all CI/CD tests to ensure reproducibility.
    All tests using vintage data should use this fixture.
    """
    return date(2024, 1, 15)


@pytest.fixture
def test_current_date() -> date:
    """Current date for relative date testing."""
    return date(2025, 11, 11)


@pytest.fixture
def date_range_monthly() -> pd.DatetimeIndex:
    """Generate a standard monthly date range for testing."""
    return pd.date_range(start="2020-01-01", end="2024-12-31", freq="MS")


@pytest.fixture
def date_range_weekly() -> pd.DatetimeIndex:
    """Generate a standard weekly date range for testing."""
    return pd.date_range(start="2020-01-01", end="2024-12-31", freq="W-SAT")


@pytest.fixture
def date_range_daily() -> pd.DatetimeIndex:
    """Generate a standard daily date range for testing."""
    return pd.date_range(start="2024-01-01", end="2024-12-31", freq="D")


# =====================
# DATABASE FIXTURES
# =====================

@pytest.fixture(scope="session")
def test_db_url() -> str:
    """
    Test database URL.
    
    Uses environment variable if set, otherwise uses in-memory SQLite.
    For integration tests, set TEST_DATABASE_URL to a test Postgres instance.
    """
    return os.getenv("TEST_DATABASE_URL", "sqlite:///:memory:")


@pytest.fixture
def db_engine(test_db_url: str):
    """Create a test database engine."""
    engine = create_engine(test_db_url, echo=False)
    yield engine
    engine.dispose()


@pytest.fixture
def db_session(db_engine):
    """Create a test database session."""
    Session = sessionmaker(bind=db_engine)
    session = Session()
    yield session
    session.rollback()
    session.close()


# =====================
# STORAGE FIXTURES
# =====================

@pytest.fixture
def mock_storage_client() -> Mock:
    """
    Mock StorageClient for testing without MinIO/S3.
    
    Simulates storage operations without actual network calls.
    """
    client = Mock(spec=StorageClient)
    client.upload_file.return_value = True
    client.download_file.return_value = True
    client.file_exists.return_value = True
    client.list_files.return_value = []
    return client


@pytest.fixture
def mock_minio_client() -> Mock:
    """Mock MinIO client for testing."""
    client = Mock()
    client.bucket_exists.return_value = True
    client.put_object.return_value = None
    client.get_object.return_value = Mock(read=lambda: b"test data")
    client.list_objects.return_value = []
    return client


# =====================
# ETL FIXTURES
# =====================

@pytest.fixture
def etl_config(test_vintage_date: date) -> ETLConfig:
    """Create a test ETL configuration."""
    return ETLConfig(
        source_name="test_source",
        vintage_date=test_vintage_date,
        output_path="data/raw/test_source",
        enable_validation=True,
        fail_on_validation_error=False,
        max_retries=3,
        timeout=30,
    )


@pytest.fixture
def sample_ingestion_metadata(test_vintage_date: date) -> IngestionMetadata:
    """Create sample ingestion metadata for testing."""
    return IngestionMetadata(
        source="test_source",
        vintage_date=test_vintage_date,
        ingestion_timestamp=datetime.now(),
        records_fetched=1000,
        status="success",
        error_message=None,
    )


# =====================
# DATA FIXTURES
# =====================

@pytest.fixture
def sample_time_series_df(date_range_monthly: pd.DatetimeIndex) -> pd.DataFrame:
    """
    Generate a sample time series DataFrame for testing.
    
    Includes:
    - Date index
    - Value column with realistic properties
    - Trend, seasonality, noise components
    """
    n = len(date_range_monthly)
    
    # Generate realistic time series components
    trend = pd.Series(range(n)) * 100 + 50000  # Linear trend
    seasonal = pd.Series([
        100 * (i % 12 - 6) for i in range(n)  # Seasonal component
    ])
    noise = pd.Series(np.random.normal(0, 500, n))  # Random noise
    
    df = pd.DataFrame({
        "date": date_range_monthly,
        "value": trend + seasonal + noise,
        "series_id": "TEST_SERIES_01",
    })
    df.set_index("date", inplace=True)
    
    return df


@pytest.fixture
def sample_claims_data(date_range_weekly: pd.DatetimeIndex) -> pd.DataFrame:
    """Generate sample unemployment claims data."""
    return pd.DataFrame({
        "date": date_range_weekly,
        "state": "US",
        "initial_claims": np.random.randint(200000, 400000, len(date_range_weekly)),
        "continued_claims": np.random.randint(1500000, 2500000, len(date_range_weekly)),
    })


@pytest.fixture
def sample_ces_data(date_range_monthly: pd.DatetimeIndex) -> pd.DataFrame:
    """Generate sample CES (employment) data."""
    base_value = 150000
    return pd.DataFrame({
        "date": date_range_monthly,
        "series_id": "CES0000000001",
        "value": base_value + np.random.randint(-50, 50, len(date_range_monthly)),
        "preliminary": False,
    })


# =====================
# HTTP/API FIXTURES
# =====================

@pytest.fixture
def mock_http_response() -> Mock:
    """Create a mock HTTP response."""
    response = Mock()
    response.status_code = 200
    response.json.return_value = {"status": "success", "data": []}
    response.text = '{"status": "success", "data": []}'
    response.raise_for_status.return_value = None
    return response


@pytest.fixture
def mock_requests_session(mock_http_response: Mock) -> Mock:
    """Create a mock requests session."""
    session = Mock()
    session.get.return_value = mock_http_response
    session.post.return_value = mock_http_response
    return session


# =====================
# SEASONAL ADJUSTMENT FIXTURES
# =====================

@pytest.fixture
def sample_x13_spec() -> str:
    """Generate a sample X-13ARIMA-SEATS specification file."""
    return """series {
    title = "Test Series"
    start = 2020.01
    data = (150000 151000 152000)
}

transform {
    function = log
}

arima {
    model = (0 1 1)(0 1 1)
}

x11 {
    mode = mult
    seasonalma = s3x5
}
"""


@pytest.fixture
def sample_x13_output() -> Dict[str, Any]:
    """Generate sample X-13 output data."""
    dates = pd.date_range(start="2020-01-01", end="2024-12-31", freq="MS")
    return {
        "series_id": "TEST_SERIES_01",
        "dates": dates,
        "original": pd.Series(range(len(dates)), index=dates) + 150000,
        "seasonally_adjusted": pd.Series(range(len(dates)), index=dates) + 149900,
        "trend": pd.Series(range(len(dates)), index=dates) + 149950,
        "seasonal_factors": pd.Series([1.0] * len(dates), index=dates),
    }


@pytest.fixture
def golden_m_statistics() -> Dict[str, float]:
    """
    Golden M-statistics baseline for regression testing.
    
    These values are recorded from a known-good seasonal adjustment run
    and used to detect quality degradation.
    """
    return {
        "m1": 0.15,  # Relative contribution of irregular over 3 months span
        "m2": 0.20,  # Relative contribution of irregular to stationary portion
        "m3": 0.50,  # Amount of month-to-month change compared to irregular
        "m4": 0.45,  # Randomness of irregular
        "m5": 0.30,  # Number of periods for cyclical dominance
        "m6": 0.25,  # Amount of annual change compared to irregular
        "m7": 0.35,  # Amount of MCD compared to TD
        "m8": 0.40,  # Smoothness of SI curve
        "m9": 0.20,  # Average linear movement in final SI ratios
        "m10": 0.55,  # Average linear movement in final irregular
        "m11": 0.60,  # Average linear movement in final seasonal factors
    }


# =====================
# VALIDATION FIXTURES
# =====================

@pytest.fixture
def sample_validation_schema() -> Dict[str, Any]:
    """Generate a sample validation schema."""
    return {
        "columns": {
            "date": {"type": "datetime64[ns]", "nullable": False},
            "value": {"type": "float64", "nullable": False, "min": 0},
            "series_id": {"type": "object", "nullable": False},
        },
        "constraints": {
            "unique": ["date", "series_id"],
            "not_null": ["date", "value", "series_id"],
        },
    }


# =====================
# FEATURE ENGINEERING FIXTURES
# =====================

@pytest.fixture
def sample_features_df(date_range_monthly: pd.DatetimeIndex) -> pd.DataFrame:
    """Generate sample feature data for model testing."""
    n = len(date_range_monthly)
    return pd.DataFrame({
        "date": date_range_monthly,
        "lag_1": np.random.randn(n),
        "lag_3": np.random.randn(n),
        "lag_12": np.random.randn(n),
        "ma_3": np.random.randn(n),
        "ma_12": np.random.randn(n),
        "diff_1": np.random.randn(n),
    }).set_index("date")


# =====================
# MOCK ENVIRONMENT FIXTURES
# =====================

@pytest.fixture
def mock_env_vars(monkeypatch) -> Dict[str, str]:
    """
    Set up mock environment variables for testing.
    
    Returns the dict of env vars set, allowing tests to verify them.
    """
    env_vars = {
        "POSTGRES_HOST": "localhost",
        "POSTGRES_PORT": "5432",
        "POSTGRES_DB": "test_forecast_labor",
        "POSTGRES_USER": "test_user",
        "POSTGRES_PASSWORD": "test_password",
        "MINIO_ENDPOINT": "localhost:9000",
        "MINIO_ACCESS_KEY": "test_access",
        "MINIO_SECRET_KEY": "test_secret",
        "MINIO_BUCKET": "test-bucket",
        "MLFLOW_TRACKING_URI": "http://localhost:5000",
        "PREFECT_API_URL": "http://localhost:4200/api",
        "ACTIVE_SUBNET": "test_subnet",
        "BLS_API_KEY": "test_bls_key",
    }
    
    for key, value in env_vars.items():
        monkeypatch.setenv(key, value)
    
    return env_vars


# =====================
# UTILITIES
# =====================

def assert_dataframe_equal(
    df1: pd.DataFrame,
    df2: pd.DataFrame,
    check_exact: bool = True,
    rtol: float = 1e-5,
    atol: float = 1e-8,
) -> None:
    """
    Assert that two DataFrames are equal with better error messages.
    
    Args:
        df1: First DataFrame
        df2: Second DataFrame
        check_exact: Whether to check exact equality (vs approximate)
        rtol: Relative tolerance for numeric comparisons
        atol: Absolute tolerance for numeric comparisons
    """
    pd.testing.assert_frame_equal(
        df1,
        df2,
        check_exact=check_exact,
        rtol=rtol,
        atol=atol,
        check_names=True,
        check_dtype=True,
        check_index_type=True,
        check_column_type=True,
    )


def assert_series_equal(
    s1: pd.Series,
    s2: pd.Series,
    check_exact: bool = True,
    rtol: float = 1e-5,
    atol: float = 1e-8,
) -> None:
    """Assert that two Series are equal with better error messages."""
    pd.testing.assert_series_equal(
        s1,
        s2,
        check_exact=check_exact,
        rtol=rtol,
        atol=atol,
        check_names=True,
        check_dtype=True,
    )


# Export utility functions for test modules
__all__ = [
    "assert_dataframe_equal",
    "assert_series_equal",
]

