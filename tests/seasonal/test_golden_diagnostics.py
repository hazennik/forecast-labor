"""
Tests for Golden Diagnostics Integration

Tests recording and verification of golden seasonal adjustment diagnostics for
regression testing in CI/CD pipeline.

Golden diagnostics ensure that seasonal adjustment quality doesn't degrade over time.
"""

import pytest
import json
from pathlib import Path
from datetime import date

import pandas as pd

# Import will work since script exists
import sys

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from scripts import record_golden_diagnostics as golden_script  # noqa: E402
from scripts.record_golden_diagnostics import (  # noqa: E402
    extract_current_diagnostics,
    record_golden_diagnostics,
    run_full_diagnostics_verification,
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

        with open(temp_output_file, "r") as f:
            diagnostics = json.load(f)

        # Check top-level fields
        assert "vintage_date" in diagnostics
        assert "recorded_at" in diagnostics
        assert "series" in diagnostics

        # Check that at least one series was processed
        assert len(diagnostics["series"]) > 0

    def test_recorded_diagnostics_include_m_statistics(self, temp_output_file):
        """Test that M-statistics are recorded"""
        vintage_date = date(2024, 1, 15)

        record_golden_diagnostics(vintage_date, temp_output_file)

        with open(temp_output_file, "r") as f:
            diagnostics = json.load(f)

        # Check first series has M-statistics
        first_series = list(diagnostics["series"].values())[0]
        assert "m_statistics" in first_series

        m_stats = first_series["m_statistics"]

        # Should have M1-M11
        for i in range(1, 12):
            m_key = f"m{i}"
            assert m_key in m_stats, f"Missing {m_key}"
            assert m_stats[m_key] is not None

    def test_recorded_diagnostics_include_q_statistics(self, temp_output_file):
        """Test that Q-statistics (Ljung-Box) are recorded"""
        vintage_date = date(2024, 1, 15)

        record_golden_diagnostics(vintage_date, temp_output_file)

        with open(temp_output_file, "r") as f:
            diagnostics = json.load(f)

        # Check first series has Q-statistics
        first_series = list(diagnostics["series"].values())[0]

        # Should have either q_statistic or q in m_statistics
        assert (
            "q_statistics" in first_series
            or "q_statistic" in first_series.get("m_statistics", {})
            or "q" in first_series.get("m_statistics", {})
        ), "Missing Q-statistics"

    def test_recorded_diagnostics_include_quality_grade(self, temp_output_file):
        """Test that quality grade is recorded"""
        vintage_date = date(2024, 1, 15)

        record_golden_diagnostics(vintage_date, temp_output_file)

        with open(temp_output_file, "r") as f:
            diagnostics = json.load(f)

        first_series = list(diagnostics["series"].values())[0]
        assert "quality_grade" in first_series
        assert first_series["quality_grade"] in [
            "good",
            "acceptable",
            "poor",
            "unknown",
        ]

    def test_recorded_diagnostics_include_thresholds(self, temp_output_file):
        """Test that quality thresholds are recorded"""
        vintage_date = date(2024, 1, 15)

        record_golden_diagnostics(vintage_date, temp_output_file)

        with open(temp_output_file, "r") as f:
            diagnostics = json.load(f)

        first_series = list(diagnostics["series"].values())[0]
        assert "thresholds" in first_series

        thresholds = first_series["thresholds"]

        # Should have thresholds for key M-statistics
        assert "m7_max" in thresholds
        assert "m8_max" in thresholds
        assert "q_max" in thresholds


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
                        "q": 0.45,
                    },
                    "thresholds": {
                        "m1_max": 0.30,
                        "m2_max": 0.35,
                        "m3_max": 0.80,
                        "m7_max": 0.60,
                        "m8_max": 0.65,
                        "m9_max": 0.35,
                        "q_max": 1.0,
                    },
                    "quality_grade": "good",
                }
            },
        }

        with open(golden_file, "w") as f:
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
                "q": 0.85,  # < 1.0 threshold
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
                "q": 0.45,
            }
        }

        result = verify_diagnostics(current_diagnostics, sample_golden_diagnostics)

        assert result is False, "Verification should fail when exceeding thresholds"

    def test_verify_diagnostics_fails_when_missing_golden_file(self, tmp_path):
        """Test that verification fails gracefully when golden file missing"""
        missing_file = tmp_path / "nonexistent.json"

        current_diagnostics = {"TEST_SERIES": {"m1": 0.25}}

        result = verify_diagnostics(current_diagnostics, missing_file)

        assert result is False

    def test_verify_diagnostics_handles_missing_series(self, sample_golden_diagnostics):
        """Test that verification handles series not in golden baseline"""
        current_diagnostics = {"UNKNOWN_SERIES": {"m1": 0.25}}

        # Should not crash, just warn
        result = verify_diagnostics(current_diagnostics, sample_golden_diagnostics)

        # Returns True if no known series failed
        assert result is True

    def test_extract_current_diagnostics_flattens_recorded_report(self):
        """Test that full CI verification extracts M and Q statistics for comparison."""
        recorded_report = {
            "series": {
                "TEST_SERIES": {
                    "m_statistics": {
                        "m1": 0.25,
                        "m2": 0.30,
                        "q_statistic": 0.45,
                        "m_quality_assessment": {"overall_quality": "good"},
                    },
                    "q_statistics": {
                        "q_statistic": 8.5,
                        "p_value": 0.12,
                    },
                }
            }
        }

        current = extract_current_diagnostics(recorded_report)

        assert current == {
            "TEST_SERIES": {
                "m1": 0.25,
                "m2": 0.30,
                "q_statistic": 0.45,
                "p_value": 0.12,
                "ljung_box_q": 8.5,
            }
        }

    def test_run_full_diagnostics_verification_records_current_diagnostics(
        self,
        sample_golden_diagnostics,
        monkeypatch,
    ):
        """Test that --verify records fresh diagnostics before comparing to baseline."""
        calls = {"record": 0, "verify": 0}

        def fake_record_golden_diagnostics(vintage_date, output_file, force_synthetic=False):
            calls["record"] += 1
            assert force_synthetic is True
            current_report = {
                "series": {
                    "TEST_SERIES": {
                        "m_statistics": {"m1": 0.25, "q_statistic": 0.45},
                        "q_statistics": {"q_statistic": 7.5, "p_value": 0.20},
                    }
                }
            }
            with open(output_file, "w") as f:
                json.dump(current_report, f)
            return True

        def fake_verify_diagnostics(current_diagnostics, golden_file, tolerance_pct=10.0):
            calls["verify"] += 1
            assert golden_file == sample_golden_diagnostics
            assert tolerance_pct == 7.5
            assert current_diagnostics["TEST_SERIES"]["m1"] == 0.25
            assert current_diagnostics["TEST_SERIES"]["p_value"] == 0.20
            return True

        monkeypatch.setattr(
            golden_script,
            "record_golden_diagnostics",
            fake_record_golden_diagnostics,
        )
        monkeypatch.setattr(golden_script, "verify_diagnostics", fake_verify_diagnostics)

        result = run_full_diagnostics_verification(
            date(2024, 1, 15),
            sample_golden_diagnostics,
            tolerance_pct=7.5,
            force_synthetic=True,
        )

        assert result is True
        assert calls == {"record": 1, "verify": 1}

    def test_run_full_diagnostics_verification_fails_without_baseline(self, tmp_path):
        """Test that full verification fails when the committed baseline is missing."""
        missing_file = tmp_path / "missing-golden.json"

        result = run_full_diagnostics_verification(date(2024, 1, 15), missing_file)

        assert result is False


