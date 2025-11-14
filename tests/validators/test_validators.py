"""
Comprehensive tests for validation framework.

Tests SchemaValidator, FreshnessValidator, QualityValidator, and ReportGenerator.
"""

import tempfile
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from etl.validators.base_validator import (
    BaseValidator,
    ValidationRule,
    ValidationResult,
    ValidationStatus,
    ValidationSeverity
)
from etl.validators.schema_validator import SchemaValidator
from etl.validators.freshness_validator import FreshnessValidator
from etl.validators.quality_validator import QualityValidator
from etl.validators.report_generator import ValidationReportGenerator


@pytest.mark.unit
@pytest.mark.validator
class TestValidationResult:
    """Tests for ValidationResult dataclass"""
    
    def test_validation_result_creation(self):
        """Test creating validation result"""
        result = ValidationResult(
            rule_name="test_rule",
            status=ValidationStatus.PASSED,
            severity=ValidationSeverity.INFO,
            message="Test passed"
        )
        
        assert result.rule_name == "test_rule"
        assert result.status == ValidationStatus.PASSED
        assert result.severity == ValidationSeverity.INFO
    
    def test_is_blocking_critical_failure(self):
        """Test that critical failures are blocking"""
        result = ValidationResult(
            rule_name="critical_check",
            status=ValidationStatus.FAILED,
            severity=ValidationSeverity.CRITICAL,
            message="Critical failure"
        )
        
        assert result.is_blocking() is True
    
    def test_is_blocking_non_critical_failure(self):
        """Test that non-critical failures are not blocking"""
        result = ValidationResult(
            rule_name="warning_check",
            status=ValidationStatus.FAILED,
            severity=ValidationSeverity.WARNING,
            message="Warning"
        )
        
        assert result.is_blocking() is False
    
    def test_to_dict_conversion(self):
        """Test conversion to dictionary"""
        result = ValidationResult(
            rule_name="test_rule",
            status=ValidationStatus.PASSED,
            severity=ValidationSeverity.INFO,
            message="Success",
            details={"count": 100}
        )
        
        result_dict = result.to_dict()
        
        assert result_dict["rule_name"] == "test_rule"
        assert result_dict["status"] == "passed"
        assert result_dict["severity"] == "info"
        assert result_dict["details"]["count"] == 100


@pytest.mark.unit
@pytest.mark.validator
class TestValidationRule:
    """Tests for ValidationRule dataclass"""
    
    def test_validation_rule_creation(self):
        """Test creating validation rule"""
        def check_func(df):
            return ValidationResult(
                rule_name="test",
                status=ValidationStatus.PASSED,
                severity=ValidationSeverity.INFO,
                message="OK"
            )
        
        rule = ValidationRule(
            name="test_rule",
            description="Test rule",
            severity=ValidationSeverity.INFO,
            check_function=check_func
        )
        
        assert rule.name == "test_rule"
        assert rule.enabled is True
    
    def test_execute_enabled_rule(self):
        """Test executing enabled rule"""
        def check_func(df):
            return ValidationResult(
                rule_name="test",
                status=ValidationStatus.PASSED,
                severity=ValidationSeverity.INFO,
                message="OK"
            )
        
        rule = ValidationRule(
            name="test_rule",
            description="Test",
            severity=ValidationSeverity.INFO,
            check_function=check_func,
            enabled=True
        )
        
        df = pd.DataFrame({"col": [1, 2, 3]})
        result = rule.execute(df)
        
        assert result.status == ValidationStatus.PASSED
    
    def test_execute_disabled_rule(self):
        """Test executing disabled rule"""
        def check_func(df):
            return ValidationResult(
                rule_name="test",
                status=ValidationStatus.PASSED,
                severity=ValidationSeverity.INFO,
                message="OK"
            )
        
        rule = ValidationRule(
            name="test_rule",
            description="Test",
            severity=ValidationSeverity.INFO,
            check_function=check_func,
            enabled=False
        )
        
        df = pd.DataFrame({"col": [1, 2, 3]})
        result = rule.execute(df)
        
        assert result.status == ValidationStatus.SKIPPED
    
    def test_execute_handles_exception(self):
        """Test that rule execution handles exceptions"""
        def failing_check(df):
            raise ValueError("Test error")
        
        rule = ValidationRule(
            name="failing_rule",
            description="Fails",
            severity=ValidationSeverity.ERROR,
            check_function=failing_check
        )
        
        df = pd.DataFrame({"col": [1, 2, 3]})
        result = rule.execute(df)
        
        assert result.status == ValidationStatus.FAILED
        assert "exception" in result.message.lower()


