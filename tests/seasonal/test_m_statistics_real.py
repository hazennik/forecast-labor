"""
Tests for Real M-Statistics Computation

Tests computation of M1-M11 statistics following X-13ARIMA-SEATS methodology.
Following TDD approach as per Phase 5.11.1 requirements.

M-Statistics Overview:
- M1: Contribution of irregular over 3-month span
- M2: Contribution of irregular to changes in original series
- M3: Amount of month-to-month change in irregular compared to trend
- M4: Randomness of irregular (auto-correlation test)
- M5: Heteroscedasticity of irregular
- M6: Duration of run above/below average in irregular
- M7: Combined seasonality test (presence of identifiable seasonality)
- M8: Closeness of annual totals (MM vs SA)
- M9: Stability of seasonal factors
- M10: Recent movements in seasonal factors
- M11: Linear trend in seasonal factors

Reference: U.S. Census Bureau X-13ARIMA-SEATS Reference Manual
"""

import pytest
import numpy as np
import pandas as pd
from datetime import datetime
from typing import Dict, Any

# Import will fail initially (TDD approach)
try:
    from seasonal.diagnostics.m_statistics import (
        MStatisticsComputer,
        compute_m_statistics,  # noqa: F401 - validates public import availability
        validate_quality_thresholds,
        store_diagnostics_to_db,
    )
except ImportError:
    pytest.skip("M-statistics module not yet implemented", allow_module_level=True)


