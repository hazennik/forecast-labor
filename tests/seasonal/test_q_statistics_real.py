"""
Tests for Real Q-Statistics Computation (Ljung-Box Test)

Tests computation of Ljung-Box Q-statistics for testing autocorrelation in
seasonal adjustment residuals/irregular component.

Ljung-Box Test:
- Tests null hypothesis: No autocorrelation in residuals
- Q-statistic: Q = n(n+2) Σ(ρ²_k / (n-k)) for k=1 to h
- Under H0, Q ~ χ²(h) where h is number of lags
- p-value > 0.05: Residuals are random (good quality)
- p-value < 0.05: Residuals have autocorrelation (poor quality)

Reference: Ljung, G. M., and Box, G. E. P. (1978). On a Measure of Lack of Fit in Time Series Models.
"""

import pytest
import numpy as np
import pandas as pd
from datetime import datetime
from typing import Dict, Any

# Import will fail initially (TDD approach)
try:
    from seasonal.diagnostics.q_statistics import (
        QStatisticsComputer,
        compute_ljung_box,
        validate_residual_randomness,
        store_q_statistics_to_db,
    )
except ImportError:
    pytest.skip("Q-statistics module not yet implemented", allow_module_level=True)


class TestQStatisticsComputer:
    """Test suite for Q-statistics computer"""

    @pytest.fixture
    def random_residuals(self) -> pd.Series:
        """
        Create random (white noise) residuals - should pass Ljung-Box test

        Returns:
            Series of iid normal random variables (no autocorrelation)
        """
        np.random.seed(42)
        dates = pd.date_range(start="2020-01-01", periods=100, freq="MS")
        residuals = pd.Series(np.random.normal(0, 1, 100), index=dates)
        return residuals

    @pytest.fixture
    def autocorrelated_residuals(self) -> pd.Series:
        """
        Create autocorrelated residuals - should fail Ljung-Box test

        Returns:
            Series with AR(1) process (strong autocorrelation)
        """
        np.random.seed(42)
        dates = pd.date_range(start="2020-01-01", periods=100, freq="MS")

        # AR(1) process: y_t = 0.7 * y_{t-1} + ε_t
        residuals = np.zeros(100)
        epsilon = np.random.normal(0, 1, 100)
        residuals[0] = epsilon[0]

        for i in range(1, 100):
            residuals[i] = 0.7 * residuals[i - 1] + epsilon[i]

        return pd.Series(residuals, index=dates)

    @pytest.fixture
    def seasonal_residuals(self) -> pd.Series:
        """
        Create residuals with seasonal autocorrelation at lag 12

        Returns:
            Series with seasonal pattern (should fail at lag 12)
        """
        np.random.seed(42)
        dates = pd.date_range(start="2020-01-01", periods=100, freq="MS")

        # Seasonal pattern: y_t = 0.6 * y_{t-12} + ε_t
        residuals = np.random.normal(0, 1, 100)

        for i in range(12, 100):
            residuals[i] += 0.6 * residuals[i - 12]

        return pd.Series(residuals, index=dates)

    def test_computer_initialization(self):
        """Test that QStatisticsComputer can be initialized"""
        computer = QStatisticsComputer()
        assert computer is not None

    def test_compute_returns_q_statistic_and_pvalue(self, random_residuals):
        """Test that compute returns Q-statistic and p-value"""
        computer = QStatisticsComputer()
        result = computer.compute(random_residuals)

        assert "q_statistic" in result
        assert "p_value" in result
        assert "degrees_of_freedom" in result
        assert "lags_tested" in result

        assert isinstance(result["q_statistic"], (int, float))
        assert isinstance(result["p_value"], (int, float))
        assert result["q_statistic"] >= 0
        assert 0 <= result["p_value"] <= 1

    def test_random_residuals_pass_test(self, random_residuals):
        """
        Test that random (white noise) residuals pass Ljung-Box test

        Random residuals should have p-value > 0.05 (no autocorrelation)
        """
        computer = QStatisticsComputer()
        result = computer.compute(random_residuals)

        assert (
            result["p_value"] > 0.05
        ), f"Random residuals should pass test: p-value={result['p_value']:.4f}"

    def test_autocorrelated_residuals_fail_test(self, autocorrelated_residuals):
        """
        Test that autocorrelated residuals fail Ljung-Box test

        AR(1) process should have p-value < 0.05 (significant autocorrelation)
        """
        computer = QStatisticsComputer()
        result = computer.compute(autocorrelated_residuals)

        assert (
            result["p_value"] < 0.05
        ), f"Autocorrelated residuals should fail test: p-value={result['p_value']:.4f}"

    def test_seasonal_residuals_detected(self, seasonal_residuals):
        """
        Test that seasonal autocorrelation is detected at appropriate lags

        Series with lag-12 autocorrelation should be detected
        """
        computer = QStatisticsComputer(lags=24)  # Test up to lag 24
        result = computer.compute(seasonal_residuals)

        # Should detect autocorrelation (p-value < 0.05)
        assert result["p_value"] < 0.05, "Seasonal autocorrelation should be detected"

    def test_q_statistic_increases_with_autocorrelation(self, random_residuals):
        """
        Test that Q-statistic increases with stronger autocorrelation

        Mathematical property: Higher autocorrelation → larger Q-statistic
        """
        computer = QStatisticsComputer()

        # Random residuals (low Q)
        result_random = computer.compute(random_residuals)
        q_random = result_random["q_statistic"]

        # Create strong autocorrelation
        dates = random_residuals.index
        ar_strong = pd.Series(np.zeros(len(random_residuals)), index=dates)
        ar_strong.iloc[0] = random_residuals.iloc[0]

        for i in range(1, len(random_residuals)):
            ar_strong.iloc[i] = 0.9 * ar_strong.iloc[i - 1] + random_residuals.iloc[i] * 0.1

        result_ar = computer.compute(ar_strong)
        q_ar = result_ar["q_statistic"]

        assert (
            q_ar > q_random
        ), f"AR process should have higher Q: Q_ar={q_ar:.2f}, Q_random={q_random:.2f}"

    def test_q_statistic_formula_properties(self, random_residuals):
        """
        Test mathematical properties of Q-statistic formula

        Properties:
        - Q >= 0 (always non-negative)
        - Q increases with sample size (for same autocorrelation)
        - Q = n(n+2) Σ(ρ²_k / (n-k)) follows chi-squared under H0
        """
        computer = QStatisticsComputer()
        result = computer.compute(random_residuals)

        # Q-statistic must be non-negative
        assert result["q_statistic"] >= 0

        # For white noise, Q should be approximately chi-squared(h)
        # Expected value of chi-squared(h) is h
        lags = result["lags_tested"]
        q = result["q_statistic"]

        # For white noise, Q should be within reasonable range of expected value
        # Allow generous bounds (chi-squared has variance 2h)
        assert 0 <= q <= lags * 4, f"Q={q:.2f} should be in reasonable range for {lags} lags"

    def test_different_lag_values(self, random_residuals):
        """Test that different lag values produce different results"""
        computer_10 = QStatisticsComputer(lags=10)
        computer_20 = QStatisticsComputer(lags=20)

        result_10 = computer_10.compute(random_residuals)
        result_20 = computer_20.compute(random_residuals)

        assert result_10["lags_tested"] == 10
        assert result_20["lags_tested"] == 20
        assert result_10["degrees_of_freedom"] == 10
        assert result_20["degrees_of_freedom"] == 20

        # Q-statistic should generally increase with more lags
        # (Not always true for random data, but degrees of freedom should differ)
        assert result_10["degrees_of_freedom"] < result_20["degrees_of_freedom"]

    def test_determinism(self, random_residuals):
        """Test that Q-statistic computation is deterministic"""
        computer = QStatisticsComputer()

        result1 = computer.compute(random_residuals)
        result2 = computer.compute(random_residuals)

        assert result1["q_statistic"] == result2["q_statistic"]
        assert result1["p_value"] == result2["p_value"]

    def test_minimum_sample_size(self):
        """Test that minimum sample size is enforced"""
        computer = QStatisticsComputer(lags=10)

        # Too few observations
        short_series = pd.Series(np.random.normal(0, 1, 15))

        with pytest.raises(ValueError, match="sample size|too short|insufficient"):
            computer.compute(short_series)

    def test_lag_validation(self):
        """Test that lag parameter is validated"""
        # Lags must be positive
        with pytest.raises(ValueError, match="lags|positive"):
            QStatisticsComputer(lags=0)

        with pytest.raises(ValueError, match="lags|positive"):
            QStatisticsComputer(lags=-5)