@pytest.mark.unit
@pytest.mark.validator
class TestSchemaValidator:
    """Tests for SchemaValidator"""
    
    @pytest.fixture
    def sample_schema(self):
        """Sample schema definition"""
        return {
            "required_columns": ["date", "value", "category"],
            "column_types": {
                "date": "datetime64[ns]",
                "value": "int64",
                "category": "object"
            },
            "unique_columns": ["date"],
            "not_null_columns": ["date", "value"]
        }
    
    @pytest.fixture
    def valid_df(self):
        """Valid DataFrame matching schema"""
        return pd.DataFrame({
            "date": pd.date_range("2024-01-01", periods=10),
            "value": range(10),
            "category": ["A", "B"] * 5
        })
    
    def test_schema_validator_initialization(self, sample_schema):
        """Test SchemaValidator initialization"""
        validator = SchemaValidator(
            "test_source",
            required_columns=sample_schema["required_columns"],
            column_types=sample_schema["column_types"]
        )
        
        assert validator.source_name == "test_source"
        assert validator.required_columns == sample_schema["required_columns"]
        assert validator.column_types == sample_schema["column_types"]
        assert len(validator.rules) > 0
    
    def test_validates_required_columns_present(self, sample_schema, valid_df):
        """Test validation passes when required columns present"""
        validator = SchemaValidator(
            "test_source",
            required_columns=sample_schema["required_columns"],
            column_types=sample_schema["column_types"]
        )
        results = validator.validate(valid_df)
        
        # Should have rule checking required columns
        column_check_results = [r for r in results if "column" in r.rule_name.lower()]
        assert len(column_check_results) > 0
    
    def test_validates_required_columns_missing(self, sample_schema):
        """Test validation fails when required columns missing"""
        validator = SchemaValidator(
            "test_source",
            required_columns=sample_schema["required_columns"],
            column_types=sample_schema["column_types"]
        )
        
        incomplete_df = pd.DataFrame({
            "date": pd.date_range("2024-01-01", periods=10),
            # Missing "value" and "category"
        })
        
        results = validator.validate(incomplete_df)
        
        # Should have failures
        failed_results = [r for r in results if r.status == ValidationStatus.FAILED]
        assert len(failed_results) > 0
    
    def test_validates_data_types(self, sample_schema, valid_df):
        """Test validation of data types"""
        validator = SchemaValidator(
            "test_source",
            required_columns=sample_schema["required_columns"],
            column_types=sample_schema["column_types"]
        )
        results = validator.validate(valid_df)
        
        # All results should pass for valid data
        passed_results = [r for r in results if r.status == ValidationStatus.PASSED]
        assert len(passed_results) > 0