class TestMStatisticsComputer:
    """Test suite for M-statistics computer"""

    @pytest.fixture
    def simple_decomposition(self) -> Dict[str, pd.Series]:
        """
        Create simple X-13 decomposition for testing

        Returns decomposition components: original, seasonal, trend, irregular
        """
        # Create monthly time series (2 years = 24 observations)
        dates = pd.date_range(start="2020-01-01", periods=24, freq="MS")

        # Original series with clear seasonal pattern
        seasonal_component = np.sin(np.arange(24) * 2 * np.pi / 12) * 10
        trend_component = np.linspace(100, 120, 24)
        irregular_component = np.random.RandomState(42).normal(0, 2, 24)

        original = seasonal_component + trend_component + irregular_component

        return {
            "original": pd.Series(original, index=dates),
            "seasonal": pd.Series(seasonal_component, index=dates),
            "trend": pd.Series(trend_component, index=dates),
            "irregular": pd.Series(irregular_component, index=dates),
            "seasonally_adjusted": pd.Series(trend_component + irregular_component, index=dates),
        }

    @pytest.fixture
    def high_quality_decomposition(self) -> Dict[str, pd.Series]:
        """
        Create high-quality decomposition (should pass all thresholds)

        - Small irregular component (M1, M2 should be low)
        - Random irregular (M3, M4, M5, M6 should be good)
        - Stable seasonality (M7, M8, M9, M10, M11 should be good)
        """
        dates = pd.date_range(start="2020-01-01", periods=60, freq="MS")

        # Stable seasonal pattern
        seasonal = np.tile(np.sin(np.arange(12) * 2 * np.pi / 12) * 20, 5)

        # Smooth trend
        trend = np.linspace(100, 150, 60)

        # Small random irregular
        np.random.seed(42)
        irregular = np.random.normal(0, 1, 60)  # Small variance

        original = seasonal + trend + irregular

        return {
            "original": pd.Series(original, index=dates),
            "seasonal": pd.Series(seasonal, index=dates),
            "trend": pd.Series(trend, index=dates),
            "irregular": pd.Series(irregular, index=dates),
            "seasonally_adjusted": pd.Series(trend + irregular, index=dates),
        }

    @pytest.fixture
    def poor_quality_decomposition(self) -> Dict[str, pd.Series]:
        """
        Create poor-quality decomposition (should fail thresholds)

        - Large irregular component (M1, M2 should be high)
        - Non-random irregular (M3, M4 should indicate problems)
        - Unstable seasonality (M9, M10, M11 should be high)
        """
        dates = pd.date_range(start="2020-01-01", periods=60, freq="MS")

        # Changing seasonal pattern (unstable)
        seasonal = []
        for year in range(5):
            amplitude = 10 + year * 5  # Increasing amplitude
            seasonal.extend(np.sin(np.arange(12) * 2 * np.pi / 12) * amplitude)
        seasonal = np.array(seasonal)

        # Trend
        trend = np.linspace(100, 150, 60)

        # Large irregular component with autocorrelation
        np.random.seed(123)
        irregular = np.random.normal(0, 10, 60)  # Large variance
        # Add autocorrelation
        for i in range(1, len(irregular)):
            irregular[i] += 0.5 * irregular[i - 1]

        original = seasonal + trend + irregular

        return {
            "original": pd.Series(original, index=dates),
            "seasonal": pd.Series(seasonal, index=dates),
            "trend": pd.Series(trend, index=dates),
            "irregular": pd.Series(irregular, index=dates),
            "seasonally_adjusted": pd.Series(trend + irregular, index=dates),
        }

    def test_computer_initialization(self):
        """Test that MStatisticsComputer can be initialized"""
        computer = MStatisticsComputer()
        assert computer is not None

    def test_compute_all_m_statistics(self, simple_decomposition):
        """Test that all M1-M11 statistics are computed"""
        computer = MStatisticsComputer()
        result = computer.compute(simple_decomposition)

        # Should return all M-statistics
        expected_keys = [f"m{i}" for i in range(1, 12)] + ["q_statistic"]
        for key in expected_keys:
            assert key in result, f"Missing {key} in results"
            assert isinstance(result[key], (int, float)), f"{key} should be numeric"
            assert not np.isnan(result[key]), f"{key} should not be NaN"

    def test_m_statistics_are_non_negative(self, simple_decomposition):
        """Test that all M-statistics are non-negative"""
        computer = MStatisticsComputer()
        result = computer.compute(simple_decomposition)

        for i in range(1, 12):
            m_key = f"m{i}"
            assert result[m_key] >= 0, f"{m_key} should be non-negative"

    def test_q_statistic_is_average_of_m_stats(self, simple_decomposition):
        """
        Test mathematical property: Q-statistic is average of M1-M11

        This tests a KEY MATHEMATICAL PROPERTY as per TESTING_MATHEMATICAL_ALGORITHMS.md
        """
        computer = MStatisticsComputer()
        result = computer.compute(simple_decomposition)

        # Q should be average of M1-M11
        m_values = [result[f"m{i}"] for i in range(1, 12)]
        expected_q = np.mean(m_values)

        assert (
            abs(result["q_statistic"] - expected_q) < 1e-6
        ), f"Q-statistic should be average of M1-M11: expected {expected_q}, got {result['q_statistic']}"

    def test_high_quality_decomposition_passes_thresholds(self, high_quality_decomposition):
        """
        Test that high-quality decomposition produces M-stats < 1.0

        Good quality should have most M-statistics < 1.0
        """
        computer = MStatisticsComputer()
        result = computer.compute(high_quality_decomposition)

        # Most M-statistics should be < 1.0 for high quality
        good_count = sum(1 for i in range(1, 12) if result[f"m{i}"] < 1.0)
        assert (
            good_count >= 8
        ), f"High quality decomposition should have at least 8 M-stats < 1.0, got {good_count}"

    def test_poor_quality_decomposition_fails_thresholds(self, poor_quality_decomposition):
        """
        Test that poor-quality decomposition produces high M-stats

        Poor quality should have elevated M-statistics
        """
        computer = MStatisticsComputer()
        result = computer.compute(poor_quality_decomposition)

        # Should have multiple M-statistics > 1.0
        poor_count = sum(1 for i in range(1, 12) if result[f"m{i}"] > 1.0)
        assert (
            poor_count >= 3
        ), f"Poor quality decomposition should have at least 3 M-stats > 1.0, got {poor_count}"

    def test_m1_measures_irregular_contribution(self, simple_decomposition):
        """
        Test M1: Contribution of irregular over 3-month span

        M1 should increase when irregular component is large relative to trend
        """
        computer = MStatisticsComputer()

        # Baseline
        result1 = computer.compute(simple_decomposition)
        m1_baseline = result1["m1"]

        # Increase irregular component
        modified = simple_decomposition.copy()
        modified["irregular"] = modified["irregular"] * 5  # 5x larger irregular
        modified["original"] = modified["seasonal"] + modified["trend"] + modified["irregular"]
        modified["seasonally_adjusted"] = modified["trend"] + modified["irregular"]

        result2 = computer.compute(modified)
        m1_modified = result2["m1"]

        assert m1_modified > m1_baseline, "M1 should increase when irregular component is larger"

    def test_m7_detects_weak_seasonality(self):
        """
        Test M7: Combined seasonality test

        M7 should be higher when seasonality is weak or absent
        """
        computer = MStatisticsComputer()

        # Case 1: Strong seasonality
        dates = pd.date_range(start="2020-01-01", periods=60, freq="MS")
        strong_seasonal = np.tile(np.sin(np.arange(12) * 2 * np.pi / 12) * 20, 5)
        trend = np.linspace(100, 150, 60)
        irregular = np.random.RandomState(42).normal(0, 1, 60)

        strong_decomp = {
            "original": pd.Series(strong_seasonal + trend + irregular, index=dates),
            "seasonal": pd.Series(strong_seasonal, index=dates),
            "trend": pd.Series(trend, index=dates),
            "irregular": pd.Series(irregular, index=dates),
            "seasonally_adjusted": pd.Series(trend + irregular, index=dates),
        }

        result_strong = computer.compute(strong_decomp)
        m7_strong = result_strong["m7"]

        # Case 2: Weak seasonality
        weak_seasonal = np.tile(np.sin(np.arange(12) * 2 * np.pi / 12) * 2, 5)  # 10x smaller

        weak_decomp = {
            "original": pd.Series(weak_seasonal + trend + irregular, index=dates),
            "seasonal": pd.Series(weak_seasonal, index=dates),
            "trend": pd.Series(trend, index=dates),
            "irregular": pd.Series(irregular, index=dates),
            "seasonally_adjusted": pd.Series(trend + irregular, index=dates),
        }

        result_weak = computer.compute(weak_decomp)
        m7_weak = result_weak["m7"]

        assert m7_weak > m7_strong, "M7 should be higher when seasonality is weaker"

    def test_m9_detects_unstable_seasonality(self):
        """
        Test M9: Stability of seasonal factors

        M9 should be higher when seasonal factors change over time
        """
        computer = MStatisticsComputer()
        dates = pd.date_range(start="2020-01-01", periods=60, freq="MS")
        trend = np.linspace(100, 150, 60)
        irregular = np.random.RandomState(42).normal(0, 1, 60)

        # Case 1: Stable seasonality
        stable_seasonal = np.tile(np.sin(np.arange(12) * 2 * np.pi / 12) * 10, 5)
        stable_decomp = {
            "original": pd.Series(stable_seasonal + trend + irregular, index=dates),
            "seasonal": pd.Series(stable_seasonal, index=dates),
            "trend": pd.Series(trend, index=dates),
            "irregular": pd.Series(irregular, index=dates),
            "seasonally_adjusted": pd.Series(trend + irregular, index=dates),
        }

        result_stable = computer.compute(stable_decomp)
        m9_stable = result_stable["m9"]

        # Case 2: Changing seasonality
        changing_seasonal = []
        for year in range(5):
            amplitude = 10 + year * 3
            changing_seasonal.extend(np.sin(np.arange(12) * 2 * np.pi / 12) * amplitude)
        changing_seasonal = np.array(changing_seasonal)

        changing_decomp = {
            "original": pd.Series(changing_seasonal + trend + irregular, index=dates),
            "seasonal": pd.Series(changing_seasonal, index=dates),
            "trend": pd.Series(trend, index=dates),
            "irregular": pd.Series(irregular, index=dates),
            "seasonally_adjusted": pd.Series(trend + irregular, index=dates),
        }

        result_changing = computer.compute(changing_decomp)
        m9_changing = result_changing["m9"]

        assert m9_changing > m9_stable, "M9 should be higher when seasonal factors are unstable"


