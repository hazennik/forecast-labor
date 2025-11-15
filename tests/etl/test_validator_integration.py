"""
Integration tests for ETL + Validator framework integration.

Tests the complete integration between ETL pipelines and validators.
"""

import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

import pandas as pd
import pytest

from etl.common.base import ETLConfig, BaseETL, IngestionStatus
from etl.validators.base_validator import ValidationResult, ValidationSeverity, ValidationStatus


class MockValidator:
    """Mock validator for testing"""
    
    def __init__(self, should_pass: bool = True, severity: str = "INFO"):
        self.should_pass = should_pass
        self.severity_str = severity
        self._called = False
    
    def validate(self, df: pd.DataFrame):
        """Mock validate method"""
        self._called = True
        
        # Map string severity to enum
        severity_map = {
            "INFO": ValidationSeverity.INFO,
            "WARNING": ValidationSeverity.WARNING,
            "ERROR": ValidationSeverity.ERROR,
            "CRITICAL": ValidationSeverity.CRITICAL
        }
        
        # Use actual ValidationResult
        result = ValidationResult(
            rule_name="mock_rule",
            status=ValidationStatus.PASSED if self.should_pass else ValidationStatus.FAILED,
            severity=severity_map.get(self.severity_str, ValidationSeverity.INFO),
            message=f"Validation {'passed' if self.should_pass else 'failed'}"
        )
        
        return [result]


class TestETLForValidation(BaseETL):
    """Test ETL pipeline for validator integration"""
    
    def extract(self) -> pd.DataFrame:
        return pd.DataFrame({
            "date": pd.date_range("2024-01-01", periods=10),
            "value": range(10)
        })
    
    def validate(self, df: pd.DataFrame) -> bool:
        return not df.empty


@pytest.mark.integration
@pytest.mark.etl
@pytest.mark.validator
class TestETLValidatorIntegration:
    """Test ETL and Validator framework integration"""
    
    @pytest.fixture
    def temp_paths(self):
        """Create temporary paths"""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            yield {
                "raw_data": tmppath / "raw",
                "vintage": tmppath / "vintages"
            }
    
    def test_etl_with_validators_enabled(self, temp_paths):
        """Test ETL pipeline with validators enabled"""
        validator = MockValidator(should_pass=True)
        
        config = ETLConfig(
            source_name="test_source",
            raw_data_path=temp_paths["raw_data"],
            vintage_path=temp_paths["vintage"],
            frequency="daily",
            enable_validators=True,
            validators=[validator],
            fail_on_validation_error=False
        )
        
        etl = TestETLForValidation(config)
        result = etl.run()
        
        assert result is True
        assert validator._called is True
    
    def test_etl_with_validator_failure_non_critical(self, temp_paths):
        """Test ETL continues on non-critical validator failure"""
        validator = MockValidator(should_pass=False, severity="WARNING")
        
        config = ETLConfig(
            source_name="test_source",
            raw_data_path=temp_paths["raw_data"],
            vintage_path=temp_paths["vintage"],
            frequency="daily",
            enable_validators=True,
            validators=[validator],
            fail_on_validation_error=False
        )
        
        etl = TestETLForValidation(config)
        result = etl.run()
        
        # Should succeed despite warning
        assert result is True
    
    def test_etl_with_validator_failure_critical(self, temp_paths):
        """Test ETL halts on critical validator failure"""
        validator = MockValidator(should_pass=False, severity="CRITICAL")
        
        config = ETLConfig(
            source_name="test_source",
            raw_data_path=temp_paths["raw_data"],
            vintage_path=temp_paths["vintage"],
            frequency="daily",
            enable_validators=True,
            validators=[validator],
            fail_on_validation_error=True  # Fail on critical errors
        )
        
        etl = TestETLForValidation(config)
        result = etl.run()
        
        # Should fail due to critical error
        assert result is False
        assert etl.metadata.status == IngestionStatus.FAILED
    
    def test_etl_with_multiple_validators(self, temp_paths):
        """Test ETL with multiple validators"""
        validator1 = MockValidator(should_pass=True, severity="INFO")
        validator2 = MockValidator(should_pass=True, severity="INFO")
        validator3 = MockValidator(should_pass=True, severity="INFO")
        
        config = ETLConfig(
            source_name="test_source",
            raw_data_path=temp_paths["raw_data"],
            vintage_path=temp_paths["vintage"],
            frequency="daily",
            enable_validators=True,
            validators=[validator1, validator2, validator3]
        )
        
        etl = TestETLForValidation(config)
        result = etl.run()
        
        assert result is True
        assert validator1._called is True
        assert validator2._called is True
        assert validator3._called is True
    
    def test_etl_handles_validator_exception(self, temp_paths):
        """Test ETL handles validator exceptions gracefully"""
        class FailingValidator:
            def validate(self, df):
                raise Exception("Validator error")
        
        config = ETLConfig(
            source_name="test_source",
            raw_data_path=temp_paths["raw_data"],
            vintage_path=temp_paths["vintage"],
            frequency="daily",
            enable_validators=True,
            validators=[FailingValidator()]
        )
        
        etl = TestETLForValidation(config)
        result = etl.run()
        
        # Should handle exception and continue
        assert result is True