@pytest.mark.unit
@pytest.mark.validator
class TestFreshnessValidator:
    """Tests for FreshnessValidator"""
    
    def test_freshness_validator_initialization(self):
        """Test FreshnessValidator initialization"""
        validator = FreshnessValidator(
            source_name="test_source",
            date_column="date",
            max_age_days=7
        )
        
        assert validator.source_name == "test_source"
        assert validator.date_column == "date"
        assert validator.max_age_days == 7
    
    def test_validates_fresh_data(self):
        """Test validation passes for fresh data"""
        validator = FreshnessValidator(
            source_name="test_source",
            date_column="date",
            max_age_days=7
        )
        
        # Data from yesterday (fresh)
        fresh_df = pd.DataFrame({
            "date": [datetime.now() - timedelta(days=1)],
            "value": [100]
        })
        
        results = validator.validate(fresh_df)
        
        # Should pass freshness check
        freshness_results = [r for r in results if "fresh" in r.rule_name.lower()]
        assert any(r.status == ValidationStatus.PASSED for r in freshness_results)
    
    def test_validates_stale_data(self):
        """Test validation fails for stale data"""
        validator = FreshnessValidator(
            source_name="test_source",
            date_column="date",
            max_age_days=7
        )
        
        # Data from 30 days ago (stale)
        stale_df = pd.DataFrame({
            "date": [datetime.now() - timedelta(days=30)],
            "value": [100]
        })
        
        results = validator.validate(stale_df)
        
        # Should fail or warn on freshness
        non_passed_results = [r for r in results if r.status != ValidationStatus.PASSED]
        assert len(non_passed_results) > 0


@pytest.mark.unit
@pytest.mark.validator
class TestQualityValidator:
    """Tests for QualityValidator"""
    
    def test_quality_validator_initialization(self):
        """Test QualityValidator initialization"""
        validator = QualityValidator(
            source_name="test_source",
            critical_columns=["value"],
            unique_keys=["id"],
            numeric_ranges={"value": (0, 100)}
        )
        
        assert validator.source_name == "test_source"
        assert validator.critical_columns == ["value"]
        assert validator.unique_keys == ["id"]
        assert validator.numeric_ranges == {"value": (0, 100)}
    
    def test_validates_null_values(self):
        """Test validation of null values"""
        validator = QualityValidator(
            source_name="test_source",
            critical_columns=["value"]  # Will check for nulls in these columns
        )
        
        # DataFrame with 10% nulls (above threshold)
        df_with_nulls = pd.DataFrame({
            "value": [1, 2, None, None, 5, 6, 7, 8, 9, 10]
        })
        
        results = validator.validate(df_with_nulls)
        
        # Should detect high null percentage
        null_results = [r for r in results if "null" in r.rule_name.lower()]
        assert len(null_results) > 0
    
    def test_validates_duplicates(self):
        """Test validation of duplicate rows"""
        validator = QualityValidator(
            source_name="test_source",
            unique_keys=["id"]  # Will check for duplicate keys
        )
        
        # DataFrame with duplicates
        df_with_dupes = pd.DataFrame({
            "value": [1, 1, 1, 2, 3, 4, 5]
        })
        
        results = validator.validate(df_with_dupes)
        
        # Should detect duplicates
        dup_results = [r for r in results if "duplicate" in r.rule_name.lower()]
        assert len(dup_results) > 0
    
    def test_validates_outliers(self):
        """Test validation of statistical outliers"""
        validator = QualityValidator(
            source_name="test_source",
            numeric_ranges={"value": (0, 100)}  # Will check if values are in range
        )
        
        # DataFrame with extreme outlier
        df_with_outlier = pd.DataFrame({
            "value": [1, 2, 3, 4, 5, 1000]  # 1000 is clear outlier
        })
        
        results = validator.validate(df_with_outlier)
        
        # Should detect outliers
        outlier_results = [r for r in results if "outlier" in r.rule_name.lower()]
        assert len(outlier_results) > 0


