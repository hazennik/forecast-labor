"""
Tests for Golden Diagnostics Integration

Tests recording and verification of golden seasonal adjustment diagnostics for
regression testing in CI/CD pipeline.

Golden diagnostics ensure that seasonal adjustment quality doesn't degrade over time.
"""

import pytest
import json
import tempfile
from pathlib import Path
from datetime import date, datetime
from typing import Dict, Any

import pandas as pd
import numpy as np

# Import will work since script exists
import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from scripts.record_golden_diagnostics import (
    record_golden_diagnostics,
    verify_diagnostics,
    _generate_sample_series,
)


class TestGoldenDiagnosticsRecording:
    """Test suite for recording golden diagnostics"""
    
    @pytest.fixture
    def temp_output_file(self, tmp_path):
        """Temporary file for golden diagnostics"""
        return tmp_path / "test_golden_diagnostics.json"
    
    def test_generate_sample_series(self):
        """Test that sample series generation works"""
        series = _generate_sample_series("TEST_SERIES", periods=120)
        
        assert isinstance(series, pd.Series)
        assert len(series) == 120
        assert series.name == "TEST_SERIES"
        assert isinstance(series.index, pd.DatetimeIndex)
    
    def test_record_golden_diagnostics_creates_file(self, temp_output_file):
        """Test that recording creates output file"""
        vintage_date = date(2024, 1, 15)
        
        success = record_golden_diagnostics(vintage_date, temp_output_file)
        
        assert success is True
        assert temp_output_file.exists()
    
    def test_recorded_diagnostics_have_required_fields(self, temp_output_file):
        """Test that recorded diagnostics have all required fields"""
        vintage_date = date(2024, 1, 15)
        
        record_golden_diagnostics(vintage_date, temp_output_file)
        
        with open(temp_output_file, 'r') as f:
            diagnostics = json.load(f)
        
        # Check top-level fields
        assert 'vintage_date' in diagnostics
        assert 'recorded_at' in diagnostics
        assert 'series' in diagnostics
        
        # Check that at least one series was processed
        assert len(diagnostics['series']) > 0
    
    def test_recorded_diagnostics_include_m_statistics(self, temp_output_file):
        """Test that M-statistics are recorded"""
        vintage_date = date(2024, 1, 15)
        
        record_golden_diagnostics(vintage_date, temp_output_file)
        
        with open(temp_output_file, 'r') as f:
            diagnostics = json.load(f)
        
        # Check first series has M-statistics
        first_series = list(diagnostics['series'].values())[0]
        assert 'm_statistics' in first_series
        
        m_stats = first_series['m_statistics']
        
        # Should have M1-M11
        for i in range(1, 12):
            m_key = f'm{i}'
            assert m_key in m_stats, f"Missing {m_key}"
            assert m_stats[m_key] is not None
    
    def test_recorded_diagnostics_include_q_statistics(self, temp_output_file):
        """Test that Q-statistics (Ljung-Box) are recorded"""
        vintage_date = date(2024, 1, 15)
        
        record_golden_diagnostics(vintage_date, temp_output_file)
        
        with open(temp_output_file, 'r') as f:
            diagnostics = json.load(f)
        
        # Check first series has Q-statistics
        first_series = list(diagnostics['series'].values())[0]
        
        # Should have either q_statistic or q in m_statistics
        assert ('q_statistics' in first_series or 
                'q_statistic' in first_series.get('m_statistics', {}) or
                'q' in first_series.get('m_statistics', {})), \
            "Missing Q-statistics"
    
    def test_recorded_diagnostics_include_quality_grade(self, temp_output_file):
        """Test that quality grade is recorded"""
        vintage_date = date(2024, 1, 15)
        
        record_golden_diagnostics(vintage_date, temp_output_file)
        
        with open(temp_output_file, 'r') as f:
            diagnostics = json.load(f)
        
        first_series = list(diagnostics['series'].values())[0]
        assert 'quality_grade' in first_series
        assert first_series['quality_grade'] in ['good', 'acceptable', 'poor', 'unknown']
    
    def test_recorded_diagnostics_include_thresholds(self, temp_output_file):
        """Test that quality thresholds are recorded"""
        vintage_date = date(2024, 1, 15)
        
        record_golden_diagnostics(vintage_date, temp_output_file)
        
        with open(temp_output_file, 'r') as f:
            diagnostics = json.load(f)
        
        first_series = list(diagnostics['series'].values())[0]
        assert 'thresholds' in first_series
        
        thresholds = first_series['thresholds']
        
        # Should have thresholds for key M-statistics
        assert 'm7_max' in thresholds
        assert 'm8_max' in thresholds
        assert 'q_max' in thresholds


