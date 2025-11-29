"""
Tests for Phase 6.1.1: Staging Validation with Real Data

Comprehensive test suite for the validation orchestrator that verifies:
- API key configuration checks
- Infrastructure health checks
- Validation workflow orchestration
- Report generation
- Error handling and edge cases

Following TDD principles learned from Phases 1-5.13.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path
from datetime import datetime
import subprocess
import os
import json

from scripts.phase_6_1_1_staging_validation import (
    Phase611Validator,
    ValidationStatus,
    ValidationStep,
    ValidationReport
)


class TestValidationStatus:
    """Test ValidationStatus enum"""
    
    def test_validation_status_values(self):
        """Test that all expected status values exist"""
        assert ValidationStatus.NOT_STARTED.value == "not_started"
        assert ValidationStatus.IN_PROGRESS.value == "in_progress"
        assert ValidationStatus.PASSED.value == "passed"
        assert ValidationStatus.FAILED.value == "failed"
        assert ValidationStatus.SKIPPED.value == "skipped"


class TestValidationStep:
    """Test ValidationStep dataclass"""
    
    def test_validation_step_creation(self):
        """Test creating a ValidationStep"""
        step = ValidationStep(
            step_id="test_step",
            step_name="Test Step",
            status=ValidationStatus.PASSED
        )
        
        assert step.step_id == "test_step"
        assert step.step_name == "Test Step"
        assert step.status == ValidationStatus.PASSED
        assert step.started_at is None
        assert step.completed_at is None
    
    def test_validation_step_to_dict(self):
        """Test converting ValidationStep to dictionary"""
        step = ValidationStep(
            step_id="test_step",
            step_name="Test Step",
            status=ValidationStatus.PASSED,
            started_at="2025-01-01T00:00:00",
            completed_at="2025-01-01T00:01:00",
            details={"key": "value"}
        )
        
        result = step.to_dict()
        
        assert result["step_id"] == "test_step"
        assert result["status"] == "passed"
        assert result["details"] == {"key": "value"}


class TestValidationReport:
    """Test ValidationReport dataclass"""
    
    def test_validation_report_creation(self):
        """Test creating a ValidationReport"""
        report = ValidationReport(
            validation_id="test_validation_123",
            started_at="2025-01-01T00:00:00"
        )
        
        assert report.validation_id == "test_validation_123"
        assert report.started_at == "2025-01-01T00:00:00"
        assert report.steps == []
        assert report.api_keys_configured == {}
        assert report.issues_discovered == []
        assert report.recommendations == []
    
    def test_validation_report_to_dict(self):
        """Test converting ValidationReport to dictionary"""
        report = ValidationReport(
            validation_id="test_validation_123",
            started_at="2025-01-01T00:00:00",
            overall_status=ValidationStatus.PASSED
        )
        
        result = report.to_dict()
        
        assert result["validation_id"] == "test_validation_123"
        assert result["overall_status"] == "passed"
        assert isinstance(result["steps"], list)


class TestPhase611ValidatorInitialization:
    """Test Phase611Validator initialization"""
    
    def test_validator_initialization_check_only(self):
        """Test validator initialization in check-only mode"""
        validator = Phase611Validator(check_only=True)
        
        assert validator.check_only is True
        assert validator.report is not None
        assert validator.report.validation_id.startswith("phase_6_1_1_")
        assert validator.output_dir.exists()
    
    def test_validator_initialization_full_validation(self):
        """Test validator initialization in full validation mode"""
        validator = Phase611Validator(check_only=False)
        
        assert validator.check_only is False
        assert validator.report is not None


class TestAPIKeysCheck:
    """Test API keys configuration check"""
    
    @patch.dict(os.environ, {
        "BLS_API_KEY": "test_key",
        "NOAA_API_TOKEN": "test_token",
        "ALLOW_FALLBACK_DATA": "false"
    })
    def test_all_api_keys_configured(self):
        """Test when all API keys are configured"""
        validator = Phase611Validator(check_only=True)
        
        step = validator.check_api_keys()
        
        assert step.status == ValidationStatus.PASSED
        assert step.step_id == "1_api_keys"
        assert step.completed_at is not None
        assert validator.report.api_keys_configured["BLS_API_KEY"] is True
        assert validator.report.api_keys_configured["NOAA_API_TOKEN"] is True
    
    @patch.dict(os.environ, {}, clear=True)
    def test_missing_api_keys(self):
        """Test when API keys are missing"""
        validator = Phase611Validator(check_only=True)
        
        step = validator.check_api_keys()
        
        assert step.status == ValidationStatus.FAILED
        assert "Missing API keys" in step.error_message
        assert validator.report.api_keys_configured["BLS_API_KEY"] is False
        assert validator.report.api_keys_configured["NOAA_API_TOKEN"] is False
    
    @patch.dict(os.environ, {
        "BLS_API_KEY": "test_key",
        "NOAA_API_TOKEN": "test_token",
        "ALLOW_FALLBACK_DATA": "true"  # Wrong for production
    })
    def test_fallback_data_enabled_warning(self):
        """Test warning when ALLOW_FALLBACK_DATA is enabled"""
        validator = Phase611Validator(check_only=True)
        
        step = validator.check_api_keys()
        
        # Should still pass but add warning
        assert step.status == ValidationStatus.PASSED
        assert any("ALLOW_FALLBACK_DATA" in issue 
                   for issue in validator.report.issues_discovered)
        assert any("ALLOW_FALLBACK_DATA=false" in rec
                   for rec in validator.report.recommendations)


class TestInfrastructureCheck:
    """Test infrastructure health check"""
    
    @patch('subprocess.run')
    def test_infrastructure_check_passed(self, mock_run):
        """Test when infrastructure health check passes"""
        mock_run.return_value = Mock(
            returncode=0,
            stdout="All services healthy",
            stderr=""
        )
        
        validator = Phase611Validator(check_only=True)
        step = validator.check_infrastructure()
        
        assert step.status == ValidationStatus.PASSED
        assert step.step_id == "2_infrastructure"
        assert step.details["health_check_passed"] is True
        mock_run.assert_called_once()
    
    @patch('subprocess.run')
    def test_infrastructure_check_failed(self, mock_run):
        """Test when infrastructure health check fails"""
        mock_run.return_value = Mock(
            returncode=1,
            stdout="",
            stderr="Postgres not healthy"
        )
        
        validator = Phase611Validator(check_only=True)
        step = validator.check_infrastructure()
        
        assert step.status == ValidationStatus.FAILED
        assert "failed" in step.error_message.lower()
        assert any("Docker services" in issue 
                   for issue in validator.report.issues_discovered)
    
    @patch('subprocess.run', side_effect=subprocess.TimeoutExpired("cmd", 60))
    def test_infrastructure_check_timeout(self, mock_run):
        """Test when infrastructure check times out"""
        validator = Phase611Validator(check_only=True)
        step = validator.check_infrastructure()
        
        assert step.status == ValidationStatus.FAILED
        assert "timeout" in step.error_message.lower()


class TestRealETL:
    """Test real ETL execution"""
    
    @patch('subprocess.run')
    def test_real_etl_skipped_check_only(self, mock_run):
        """Test that real ETL is skipped in check-only mode"""
        validator = Phase611Validator(check_only=True)
        step = validator.run_real_etl()
        
        assert step.status == ValidationStatus.SKIPPED
        assert step.details["reason"] == "check_only mode enabled"
        mock_run.assert_not_called()
    
    @patch('subprocess.run')
    def test_real_etl_passed(self, mock_run):
        """Test when real ETL execution passes"""
        mock_run.return_value = Mock(
            returncode=0,
            stdout="✅ All ETL pipelines completed successfully",
            stderr=""
        )
        
        validator = Phase611Validator(check_only=False)
        step = validator.run_real_etl()
        
        assert step.status == ValidationStatus.PASSED
        assert step.details["etl_completed"] is True
        mock_run.assert_called_once()
    
    @patch('subprocess.run')
    def test_real_etl_failed(self, mock_run):
        """Test when real ETL execution fails"""
        mock_run.return_value = Mock(
            returncode=1,
            stdout="",
            stderr="API authentication failed"
        )
        
        validator = Phase611Validator(check_only=False)
        step = validator.run_real_etl()
        
        assert step.status == ValidationStatus.FAILED
        assert "failed" in step.error_message.lower()
        assert any("Real ETL failed" in issue
                   for issue in validator.report.issues_discovered)


class TestDataQualityValidation:
    """Test data quality validation"""
    
    @patch('subprocess.run')
    def test_data_quality_validation_skipped_check_only(self, mock_run):
        """Test that validation is skipped in check-only mode"""
        validator = Phase611Validator(check_only=True)
        step = validator.validate_data_quality()
        
        assert step.status == ValidationStatus.SKIPPED
        mock_run.assert_not_called()
    
    @patch('subprocess.run')
    def test_data_quality_validation_passed(self, mock_run):
        """Test when data quality validation passes"""
        mock_run.return_value = Mock(
            returncode=0,
            stdout="✅ All validations passed",
            stderr=""
        )
        
        validator = Phase611Validator(check_only=False)
        step = validator.validate_data_quality()
        
        assert step.status == ValidationStatus.PASSED
        assert step.details["validation_passed"] is True
    
    @patch('subprocess.run')
    def test_data_quality_validation_failed(self, mock_run):
        """Test when data quality validation fails"""
        mock_run.return_value = Mock(
            returncode=1,
            stdout="",
            stderr="Schema validation failed: Missing required columns"
        )
        
        validator = Phase611Validator(check_only=False)
        step = validator.validate_data_quality()
        
        assert step.status == ValidationStatus.FAILED
        assert "failed" in step.error_message.lower()


class TestSeasonalAdjustment:
    """Test seasonal adjustment execution"""
    
    @patch('subprocess.run')
    def test_seasonal_adjustment_skipped_check_only(self, mock_run):
        """Test that seasonal adjustment is skipped in check-only mode"""
        validator = Phase611Validator(check_only=True)
        step = validator.run_seasonal_adjustment()
        
        assert step.status == ValidationStatus.SKIPPED
        mock_run.assert_not_called()
    
    @patch('subprocess.run')
    def test_seasonal_adjustment_passed(self, mock_run):
        """Test when seasonal adjustment passes"""
        mock_run.return_value = Mock(
            returncode=0,
            stdout="✅ Seasonal adjustment completed",
            stderr=""
        )
        
        validator = Phase611Validator(check_only=False)
        step = validator.run_seasonal_adjustment()
        
        assert step.status == ValidationStatus.PASSED
        assert step.details["seasonal_adjustment_completed"] is True


class TestFeatureBuilding:
    """Test feature generation"""
    
    @patch('subprocess.run')
    def test_feature_building_skipped_check_only(self, mock_run):
        """Test that feature building is skipped in check-only mode"""
        validator = Phase611Validator(check_only=True)
        step = validator.build_features()
        
        assert step.status == ValidationStatus.SKIPPED
        mock_run.assert_not_called()
    
    @patch('subprocess.run')
    def test_feature_building_passed(self, mock_run):
        """Test when feature building passes"""
        mock_run.return_value = Mock(
            returncode=0,
            stdout="✅ Features built successfully",
            stderr=""
        )
        
        validator = Phase611Validator(check_only=False)
        step = validator.build_features()
        
        assert step.status == ValidationStatus.PASSED
        assert step.details["features_built"] is True
        assert "vintage_date" in step.details


class TestSampleModelTraining:
    """Test sample model training"""
    
    def test_sample_model_training_skipped_check_only(self):
        """Test that model training is skipped in check-only mode"""
        validator = Phase611Validator(check_only=True)
        step = validator.train_sample_model()
        
        assert step.status == ValidationStatus.SKIPPED
        assert "check_only mode enabled" in step.details["reason"]
    
    def test_sample_model_training_deferred(self):
        """Test that model training is deferred (Phase 5 not fully integrated)"""
        validator = Phase611Validator(check_only=False)
        step = validator.train_sample_model()
        
        # Currently deferred until Phase 6+ training orchestration
        assert step.status == ValidationStatus.SKIPPED
        assert "Model training infrastructure" in step.details["reason"]


class TestReportGeneration:
    """Test validation report generation"""
    
    @patch.dict(os.environ, {
        "BLS_API_KEY": "test_key",
        "NOAA_API_TOKEN": "test_token"
    })
    def test_generate_json_report(self):
        """Test generating JSON validation report"""
        validator = Phase611Validator(check_only=True)
        
        # Add some steps
        step1 = ValidationStep(
            step_id="1_api_keys",
            step_name="API Keys Check",
            status=ValidationStatus.PASSED
        )
        validator.report.steps.append(step1)
        
        json_path, md_path = validator.generate_final_report()
        
        assert json_path.exists()
        assert json_path.suffix == ".json"
        
        # Verify JSON content
        with open(json_path) as f:
            data = json.load(f)
        
        assert data["validation_id"] == validator.report.validation_id
        assert data["overall_status"] == "passed"
        assert len(data["steps"]) == 1
        
        # Cleanup
        json_path.unlink()
        if md_path.exists():
            md_path.unlink()
    
    @patch.dict(os.environ, {
        "BLS_API_KEY": "test_key",
        "NOAA_API_TOKEN": "test_token"
    })
    def test_generate_markdown_report(self):
        """Test generating Markdown validation report"""
        validator = Phase611Validator(check_only=True)
        
        # Add some steps
        step1 = ValidationStep(
            step_id="1_api_keys",
            step_name="API Keys Check",
            status=ValidationStatus.PASSED
        )
        validator.report.steps.append(step1)
        
        json_path, md_path = validator.generate_final_report()
        
        assert md_path.exists()
        assert md_path.suffix == ".md"
        
        # Verify Markdown content
        content = md_path.read_text()
        
        assert "Phase 6.1.1: Staging Validation with Real Data" in content
        assert validator.report.validation_id in content
        assert "API Keys Check" in content
        assert "✅" in content  # Passed status emoji
        
        # Cleanup
        json_path.unlink()
        md_path.unlink()
    
    @patch.dict(os.environ, {}, clear=True)
    def test_report_with_failures(self):
        """Test report generation with failed steps"""
        validator = Phase611Validator(check_only=True)
        
        # Add failed step
        step1 = ValidationStep(
            step_id="1_api_keys",
            step_name="API Keys Check",
            status=ValidationStatus.FAILED,
            error_message="Missing API keys"
        )
        validator.report.steps.append(step1)
        validator.report.issues_discovered.append("API keys not configured")
        
        json_path, md_path = validator.generate_final_report()
        
        # Verify overall status is FAILED
        with open(json_path) as f:
            data = json.load(f)
        
        assert data["overall_status"] == "failed"
        
        # Verify Markdown shows failure
        content = md_path.read_text()
        assert "❌" in content
        assert "Issues Discovered" in content
        
        # Cleanup
        json_path.unlink()
        md_path.unlink()


class TestFullValidationWorkflow:
    """Test complete validation workflow"""
    
    @patch.dict(os.environ, {
        "BLS_API_KEY": "test_key",
        "NOAA_API_TOKEN": "test_token",
        "ALLOW_FALLBACK_DATA": "false"
    })
    @patch('subprocess.run')
    def test_full_workflow_check_only_mode(self, mock_run):
        """Test complete workflow in check-only mode"""
        # Mock infrastructure check to pass
        mock_run.return_value = Mock(returncode=0, stdout="", stderr="")
        
        validator = Phase611Validator(check_only=True)
        success = validator.run_full_validation()
        
        assert success is True
        assert validator.report.overall_status == ValidationStatus.PASSED
        assert len(validator.report.steps) == 7  # All 7 steps
        
        # Verify steps 3-7 are skipped in check-only mode
        assert validator.report.steps[2].status == ValidationStatus.SKIPPED  # ETL
        assert validator.report.steps[3].status == ValidationStatus.SKIPPED  # Validation
        assert validator.report.steps[4].status == ValidationStatus.SKIPPED  # Seasonal
        assert validator.report.steps[5].status == ValidationStatus.SKIPPED  # Features
        assert validator.report.steps[6].status == ValidationStatus.SKIPPED  # Training
    
    @patch.dict(os.environ, {}, clear=True)
    @patch('subprocess.run')
    def test_full_workflow_stops_on_api_key_failure(self, mock_run):
        """Test that workflow stops if API keys are not configured"""
        validator = Phase611Validator(check_only=True)
        success = validator.run_full_validation()
        
        assert success is False
        assert validator.report.overall_status == ValidationStatus.FAILED
        assert len(validator.report.steps) == 1  # Only API keys check ran
        assert validator.report.steps[0].status == ValidationStatus.FAILED
    
    @patch.dict(os.environ, {
        "BLS_API_KEY": "test_key",
        "NOAA_API_TOKEN": "test_token"
    })
    @patch('subprocess.run')
    def test_full_workflow_stops_on_infrastructure_failure(self, mock_run):
        """Test that workflow stops if infrastructure is unhealthy"""
        # Mock infrastructure check to fail
        mock_run.return_value = Mock(returncode=1, stdout="", stderr="Services down")
        
        validator = Phase611Validator(check_only=True)
        success = validator.run_full_validation()
        
        assert success is False
        assert validator.report.overall_status == ValidationStatus.FAILED
        assert len(validator.report.steps) == 2  # API keys + infrastructure
        assert validator.report.steps[1].status == ValidationStatus.FAILED


class TestEdgeCases:
    """Test edge cases and error handling"""
    
    def test_output_directory_creation(self):
        """Test that output directory is created if it doesn't exist"""
        validator = Phase611Validator(check_only=True)
        
        assert validator.output_dir.exists()
        assert validator.output_dir.is_dir()
    
    @patch('subprocess.run', side_effect=Exception("Unexpected error"))
    def test_infrastructure_check_exception_handling(self, mock_run):
        """Test exception handling in infrastructure check"""
        validator = Phase611Validator(check_only=True)
        step = validator.check_infrastructure()
        
        assert step.status == ValidationStatus.FAILED
        assert "Unexpected error" in step.error_message
    
    def test_validation_id_uniqueness(self):
        """Test that each validator gets a unique validation ID"""
        validator1 = Phase611Validator(check_only=True)
        validator2 = Phase611Validator(check_only=True)
        
        assert validator1.report.validation_id != validator2.report.validation_id
    
    def test_duration_calculation(self):
        """Test that report duration is calculated correctly"""
        validator = Phase611Validator(check_only=True)
        
        # Manually set times for testing
        validator.report.started_at = "2025-01-01T00:00:00"
        validator.report.completed_at = "2025-01-01T00:01:30"
        
        json_path, md_path = validator.generate_final_report()
        
        assert validator.report.total_duration_seconds == 90.0
        
        # Cleanup
        json_path.unlink()
        md_path.unlink()


# Run tests if executed directly
if __name__ == "__main__":
    pytest.main([__file__, "-v"])