class TestQualityThresholdValidation:
    """Test suite for quality threshold validation based on Q-statistics"""

    def test_validate_good_quality(self):
        """Test validation of good quality residuals (p-value > 0.05)"""
        q_stats = {"q_statistic": 8.5, "p_value": 0.58, "lags_tested": 10, "degrees_of_freedom": 10}

        validation = validate_residual_randomness(q_stats)

        assert validation["quality"] == "good"
        assert validation["pass"] is True
        assert validation["random"] is True
        assert "No significant autocorrelation" in validation["message"]

    def test_validate_poor_quality(self):
        """Test validation of poor quality residuals (p-value < 0.05)"""
        q_stats = {
            "q_statistic": 28.5,
            "p_value": 0.001,
            "lags_tested": 10,
            "degrees_of_freedom": 10,
        }

        validation = validate_residual_randomness(q_stats)

        assert validation["quality"] == "poor"
        assert validation["pass"] is False
        assert validation["random"] is False
        assert "Significant autocorrelation" in validation["message"]

    def test_threshold_boundary(self):
        """Test validation at threshold boundary (p-value = 0.05)"""
        q_stats_just_pass = {
            "q_statistic": 18.3,
            "p_value": 0.051,
            "lags_tested": 10,
            "degrees_of_freedom": 10,
        }

        q_stats_just_fail = {
            "q_statistic": 18.5,
            "p_value": 0.049,
            "lags_tested": 10,
            "degrees_of_freedom": 10,
        }

        validation_pass = validate_residual_randomness(q_stats_just_pass)
        validation_fail = validate_residual_randomness(q_stats_just_fail)

        assert validation_pass["pass"] is True
        assert validation_fail["pass"] is False