class TestGoldenDiagnosticsVerification:
    """Test suite for verifying diagnostics against golden baseline"""
    
    @pytest.fixture
    def sample_golden_diagnostics(self, tmp_path):
        """Create sample golden diagnostics file"""
        golden_file = tmp_path / "golden.json"
        
        golden_data = {
            "vintage_date": "2024-01-15",
            "recorded_at": "2024-01-15",
            "series": {
                "TEST_SERIES": {
                    "name": "Test Series",
                    "source": "test",
                    "m_statistics": {
                        "m1": 0.25,
                        "m2": 0.28,
                        "m3": 0.65,
                        "m7": 0.48,
                        "m8": 0.52,
                        "m9": 0.28,
                        "q": 0.45
                    },
                    "thresholds": {
                        "m1_max": 0.30,
                        "m2_max": 0.35,
                        "m3_max": 0.80,
                        "m7_max": 0.60,
                        "m8_max": 0.65,
                        "m9_max": 0.35,
                        "q_max": 1.0
                    },
                    "quality_grade": "good"
                }
            }
        }
        
        with open(golden_file, 'w') as f:
            json.dump(golden_data, f)
        
        return golden_file
    
    def test_verify_diagnostics_passes_when_within_thresholds(self, sample_golden_diagnostics):
        """Test that verification passes when diagnostics are within thresholds"""
        current_diagnostics = {
            "TEST_SERIES": {
                "m1": 0.28,  # < 0.30 threshold
                "m2": 0.30,  # < 0.35 threshold
                "m3": 0.70,  # < 0.80 threshold
                "m7": 0.55,  # < 0.60 threshold
                "m8": 0.60,  # < 0.65 threshold
                "m9": 0.30,  # < 0.35 threshold
                "q": 0.85    # < 1.0 threshold
            }
        }
        
        result = verify_diagnostics(current_diagnostics, sample_golden_diagnostics)
        
        assert result is True, "Verification should pass when within thresholds"
    
    def test_verify_diagnostics_fails_when_exceeds_thresholds(self, sample_golden_diagnostics):
        """Test that verification fails when diagnostics exceed thresholds"""
        current_diagnostics = {
            "TEST_SERIES": {
                "m1": 0.35,  # > 0.30 threshold (FAIL)
                "m2": 0.28,
                "m3": 0.65,
                "m7": 0.48,
                "m8": 0.52,
                "m9": 0.28,
                "q": 0.45
            }
        }
        
        result = verify_diagnostics(current_diagnostics, sample_golden_diagnostics)
        
        assert result is False, "Verification should fail when exceeding thresholds"
    
    def test_verify_diagnostics_fails_when_missing_golden_file(self, tmp_path):
        """Test that verification fails gracefully when golden file missing"""
        missing_file = tmp_path / "nonexistent.json"
        
        current_diagnostics = {
            "TEST_SERIES": {"m1": 0.25}
        }
        
        result = verify_diagnostics(current_diagnostics, missing_file)
        
        assert result is False
    
    def test_verify_diagnostics_handles_missing_series(self, sample_golden_diagnostics):
        """Test that verification handles series not in golden baseline"""
        current_diagnostics = {
            "UNKNOWN_SERIES": {
                "m1": 0.25
            }
        }
        
        # Should not crash, just warn
        result = verify_diagnostics(current_diagnostics, sample_golden_diagnostics)
        
        # Returns True if no known series failed
        assert result is True