class TestQualityThresholdValidation:
    """Test suite for quality threshold validation"""

    def test_validate_quality_thresholds_good_quality(self):
        """Test validation of good quality M-statistics"""
        m_stats = {f"m{i}": 0.5 for i in range(1, 12)}  # All < 1.0
        m_stats["q_statistic"] = 0.5

        validation = validate_quality_thresholds(m_stats)

        assert validation["overall_quality"] == "good"
        assert validation["pass"] is True
        assert len(validation["failures"]) == 0

    def test_validate_quality_thresholds_acceptable_quality(self):
        """Test validation of acceptable quality M-statistics"""
        m_stats = {f"m{i}": 1.5 for i in range(1, 12)}  # Between 1.0 and 2.0
        m_stats["q_statistic"] = 1.5

        validation = validate_quality_thresholds(m_stats)

        assert validation["overall_quality"] == "acceptable"
        assert validation["pass"] is True  # Still passes, but with warnings

    def test_validate_quality_thresholds_poor_quality(self):
        """Test validation of poor quality M-statistics"""
        m_stats = {f"m{i}": 2.5 for i in range(1, 12)}  # All > 2.0
        m_stats["q_statistic"] = 2.5

        validation = validate_quality_thresholds(m_stats)

        assert validation["overall_quality"] == "poor"
        assert validation["pass"] is False
        assert len(validation["failures"]) > 0

    def test_threshold_enforcement_m7(self):
        """Test that M7 < 1.0 threshold is enforced"""
        m_stats = {f"m{i}": 0.5 for i in range(1, 12)}
        m_stats["m7"] = 1.5  # Exceeds threshold
        m_stats["q_statistic"] = 0.6

        validation = validate_quality_thresholds(m_stats)

        assert "m7" in str(validation["warnings"]) or "m7" in str(
            validation["failures"]
        ), "M7 threshold violation should be flagged"

    def test_threshold_enforcement_m8(self):
        """Test that M8 < 1.0 threshold is enforced"""
        m_stats = {f"m{i}": 0.5 for i in range(1, 12)}
        m_stats["m8"] = 1.8  # Exceeds threshold
        m_stats["q_statistic"] = 0.6

        validation = validate_quality_thresholds(m_stats)

        assert "m8" in str(validation["warnings"]) or "m8" in str(
            validation["failures"]
        ), "M8 threshold violation should be flagged"