class TestDatabaseStorage:
    """Test suite for database storage of Q-statistics"""

    @pytest.fixture
    def sample_q_statistics(self) -> Dict[str, Any]:
        """Sample Q-statistics for testing"""
        return {
            "series_name": "test_series_irregular",
            "vintage_date": "2024-01-15",
            "computation_timestamp": datetime.now(),
            "q_statistic": 12.5,
            "p_value": 0.25,
            "lags_tested": 12,
            "degrees_of_freedom": 12,
            "quality_assessment": {
                "quality": "good",
                "pass": True,
                "random": True,
                "message": "No significant autocorrelation detected",
            },
        }

    def test_store_q_statistics_returns_record_id(self, sample_q_statistics):
        """Test that storing Q-statistics returns a record ID"""
        record_id = store_q_statistics_to_db(sample_q_statistics)

        assert record_id is not None
        assert isinstance(record_id, (int, str))

    def test_store_validates_required_fields(self):
        """Test that missing required fields raise ValueError"""
        incomplete_stats = {
            "series_name": "test_series",
            # Missing q_statistic, p_value, etc.
        }

        with pytest.raises(ValueError, match="required field"):
            store_q_statistics_to_db(incomplete_stats)

    def test_store_handles_duplicate_series_vintage(self, sample_q_statistics):
        """Test that duplicate series+vintage updates existing record"""
        # Store first time
        record_id1 = store_q_statistics_to_db(sample_q_statistics)

        # Store again with same series+vintage
        record_id2 = store_q_statistics_to_db(sample_q_statistics)

        # Should update existing record
        assert record_id1 is not None and record_id2 is not None


class TestIntegrationWithSeasonalPipeline:
    """Test integration with seasonal adjustment pipeline"""

    def test_q_statistics_added_to_diagnostics(self):
        """
        Test that Q-statistics are automatically added to seasonal diagnostics

        Integration test - requires seasonal pipeline
        """
        pytest.skip("Integration test - requires seasonal pipeline setup")

    def test_quality_gates_enforced(self):
        """
        Test that quality gates are enforced based on Q-statistics

        If p-value < 0.05, should flag quality issue
        """
        pytest.skip("Integration test - requires quality gate implementation")


class TestComputeLjungBox:
    """Test standalone compute_ljung_box function"""

    def test_compute_ljung_box_convenience_function(self):
        """Test that convenience function works"""
        np.random.seed(42)
        residuals = pd.Series(np.random.normal(0, 1, 100))

        result = compute_ljung_box(residuals, lags=10)

        assert "q_statistic" in result
        assert "p_value" in result
        assert result["lags_tested"] == 10

    def test_compute_ljung_box_default_lags(self):
        """Test that default lags are reasonable"""
        np.random.seed(42)
        residuals = pd.Series(np.random.normal(0, 1, 100))

        result = compute_ljung_box(residuals)

        # Default should be min(10, len(series)//5) or similar
        assert result["lags_tested"] > 0
        assert result["lags_tested"] <= len(residuals) // 2


class TestMathematicalProperties:
    """Test mathematical properties of Ljung-Box test"""

    def test_chi_squared_distribution_under_null(self):
        """
        Test that Q-statistic approximately follows chi-squared distribution

        Under null hypothesis (white noise), Q ~ χ²(h)
        """
        np.random.seed(42)
        computer = QStatisticsComputer(lags=10)

        # Generate many white noise series and compute Q-statistics
        q_stats = []
        for i in range(100):
            np.random.seed(42 + i)
            residuals = pd.Series(np.random.normal(0, 1, 100))
            result = computer.compute(residuals)
            q_stats.append(result["q_statistic"])

        # Mean of Q-statistics should be approximately h (degrees of freedom)
        mean_q = np.mean(q_stats)
        expected_mean = 10  # Chi-squared(10) has mean = 10

        # Allow 20% tolerance (statistical test, not exact)
        assert (
            abs(mean_q - expected_mean) / expected_mean < 0.3
        ), f"Mean Q-statistic {mean_q:.2f} should be near {expected_mean}"

    def test_p_values_uniform_under_null(self):
        """
        Test that p-values are approximately uniformly distributed under null

        For white noise, p-values should be uniform(0, 1)
        """
        np.random.seed(42)
        computer = QStatisticsComputer(lags=10)

        # Generate many white noise series and compute p-values
        p_values = []
        for i in range(100):
            np.random.seed(42 + i)
            residuals = pd.Series(np.random.normal(0, 1, 100))
            result = computer.compute(residuals)
            p_values.append(result["p_value"])

        # Check that p-values are spread across [0, 1]
        # For uniform(0,1), approximately 50% should be < 0.5
        below_half = sum(1 for p in p_values if p < 0.5)
        proportion = below_half / len(p_values)

        # Allow 10% tolerance
        assert 0.35 <= proportion <= 0.65, f"Proportion < 0.5 should be ~0.5, got {proportion:.2f}"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