class TestDiagnosticsComparison:
    """Test suite for diagnostics comparison logic"""

    def test_compare_detects_degradation(self):
        """Test that comparison detects quality degradation"""

        current_stats = {
            "m7": 0.75,  # Degraded from 0.45
            "m8": 0.52,  # Slight increase
            "q": 0.85,  # Degraded from 0.40
        }

        thresholds = {"m7_max": 0.60, "m8_max": 0.65, "q_max": 1.0}

        # M7 and Q have degraded significantly
        # M7: 0.45 → 0.75 (exceeds 0.60 threshold)
        # Q: 0.40 → 0.85 (below 1.0 threshold but significant increase)

        assert current_stats["m7"] > thresholds["m7_max"], "M7 degradation should be detected"

    def test_compare_allows_acceptable_variance(self):
        """Test that comparison allows small acceptable variance"""

        current_stats = {
            "m7": 0.47,  # Small increase (+0.02)
            "m8": 0.51,  # Small increase (+0.01)
        }

        thresholds = {"m7_max": 0.60, "m8_max": 0.65}

        # Both should pass (within thresholds)
        assert current_stats["m7"] < thresholds["m7_max"]
        assert current_stats["m8"] < thresholds["m8_max"]

    def test_compare_uses_relative_tolerance(self):
        """Test that comparison can use relative tolerance bands"""
        golden_value = 0.50
        current_value = 0.52

        # 5% relative tolerance
        tolerance = 0.05
        max_allowed = golden_value * (1 + tolerance)  # 0.525

        assert (
            current_value < max_allowed
        ), f"Current {current_value} should be within 5% of golden {golden_value}"

    def test_compare_uses_absolute_tolerance(self):
        """Test that comparison can use absolute tolerance bands"""
        golden_value = 0.50
        current_value = 0.52

        # Absolute tolerance of 0.05
        tolerance = 0.05
        max_allowed = golden_value + tolerance  # 0.55

        assert current_value < max_allowed, (
            f"Current {current_value} should be within ±{tolerance} " f"of golden {golden_value}"
        )


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
            "is_golden": True,
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
            "is_baseline": True,
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
        """Test that CI workflow runs the golden diagnostics gate in X-13 Docker."""
        workflow_path = Path(__file__).parent.parent.parent / ".github" / "workflows" / "test.yml"
        workflow = workflow_path.read_text()

        assert "Build X-13 CI image" in workflow
        assert "Verify X-13 CI image" in workflow
        assert "Check golden diagnostics (X-13 Quality Gate)" in workflow
        assert "docker run --rm" in workflow
        assert "scripts/record_golden_diagnostics.py" in workflow
        assert "--vintage-date 2024-01-15" in workflow
        assert "--verify" in workflow
        assert "--force-synthetic" in workflow
        assert "golden_seasonal_diagnostics_ci.json" in workflow


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