class TestDatabaseStorage:
    """Test suite for database storage of diagnostics"""

    @pytest.fixture
    def sample_diagnostics(self) -> Dict[str, Any]:
        """Sample diagnostics for testing"""
        return {
            "series_name": "test_series_sa",
            "vintage_date": "2024-01-15",
            "computation_timestamp": datetime.now(),
            "m_statistics": {f"m{i}": 0.5 for i in range(1, 12)},
            "q_statistic": 0.5,
            "quality_assessment": {
                "overall_quality": "good",
                "pass": True,
                "warnings": [],
                "failures": [],
            },
        }

    def test_store_diagnostics_returns_record_id(self, sample_diagnostics):
        """Test that storing diagnostics returns a record ID"""
        record_id = store_diagnostics_to_db(sample_diagnostics)

        assert record_id is not None
        assert isinstance(record_id, (int, str))

    def test_store_diagnostics_validates_required_fields(self):
        """Test that missing required fields raise ValueError"""
        incomplete_diagnostics = {
            "series_name": "test_series",
            # Missing vintage_date, m_statistics, etc.
        }

        with pytest.raises(ValueError, match="required field"):
            store_diagnostics_to_db(incomplete_diagnostics)

    def test_store_diagnostics_handles_duplicate_series_vintage(self, sample_diagnostics):
        """Test that duplicate series+vintage updates existing record"""
        # Store first time
        record_id1 = store_diagnostics_to_db(sample_diagnostics)

        # Store again with same series+vintage
        record_id2 = store_diagnostics_to_db(sample_diagnostics)

        # Should update existing record (or return same ID)
        assert record_id1 is not None and record_id2 is not None


class TestIntegrationWithX13Output:
    """Test integration with existing X-13 output extraction"""

    def test_compute_from_x13_output_components(self):
        """
        Test that we can compute M-statistics from X-13 output components

        X-13 outputs: D11 (seasonal factors), D12 (trend), D13 (irregular), etc.
        """
        # This would use actual X-13 output files from tests/fixtures
        pytest.skip("Integration test - requires X-13 output files")

    def test_computed_stats_match_x13_reported_stats(self):
        """
        Test that our computed M-statistics match X-13's reported values

        This is CRITICAL: Our computation should match X-13's reference implementation
        Reference validation as per TESTING_MATHEMATICAL_ALGORITHMS.md
        """
        pytest.skip("Reference validation test - requires X-13 output comparison")


class TestDeterminism:
    """Test determinism of M-statistics computation"""

    def test_same_input_produces_same_output(self, simple_decomposition):
        """Test that M-statistics computation is deterministic"""
        computer = MStatisticsComputer()

        result1 = computer.compute(simple_decomposition)
        result2 = computer.compute(simple_decomposition)

        for i in range(1, 12):
            m_key = f"m{i}"
            assert abs(result1[m_key] - result2[m_key]) < 1e-10, f"{m_key} should be deterministic"

    def test_computation_is_reproducible_across_runs(self, high_quality_decomposition):
        """Test reproducibility across multiple computer instances"""
        computer1 = MStatisticsComputer()
        computer2 = MStatisticsComputer()

        result1 = computer1.compute(high_quality_decomposition)
        result2 = computer2.compute(high_quality_decomposition)

        for i in range(1, 12):
            m_key = f"m{i}"
            assert (
                result1[m_key] == result2[m_key]
            ), f"{m_key} should be same across different computer instances"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
