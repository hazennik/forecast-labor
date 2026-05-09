"""
Integration Test for Golden Diagnostics Workflow

Tests the end-to-end workflow of recording and verifying golden diagnostics,
integrating X-13 seasonal adjustment, M-statistics, Q-statistics, and database storage.

This validates Phase 5.11.3: Golden Diagnostics Integration
"""

import pytest
import json
from pathlib import Path
from datetime import date
import sys

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from scripts.record_golden_diagnostics import (
    record_golden_diagnostics,
    verify_diagnostics,
)


class TestGoldenDiagnosticsWorkflowIntegration:
    """End-to-end integration tests for golden diagnostics workflow"""

    @pytest.fixture
    def temp_golden_file(self, tmp_path):
        """Temporary golden diagnostics file"""
        return tmp_path / "golden_diagnostics.json"

    def test_end_to_end_record_and_verify_workflow(self, temp_golden_file):
        """
        Test the complete workflow:
        1. Record golden diagnostics from X-13 seasonal adjustment
        2. Verify current diagnostics against golden baseline
        3. Ensure quality gates are operational
        """
        vintage_date = date(2024, 1, 15)

        # Step 1: Record golden diagnostics
        print("\n=== STEP 1: Recording Golden Diagnostics ===")
        success = record_golden_diagnostics(vintage_date, temp_golden_file)

        assert success is True, "Recording should succeed"
        assert temp_golden_file.exists(), "Golden file should be created"

        # Step 2: Load and validate structure
        print("\n=== STEP 2: Validating Golden File Structure ===")
        with open(temp_golden_file, "r") as f:
            golden = json.load(f)

        assert "vintage_date" in golden
        assert "recorded_at" in golden
        assert "series" in golden
        assert len(golden["series"]) > 0, "Should have processed at least one series"

        # Step 3: Validate diagnostics content
        print("\n=== STEP 3: Validating Diagnostics Content ===")
        for series_id, series_data in golden["series"].items():
            print(f"\nChecking {series_id}:")

            # Check required fields
            assert "name" in series_data
            assert "source" in series_data
            assert "m_statistics" in series_data
            assert "thresholds" in series_data
            assert "quality_grade" in series_data

            # Check M-statistics (M1-M11)
            m_stats = series_data["m_statistics"]
            for i in range(1, 12):
                m_key = f"m{i}"
                assert m_key in m_stats, f"Missing {m_key}"
                assert m_stats[m_key] is not None, f"{m_key} should not be None"
                print(f"  ✅ {m_key.upper()}: {m_stats[m_key]:.3f}")

            # Check Q-statistic
            assert "q_statistic" in m_stats or "q" in m_stats, "Missing Q-statistic"
            q_val = m_stats.get("q_statistic") or m_stats.get("q")
            print(f"  ✅ Q-STAT: {q_val:.3f}")

            # Check Q-statistics (Ljung-Box) if available
            if "q_statistics" in series_data:
                q_stats = series_data["q_statistics"]
                if q_stats.get("q_statistic") is not None:
                    print(f"  ✅ Ljung-Box Q: {q_stats['q_statistic']:.3f}")
                if q_stats.get("p_value") is not None:
                    print(f"  ✅ Ljung-Box p: {q_stats['p_value']:.4f}")

            # Check quality assessment
            assert series_data["quality_grade"] in ["good", "acceptable", "poor", "unknown"]
            print(f"  ✅ Quality Grade: {series_data['quality_grade']}")

        # Step 4: Verify against golden baseline (should pass with same data)
        print("\n=== STEP 4: Verification Against Golden Baseline ===")

        # Create current diagnostics from golden (simulating no degradation)
        current_diagnostics = {}
        for series_id, series_data in golden["series"].items():
            m_stats = series_data["m_statistics"]
            q_stats = series_data.get("q_statistics", {})

            current_diagnostics[series_id] = {
                **{k: v for k, v in m_stats.items() if k.startswith("m") or k == "q_statistic"},
                "p_value": q_stats.get("p_value"),
                "ljung_box_q": q_stats.get("q_statistic"),
            }

        # Verification should pass (no degradation)
        result = verify_diagnostics(current_diagnostics, temp_golden_file, tolerance_pct=10.0)
        assert result is True, "Verification should pass with same diagnostics"

        print("\n=== WORKFLOW COMPLETE ===")
        print(f"✅ Recorded {len(golden['series'])} series")
        print("✅ Verified all series against baseline")
        print("✅ Quality gates operational")

    def test_workflow_detects_quality_degradation(self, temp_golden_file):
        """
        Test that the workflow detects quality degradation:
        1. Record baseline
        2. Simulate degraded diagnostics
        3. Verify that verification fails
        """
        vintage_date = date(2024, 1, 15)

        # Record baseline
        print("\n=== Recording Baseline ===")
        success = record_golden_diagnostics(vintage_date, temp_golden_file)
        assert success is True

        with open(temp_golden_file, "r") as f:
            golden = json.load(f)

        # Simulate degraded diagnostics (M7 exceeds threshold)
        print("\n=== Simulating Quality Degradation ===")
        degraded_diagnostics = {}

        for series_id, series_data in golden["series"].items():
            m_stats = series_data["m_statistics"]
            thresholds = series_data["thresholds"]

            # Degrade M7 to exceed threshold
            degraded_m7 = thresholds.get("m7_max", 1.0) + 0.1  # Exceed threshold by 0.1

            degraded_diagnostics[series_id] = {
                "m1": m_stats.get("m1", 0.5),
                "m2": m_stats.get("m2", 0.5),
                "m3": m_stats.get("m3", 0.5),
                "m4": m_stats.get("m4", 0.5),
                "m5": m_stats.get("m5", 0.5),
                "m6": m_stats.get("m6", 0.5),
                "m7": degraded_m7,  # DEGRADED
                "m8": m_stats.get("m8", 0.5),
                "m9": m_stats.get("m9", 0.5),
                "m10": m_stats.get("m10", 0.5),
                "m11": m_stats.get("m11", 0.5),
            }

            print(f"Series {series_id}:")
            print(f"  M7 degraded: {m_stats.get('m7', 0.5):.3f} → {degraded_m7:.3f}")
            print(f"  Threshold: {thresholds.get('m7_max', 1.0):.3f}")

        # Verification should fail (quality degraded)
        print("\n=== Running Verification (Should Fail) ===")
        result = verify_diagnostics(degraded_diagnostics, temp_golden_file, tolerance_pct=10.0)

        assert result is False, "Verification should fail with degraded diagnostics"
        print("\n✅ Quality degradation correctly detected")

    def test_workflow_handles_missing_series_gracefully(self, temp_golden_file):
        """Test that workflow handles missing series in current diagnostics"""
        vintage_date = date(2024, 1, 15)

        # Record baseline
        success = record_golden_diagnostics(vintage_date, temp_golden_file)
        assert success is True

        # Verify with empty current diagnostics (all series missing)
        current_diagnostics = {}

        # Should not crash, just warn
        result = verify_diagnostics(current_diagnostics, temp_golden_file)

        # Returns True if no known series failed (they're just missing)
        assert result is True

    def test_workflow_uses_tolerance_bands(self, temp_golden_file):
        """Test that workflow allows small variations within tolerance bands"""
        vintage_date = date(2024, 1, 15)

        # Record baseline
        success = record_golden_diagnostics(vintage_date, temp_golden_file)
        assert success is True

        with open(temp_golden_file, "r") as f:
            golden = json.load(f)

        # Create slightly degraded diagnostics (within 10% tolerance)
        print("\n=== Testing Tolerance Bands ===")
        slightly_degraded = {}

        for series_id, series_data in golden["series"].items():
            m_stats = series_data["m_statistics"]

            # Increase all M-stats by 5% (within 10% tolerance)
            slightly_degraded[series_id] = {
                f"m{i}": m_stats.get(f"m{i}", 0.5) * 1.05 for i in range(1, 12)
            }

            print(f"Series {series_id}:")
            print(
                f"  M1: {m_stats.get('m1', 0.5):.3f} → {slightly_degraded[series_id]['m1']:.3f} (+5%)"
            )

        # Verification should pass (within tolerance)
        result = verify_diagnostics(slightly_degraded, temp_golden_file, tolerance_pct=10.0)

        assert result is True, "Verification should pass with 5% degradation (within 10% tolerance)"
        print("\n✅ Tolerance bands working correctly")


