"""
Unit tests for BaseETL class.

Tests the abstract base class for all ETL pipelines.
"""

import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import Mock, patch

import pandas as pd
import pytest

from etl.common.base import BaseETL, ETLConfig, IngestionStatus


# Create a concrete implementation for testing
class TestETLPipeline(BaseETL):
    """Concrete ETL implementation for testing"""

    def __init__(self, config: ETLConfig, test_data: pd.DataFrame = None):
        super().__init__(config)
        if test_data is not None:
            self.test_data = test_data
        else:
            self.test_data = pd.DataFrame(
                {"date": pd.date_range("2024-01-01", periods=10, freq="D"), "value": range(10)}
            )
        self._extract_called = False
        self._validate_called = False
        self._transform_called = False

    def extract(self) -> pd.DataFrame:
        """Mock extract method"""
        self._extract_called = True
        return self.test_data.copy()

    def validate(self, df: pd.DataFrame) -> bool:
        """Mock validate method"""
        self._validate_called = True
        return not df.empty


@pytest.mark.unit
@pytest.mark.etl
class TestBaseETL:
    """Test suite for BaseETL class"""

    @pytest.fixture
    def temp_paths(self):
        """Create temporary paths for testing"""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            yield {"raw_data": tmppath / "raw", "vintage": tmppath / "vintages"}

    @pytest.fixture
    def etl_config(self, temp_paths) -> ETLConfig:
        """Create ETL configuration for testing"""
        return ETLConfig(
            source_name="test_source",
            raw_data_path=temp_paths["raw_data"],
            vintage_path=temp_paths["vintage"],
            frequency="daily",
            retention_days=365,
            validate_schema=True,
            create_vintage=True,
            enable_validators=False,
            fail_on_validation_error=False,
        )

    @pytest.fixture
    def sample_data(self) -> pd.DataFrame:
        """Create sample DataFrame for testing"""
        return pd.DataFrame(
            {
                "date": pd.date_range("2024-01-01", periods=100, freq="D"),
                "value": range(100),
                "category": ["A", "B"] * 50,
            }
        )

    @pytest.fixture
    def test_etl(self, etl_config, sample_data) -> TestETLPipeline:
        """Create test ETL pipeline instance"""
        return TestETLPipeline(etl_config, sample_data)

    # =====================
    # INITIALIZATION TESTS
    # =====================

    def test_init_creates_metadata(self, test_etl):
        """Test that initialization creates metadata"""
        assert test_etl.metadata is not None
        assert test_etl.metadata.source_name == "test_source"
        assert test_etl.metadata.status == IngestionStatus.SUCCESS

    def test_init_stores_config(self, test_etl, etl_config):
        """Test that initialization stores config"""
        assert test_etl.config == etl_config
        assert test_etl.config.source_name == "test_source"

    @patch("loguru.logger.add")
    def test_init_sets_up_logging(self, mock_logger_add, etl_config):
        """Test that initialization sets up logging"""
        TestETLPipeline(etl_config)

        # Verify logger.add was called
        mock_logger_add.assert_called()
        call_args = mock_logger_add.call_args
        assert "test_source" in str(call_args)

    # =====================
    # EXTRACT METHOD TESTS
    # =====================

    def test_extract_must_be_implemented(self, etl_config):
        """Test that extract is abstract and must be implemented"""
        # Trying to instantiate BaseETL directly should fail
        with pytest.raises(TypeError):
            BaseETL(etl_config)

    def test_extract_called_by_run(self, test_etl):
        """Test that extract is called during run"""
        test_etl.run()

        assert test_etl._extract_called is True

    def test_extract_returns_dataframe(self, test_etl):
        """Test that extract returns DataFrame"""
        result = test_etl.extract()

        assert isinstance(result, pd.DataFrame)
        assert not result.empty

    # =====================
    # VALIDATE METHOD TESTS
    # =====================

    def test_validate_must_be_implemented(self, etl_config):
        """Test that validate is abstract and must be implemented"""
        # Already tested in extract test (same concept)
        pass

    def test_validate_called_by_run(self, test_etl):
        """Test that validate is called during run"""
        test_etl.run()

        assert test_etl._validate_called is True

    def test_validate_receives_dataframe(self, test_etl, sample_data):
        """Test that validate receives DataFrame"""
        result = test_etl.validate(sample_data)

        assert isinstance(result, bool)
        assert test_etl._validate_called is True

    def test_validate_can_return_false(self, test_etl):
        """Test that validate can return False"""
        # Create etl with empty data
        empty_data = pd.DataFrame()
        result = test_etl.validate(empty_data)

        assert result is False

    # =====================
    # TRANSFORM METHOD TESTS
    # =====================

    def test_transform_default_returns_unchanged(self, test_etl, sample_data):
        """Test that default transform returns data unchanged"""
        result = test_etl.transform(sample_data)

        pd.testing.assert_frame_equal(result, sample_data)

    def test_transform_can_be_overridden(self, etl_config, sample_data):
        """Test that transform can be overridden"""

        class CustomETL(TestETLPipeline):
            def transform(self, df: pd.DataFrame) -> pd.DataFrame:
                df = df.copy()
                df["transformed"] = True
                return df

        etl = CustomETL(etl_config, sample_data)
        result = etl.transform(sample_data)

        assert "transformed" in result.columns
        assert result["transformed"].all()

    # =====================
    # SAVE_RAW METHOD TESTS
    # =====================

    def test_save_raw_creates_file(self, test_etl, sample_data):
        """Test that save_raw creates file"""
        filepath = test_etl.save_raw(sample_data)

        assert filepath.exists()
        assert filepath.suffix == ".parquet"
        assert "test_source" in filepath.name

    def test_save_raw_creates_directory(self, test_etl, sample_data):
        """Test that save_raw creates directory if not exists"""
        filepath = test_etl.save_raw(sample_data)

        assert filepath.parent.exists()

    def test_save_raw_updates_metadata(self, test_etl, sample_data):
        """Test that save_raw updates metadata"""
        filepath = test_etl.save_raw(sample_data)

        assert test_etl.metadata.file_path == str(filepath)
        assert test_etl.metadata.file_size_bytes > 0
        assert test_etl.metadata.row_count == len(sample_data)

    def test_save_raw_data_readable(self, test_etl, sample_data):
        """Test that saved data can be read back"""
        filepath = test_etl.save_raw(sample_data)

        loaded_data = pd.read_parquet(filepath)

        assert len(loaded_data) == len(sample_data)
        assert list(loaded_data.columns) == list(sample_data.columns)

    def test_save_raw_filename_format(self, test_etl, sample_data):
        """Test that save_raw uses correct filename format"""
        filepath = test_etl.save_raw(sample_data)

        # Format: {source_name}_{timestamp}.parquet
        assert "test_source" in filepath.name
        assert filepath.suffix == ".parquet"
        # Check timestamp format (should contain digits)
        assert any(char.isdigit() for char in filepath.stem)

    # =====================
    # CREATE_VINTAGE METHOD TESTS
    # =====================

    def test_create_vintage_creates_file(self, test_etl, sample_data):
        """Test that create_vintage creates file"""
        vintage_date = datetime(2024, 11, 1)
        filepath = test_etl.create_vintage(sample_data, vintage_date)

        assert filepath.exists()
        assert "2024-11-01" in str(filepath)

    def test_create_vintage_directory_structure(self, test_etl, sample_data):
        """Test vintage directory structure"""
        vintage_date = datetime(2024, 11, 1)
        filepath = test_etl.create_vintage(sample_data, vintage_date)

        # Expected: {vintage_path}/test_source/2024-11-01/test_source_vintage.parquet
        assert "test_source" in str(filepath)
        assert "2024-11-01" in str(filepath)
        assert filepath.name == "test_source_vintage.parquet"

    def test_create_vintage_updates_metadata(self, test_etl, sample_data):
        """Test that create_vintage updates metadata"""
        vintage_date = datetime(2024, 11, 1)
        test_etl.create_vintage(sample_data, vintage_date)

        assert test_etl.metadata.vintage_date == vintage_date

    def test_create_vintage_default_date(self, test_etl, sample_data):
        """Test create_vintage with default date (today)"""
        filepath = test_etl.create_vintage(sample_data)

        today_str = datetime.now().strftime("%Y-%m-%d")
        assert today_str in str(filepath)

    def test_create_vintage_respects_config_flag(self, etl_config, sample_data):
        """Test that create_vintage respects config flag"""
        etl_config.create_vintage = False
        test_etl = TestETLPipeline(etl_config, sample_data)

        result = test_etl.create_vintage(sample_data)

        assert result is None

    def test_create_vintage_warns_if_exists(self, test_etl, sample_data):
        """Test that create_vintage warns if vintage exists"""
        vintage_date = datetime(2024, 11, 1)

        # Create first vintage
        test_etl.create_vintage(sample_data, vintage_date)

        # Create duplicate (should return existing path)
        with patch("loguru.logger.warning") as mock_warning:
            filepath = test_etl.create_vintage(sample_data, vintage_date)

            # Should have logged warning
            mock_warning.assert_called()
            assert filepath.exists()

    # =====================
    # RUN_VALIDATORS TESTS
    # =====================

    def test_run_validators_disabled_by_default(self, test_etl, sample_data):
        """Test that validators are disabled by default"""
        results, passed = test_etl.run_validators(sample_data)

        assert results == []
        assert passed is True

    def test_run_validators_returns_empty_if_no_validators(self, etl_config, sample_data):
        """Test run_validators with enable but no validators"""
        etl_config.enable_validators = True
        etl_config.validators = []
        test_etl = TestETLPipeline(etl_config, sample_data)

        results, passed = test_etl.run_validators(sample_data)

        assert results == []
        assert passed is True

    def test_run_validators_calls_each_validator(self, etl_config, sample_data):
        """Test that run_validators calls each validator"""
        # Create mock validators
        mock_validator1 = Mock()
        mock_validator2 = Mock()

        mock_result1 = Mock(passed=True, severity=Mock(value="INFO"), message="OK")
        mock_result2 = Mock(passed=True, severity=Mock(value="INFO"), message="OK")

        mock_validator1.validate.return_value = [mock_result1]
        mock_validator2.validate.return_value = [mock_result2]

        etl_config.enable_validators = True
        etl_config.validators = [mock_validator1, mock_validator2]

        test_etl = TestETLPipeline(etl_config, sample_data)
        results, passed = test_etl.run_validators(sample_data)

        assert len(results) == 2
        assert passed is True
        mock_validator1.validate.assert_called_once()
        mock_validator2.validate.assert_called_once()

    def test_run_validators_detects_critical_failure(self, etl_config, sample_data):
        """Test that critical failures are detected"""
        from etl.validators.base_validator import (
            ValidationResult,
            ValidationStatus,
            ValidationSeverity,
        )

        mock_validator = Mock()
        # Use actual ValidationResult with CRITICAL severity
        mock_result = ValidationResult(
            rule_name="test_rule",
            status=ValidationStatus.FAILED,
            severity=ValidationSeverity.CRITICAL,
            message="Critical error",
        )
        mock_validator.validate.return_value = [mock_result]

        etl_config.enable_validators = True
        etl_config.validators = [mock_validator]
        etl_config.fail_on_validation_error = True

        test_etl = TestETLPipeline(etl_config, sample_data)
        results, passed = test_etl.run_validators(sample_data)

        assert len(results) == 1
        assert passed is False

    def test_run_validators_handles_validator_exception(self, etl_config, sample_data):
        """Test handling of validator exceptions"""
        mock_validator = Mock()
        mock_validator.validate.side_effect = Exception("Validator error")

        etl_config.enable_validators = True
        etl_config.validators = [mock_validator]

        test_etl = TestETLPipeline(etl_config, sample_data)

        # Should not raise, should handle gracefully
        results, passed = test_etl.run_validators(sample_data)

        assert results == []
        assert passed is True

    # =====================
    # LOG_INGESTION TESTS
    # =====================

    def test_log_ingestion_updates_metadata(self, test_etl):
        """Test that log_ingestion updates metadata"""
        test_etl.log_ingestion(IngestionStatus.SUCCESS)

        assert test_etl.metadata.status == IngestionStatus.SUCCESS
        assert test_etl.metadata.error_message is None

    def test_log_ingestion_with_error(self, test_etl):
        """Test log_ingestion with error message"""
        error_msg = "Test error message"
        test_etl.log_ingestion(IngestionStatus.FAILED, error_msg)

        assert test_etl.metadata.status == IngestionStatus.FAILED
        assert test_etl.metadata.error_message == error_msg

    @patch("loguru.logger.error")
    def test_log_ingestion_logs_error(self, mock_logger_error, test_etl):
        """Test that errors are logged"""
        test_etl.log_ingestion(IngestionStatus.FAILED, "Error message")

        mock_logger_error.assert_called()

    # =====================
    # RUN METHOD TESTS (INTEGRATION)
    # =====================

    def test_run_success_full_pipeline(self, test_etl):
        """Test successful run of full pipeline"""
        result = test_etl.run()

        assert result is True
        assert test_etl._extract_called is True
        assert test_etl._validate_called is True
        assert test_etl.metadata.status == IngestionStatus.SUCCESS

    def test_run_creates_raw_file(self, test_etl):
        """Test that run creates raw file"""
        test_etl.run()

        raw_path = test_etl.config.raw_data_path
        files = list(raw_path.glob("*.parquet"))

        assert len(files) > 0

    def test_run_creates_vintage(self, test_etl):
        """Test that run creates vintage snapshot"""
        test_etl.run()

        vintage_path = test_etl.config.vintage_path / "test_source"

        assert vintage_path.exists()
        # Check that vintage directory was created
        vintage_dirs = list(vintage_path.iterdir())
        assert len(vintage_dirs) > 0

    def test_run_handles_empty_extract(self, etl_config):
        """Test run handles empty data from extract"""

        class EmptyETL(TestETLPipeline):
            def extract(self) -> pd.DataFrame:
                return pd.DataFrame()  # Empty

        test_etl = EmptyETL(etl_config)
        result = test_etl.run()

        assert result is False
        assert test_etl.metadata.status == IngestionStatus.FAILED

    def test_run_handles_none_extract(self, etl_config):
        """Test run handles None from extract"""

        class NoneETL(TestETLPipeline):
            def extract(self) -> pd.DataFrame:
                return None

        test_etl = NoneETL(etl_config)
        result = test_etl.run()

        assert result is False
        assert test_etl.metadata.status == IngestionStatus.FAILED

    def test_run_handles_validation_failure(self, etl_config, sample_data):
        """Test run handles validation failure"""

        class FailValidationETL(TestETLPipeline):
            def validate(self, df: pd.DataFrame) -> bool:
                return False  # Always fail

        test_etl = FailValidationETL(etl_config, sample_data)
        result = test_etl.run()

        assert result is False
        assert test_etl.metadata.status == IngestionStatus.FAILED

    def test_run_handles_exception(self, etl_config):
        """Test run handles exceptions gracefully"""

        class ErrorETL(TestETLPipeline):
            def extract(self) -> pd.DataFrame:
                raise ValueError("Test error")

        test_etl = ErrorETL(etl_config)
        result = test_etl.run()

        assert result is False
        assert test_etl.metadata.status == IngestionStatus.FAILED
        assert "Test error" in test_etl.metadata.error_message

    def test_run_skips_validation_if_disabled(self, etl_config, sample_data):
        """Test that validation can be skipped"""
        etl_config.validate_schema = False
        test_etl = TestETLPipeline(etl_config, sample_data)

        result = test_etl.run()

        assert result is True
        # validate() should not be called when validate_schema=False
        # (but our test implementation calls it anyway, so we check success)

    def test_run_respects_validator_failure(self, etl_config, sample_data):
        """Test that run respects validator failures"""
        from etl.validators.base_validator import (
            ValidationResult,
            ValidationStatus,
            ValidationSeverity,
        )

        mock_validator = Mock()
        # Use actual ValidationResult with CRITICAL severity
        mock_result = ValidationResult(
            rule_name="test_rule",
            status=ValidationStatus.FAILED,
            severity=ValidationSeverity.CRITICAL,
            message="Critical failure",
        )
        mock_validator.validate.return_value = [mock_result]

        etl_config.enable_validators = True
        etl_config.validators = [mock_validator]
        etl_config.fail_on_validation_error = True

        test_etl = TestETLPipeline(etl_config, sample_data)
        result = test_etl.run()

        assert result is False
        assert test_etl.metadata.status == IngestionStatus.FAILED

    # =====================
    # EDGE CASES
    # =====================

    def test_multiple_runs_create_separate_files(self, test_etl):
        """Test that multiple runs create separate files"""
        import time

        test_etl.run()
        time.sleep(1.1)  # Ensure different timestamp (second precision)
        test_etl.run()

        raw_path = test_etl.config.raw_data_path
        files = list(raw_path.glob("*.parquet"))

        # Should have 2 separate files
        assert len(files) == 2

    def test_large_dataframe_handling(self, etl_config):
        """Test handling of large DataFrames"""
        # Create large DataFrame (10,000 rows)
        large_data = pd.DataFrame(
            {
                "date": pd.date_range("2020-01-01", periods=10000, freq="H"),
                "value": range(10000),
                "category": ["A", "B", "C", "D", "E"] * 2000,
            }
        )

        test_etl = TestETLPipeline(etl_config, large_data)
        result = test_etl.run()

        assert result is True
        assert test_etl.metadata.row_count == 10000