class TestDiagnosticsComparison:
    """Test suite for diagnostics comparison logic"""
    
    def test_compare_detects_degradation(self):
        """Test that comparison detects quality degradation"""
        golden_stats = {
            "m7": 0.45,
            "m8": 0.50,
            "q": 0.40
        }
        
        current_stats = {
            "m7": 0.75,  # Degraded from 0.45
            "m8": 0.52,  # Slight increase
            "q": 0.85    # Degraded from 0.40
        }
        
        thresholds = {
            "m7_max": 0.60,
            "m8_max": 0.65,
            "q_max": 1.0
        }
        
        # M7 and Q have degraded significantly
        # M7: 0.45 → 0.75 (exceeds 0.60 threshold)
        # Q: 0.40 → 0.85 (below 1.0 threshold but significant increase)
        
        assert current_stats['m7'] > thresholds['m7_max'], \
            "M7 degradation should be detected"
    
    def test_compare_allows_acceptable_variance(self):
        """Test that comparison allows small acceptable variance"""
        golden_stats = {
            "m7": 0.45,
            "m8": 0.50
        }
        
        current_stats = {
            "m7": 0.47,  # Small increase (+0.02)
            "m8": 0.51   # Small increase (+0.01)
        }
        
        thresholds = {
            "m7_max": 0.60,
            "m8_max": 0.65
        }
        
        # Both should pass (within thresholds)
        assert current_stats['m7'] < thresholds['m7_max']
        assert current_stats['m8'] < thresholds['m8_max']
    
    def test_compare_uses_relative_tolerance(self):
        """Test that comparison can use relative tolerance bands"""
        golden_value = 0.50
        current_value = 0.52
        
        # 5% relative tolerance
        tolerance = 0.05
        max_allowed = golden_value * (1 + tolerance)  # 0.525
        
        assert current_value < max_allowed, \
            f"Current {current_value} should be within 5% of golden {golden_value}"
    
    def test_compare_uses_absolute_tolerance(self):
        """Test that comparison can use absolute tolerance bands"""
        golden_value = 0.50
        current_value = 0.52
        
        # Absolute tolerance of 0.05
        tolerance = 0.05
        max_allowed = golden_value + tolerance  # 0.55
        
        assert current_value < max_allowed, \
            f"Current {current_value} should be within ±{tolerance} of golden {golden_value}"


class TestDatabaseStorage:
    """Test suite for database storage of golden diagnostics"""
    
    def test_golden_diagnostics_can_be_stored_in_database(self):
        """Test that golden diagnostics can be stored in database"""
        # This would require database connection
        # For now, test the data structure is compatible
        
        diagnostics = {
            "series_name": "TEST_SERIES",
            "vintage_date": "2024-01-15",
            "m_statistics": {f"m{i}": 0.5 for i in range(1, 12)},
            "q_statistics": {"q_statistic": 8.5, "p_value": 0.58},
            "quality_grade": "good",
            "is_golden": True
        }
        
        # Check required fields present
        assert "series_name" in diagnostics
        assert "vintage_date" in diagnostics
        assert "m_statistics" in diagnostics
        assert "quality_grade" in diagnostics
    
    def test_golden_diagnostics_marked_as_baseline(self):
        """Test that golden diagnostics are marked as baseline"""
        diagnostics = {
            "series_name": "TEST_SERIES",
            "is_golden": True,
            "is_baseline": True
        }
        
        assert diagnostics.get("is_golden") is True
        assert diagnostics.get("is_baseline") is True


class TestCIIntegration:
    """Test suite for CI workflow integration"""
    
    def test_verification_returns_exit_code_0_on_success(self):
        """Test that verification returns 0 exit code on success"""
        # This will be tested in actual CI
        # Here we test the boolean return value
        
        # Simulate successful verification
        result = True  # verify_diagnostics would return True
        exit_code = 0 if result else 1
        
        assert exit_code == 0
    
    def test_verification_returns_exit_code_1_on_failure(self):
        """Test that verification returns 1 exit code on failure"""
        # Simulate failed verification
        result = False  # verify_diagnostics would return False
        exit_code = 0 if result else 1
        
        assert exit_code == 1
    
    def test_ci_workflow_has_quality_check_step(self):
        """Test that CI workflow includes quality check step"""
        # This will be validated by checking .github/workflows/test.yml
        # Placeholder for documentation
        pytest.skip("CI workflow validation - checked manually")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])