class TestGoldenDiagnosticsCIIntegration:
    """Test CI/CD integration scenarios"""

    def test_ci_workflow_simulation(self, tmp_path):
        """Simulate CI workflow: record baseline once, verify on every commit"""
        vintage_date = date(2024, 1, 15)
        golden_file = tmp_path / "golden.json"

        # === ONE-TIME: Record baseline (manual step or first CI run) ===
        print("\n=== ONE-TIME: Recording Golden Baseline ===")
        success = record_golden_diagnostics(vintage_date, golden_file)
        assert success is True
        print("✅ Baseline recorded and committed to git")

        # === EVERY COMMIT: Verify current code against baseline ===
        print("\n=== EVERY COMMIT: Verifying Against Baseline ===")

        # Simulate running X-13 with current code
        success_current = record_golden_diagnostics(vintage_date, tmp_path / "current.json")
        assert success_current is True

        # Load current diagnostics
        with open(tmp_path / "current.json", "r") as f:
            current = json.load(f)

        # Extract diagnostics for verification
        current_diagnostics = {}
        for series_id, series_data in current["series"].items():
            m_stats = series_data["m_statistics"]
            q_stats = series_data.get("q_statistics", {})

            current_diagnostics[series_id] = {
                **{k: v for k, v in m_stats.items() if k.startswith("m") or k == "q_statistic"},
                "p_value": q_stats.get("p_value"),
            }

        # Verify against baseline
        result = verify_diagnostics(current_diagnostics, golden_file, tolerance_pct=10.0)

        if result:
            print("✅ CI PASSED: Seasonal adjustment quality maintained")
        else:
            print("❌ CI FAILED: Seasonal adjustment quality degraded")

        assert result is True, "CI should pass with no code changes"

    def test_baseline_update_workflow(self, tmp_path):
        """Test workflow for updating baselines after legitimate code changes"""
        vintage_date = date(2024, 1, 15)
        baseline_file = tmp_path / "golden.json"

        # Record initial baseline
        print("\n=== Initial Baseline ===")
        record_golden_diagnostics(vintage_date, baseline_file)

        # Simulate code improvement (better diagnostics)
        print("\n=== After Code Improvement ===")
        # In reality, this would come from improved X-13 specs or better data
        # For testing, we record to a new file
        improved_file = tmp_path / "improved.json"
        record_golden_diagnostics(vintage_date, improved_file)

        with open(improved_file, "r") as f:
            improved = json.load(f)

        # Extract improved diagnostics
        improved_diagnostics = {}
        for series_id, series_data in improved["series"].items():
            m_stats = series_data["m_statistics"]
            # Simulate 10% improvement in all stats
            improved_diagnostics[series_id] = {
                f"m{i}": m_stats.get(f"m{i}", 0.5) * 0.90 for i in range(1, 12)  # 10% better
            }

        # Verify against old baseline (might fail due to changes)
        verify_diagnostics(improved_diagnostics, baseline_file, tolerance_pct=10.0)

        # If changes are legitimate, developer should:
        # 1. Review diagnostic changes
        # 2. Run: make regenerate-baselines
        # 3. Commit updated baseline files

        print("\n=== Workflow Steps ===")
        print("1. Review diagnostic changes (ensure improvement, not degradation)")
        print("2. Run: make regenerate-baselines")
        print("3. Commit updated baseline files to git")
        print("4. CI will now use new baseline for future commits")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short", "-s"])