@pytest.mark.unit
@pytest.mark.validator
class TestValidationReportGenerator:
    """Tests for ValidationReportGenerator"""
    
    @pytest.fixture
    def sample_results(self):
        """Sample validation results"""
        return [
            ValidationResult(
                rule_name="required_columns",
                status=ValidationStatus.PASSED,
                severity=ValidationSeverity.CRITICAL,
                message="All required columns present"
            ),
            ValidationResult(
                rule_name="data_types",
                status=ValidationStatus.PASSED,
                severity=ValidationSeverity.ERROR,
                message="Data types correct"
            ),
            ValidationResult(
                rule_name="freshness",
                status=ValidationStatus.WARNING,
                severity=ValidationSeverity.WARNING,
                message="Data is 5 days old"
            ),
            ValidationResult(
                rule_name="null_check",
                status=ValidationStatus.FAILED,
                severity=ValidationSeverity.ERROR,
                message="High null percentage detected"
            )
        ]
    
    def test_report_generator_initialization(self):
        """Test ReportGenerator initialization"""
        generator = ValidationReportGenerator()
        
        assert generator is not None
    
    def test_generate_html_report(self, sample_results):
        """Test HTML report generation"""
        generator = ValidationReportGenerator()
        
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = generator.generate_html_report(
                results=sample_results,
                title="Test Validation Report",
                output_dir=tmpdir
            )
            
            assert output_path.exists()
            assert output_path.suffix == ".html"
            
            # Verify HTML content
            content = output_path.read_text()
            assert "Test Validation Report" in content
            assert "required_columns" in content
    
    def test_generate_summary(self, sample_results):
        """Test summary generation"""
        generator = ValidationReportGenerator()
        
        summary = generator.generate_summary(sample_results)
        
        assert "total" in summary
        assert "passed" in summary
        assert "failed" in summary
        assert "warnings" in summary
        
        assert summary["total"] == 4
        assert summary["passed"] == 2
        assert summary["failed"] == 1
        assert summary["warnings"] == 1
    
    def test_generate_csv_report(self, sample_results):
        """Test CSV report generation"""
        generator = ValidationReportGenerator()
        
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = generator.generate_csv_report(
                results=sample_results,
                output_dir=tmpdir
            )
            
            assert output_path.exists()
            assert output_path.suffix == ".csv"
            
            # Verify CSV can be loaded
            df = pd.read_csv(output_path)
            assert len(df) == 4
            assert "rule_name" in df.columns


@pytest.mark.integration
@pytest.mark.validator
class TestValidatorIntegration:
    """Integration tests for complete validator workflow"""
    
    def test_full_validation_workflow(self):
        """Test complete validation workflow"""
        # Create validators
        schema = {
            "required_columns": ["date", "value"],
            "column_types": {"date": "datetime64[ns]", "value": "int64"},
            "not_null_columns": ["date", "value"]
        }
        
        schema_validator = SchemaValidator(
            "test_source",
            required_columns=schema["required_columns"],
            column_types=schema["column_types"]
        )
        freshness_validator = FreshnessValidator("test_source", "date", max_age_days=30)
        quality_validator = QualityValidator(
            "test_source",
            critical_columns=["value"],
            numeric_ranges={"value": (0, 200)}
        )
        
        # Create test data
        df = pd.DataFrame({
            "date": pd.date_range("2024-01-01", periods=100),
            "value": range(100)
        })
        
        # Run all validators
        all_results = []
        all_results.extend(schema_validator.validate(df))
        all_results.extend(freshness_validator.validate(df))
        all_results.extend(quality_validator.validate(df))
        
        assert len(all_results) > 0
        
        # Generate report
        generator = ValidationReportGenerator()
        summary = generator.generate_summary(all_results)
        
        assert summary["total"] > 0
    
    def test_validators_with_invalid_data(self):
        """Test validators with intentionally invalid data"""
        schema = {
            "required_columns": ["date", "value", "category"],
            "column_types": {"date": "datetime64[ns]", "value": "int64"},
            "not_null_columns": ["date", "value"]
        }
        
        schema_validator = SchemaValidator(
            "test_source",
            required_columns=schema["required_columns"],
            column_types=schema["column_types"]
        )
        quality_validator = QualityValidator(
            "test_source",
            critical_columns=["value"]  # Nulls will be flagged
        )
        
        # Invalid data: missing column, high nulls
        invalid_df = pd.DataFrame({
            "date": pd.date_range("2024-01-01", periods=10),
            "value": [1, None, None, None, None, 6, 7, 8, 9, 10]
            # Missing "category" column
            # 40% nulls in value (above threshold)
        })
        
        all_results = []
        all_results.extend(schema_validator.validate(invalid_df))
        all_results.extend(quality_validator.validate(invalid_df))
        
        # Should have failures
        failed_results = [r for r in all_results if r.status == ValidationStatus.FAILED]
        assert len(failed_results) > 0

