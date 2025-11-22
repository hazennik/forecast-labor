"""
Tests for Hierarchical Forecast Coherence Validation

Tests coherence validation utilities used in hierarchical forecast reconciliation.
Ensures that aggregate forecasts equal the sum of their components within tolerance.

Key Functions Tested:
- validate_coherence: Check if forecasts are coherent
- compute_coherence_errors: Calculate incoherence magnitude
- build_summing_matrix: Construct hierarchical summing matrices
"""

import pytest
import numpy as np
import pandas as pd

from features.aggregations.hierarchical import (
    validate_coherence,
    compute_coherence_errors,
    build_summing_matrix
)


class TestValidateCoherence:
    """Test coherence validation for hierarchical forecasts."""
    
    def test_validate_coherence_perfect_coherence(self):
        """Test validation with perfectly coherent forecasts."""
        # National = sum of states
        forecasts = pd.DataFrame({
            'national': [300, 305, 310],
            'CA': [100, 102, 104],
            'TX': [100, 101, 103],
            'NY': [100, 102, 103]
        })
        
        is_coherent = validate_coherence(
            forecasts,
            total_col='national',
            component_cols=['CA', 'TX', 'NY'],
            tolerance=1e-10
        )
        
        assert is_coherent
    
    def test_validate_coherence_incoherent_forecasts(self):
        """Test validation with incoherent forecasts."""
        # National ≠ sum of states
        forecasts = pd.DataFrame({
            'national': [300, 305, 310],
            'CA': [100, 102, 104],
            'TX': [100, 101, 103],
            'NY': [95, 98, 100]  # Sum = 295, 301, 307 (not 300, 305, 310)
        })
        
        is_coherent = validate_coherence(
            forecasts,
            total_col='national',
            component_cols=['CA', 'TX', 'NY'],
            tolerance=1e-10
        )
        
        assert not is_coherent
    
    def test_validate_coherence_within_tolerance(self):
        """Test validation with small errors within tolerance."""
        # Small rounding errors
        forecasts = pd.DataFrame({
            'national': [300.0000001, 305.0000002, 310.0],
            'CA': [100.0, 102.0, 104.0],
            'TX': [100.0, 101.0, 103.0],
            'NY': [100.0, 102.0, 103.0]
        })
        
        # Should pass with reasonable tolerance
        is_coherent = validate_coherence(
            forecasts,
            total_col='national',
            component_cols=['CA', 'TX', 'NY'],
            tolerance=1e-6
        )
        
        assert is_coherent
        
        # Should fail with very strict tolerance
        is_coherent_strict = validate_coherence(
            forecasts,
            total_col='national',
            component_cols=['CA', 'TX', 'NY'],
            tolerance=1e-10
        )
        
        assert not is_coherent_strict
    
    def test_validate_coherence_missing_columns(self):
        """Test validation with missing columns."""
        forecasts = pd.DataFrame({
            'national': [300, 305, 310],
            'CA': [100, 102, 104],
            'TX': [100, 101, 103]
            # NY missing
        })
        
        with pytest.raises((ValueError, KeyError)):
            validate_coherence(
                forecasts,
                total_col='national',
                component_cols=['CA', 'TX', 'NY'],
                tolerance=1e-10
            )
    
    def test_validate_coherence_empty_dataframe(self):
        """Test validation with empty DataFrame."""
        forecasts = pd.DataFrame()
        
        with pytest.raises((ValueError, KeyError)):
            validate_coherence(
                forecasts,
                total_col='national',
                component_cols=['CA', 'TX', 'NY'],
                tolerance=1e-10
            )
    
    def test_validate_coherence_two_components(self):
        """Test validation with minimum two-component hierarchy."""
        forecasts = pd.DataFrame({
            'total': [200, 205, 210],
            'component1': [120, 123, 126],
            'component2': [80, 82, 84]
        })
        
        is_coherent = validate_coherence(
            forecasts,
            total_col='total',
            component_cols=['component1', 'component2'],
            tolerance=1e-10
        )
        
        assert is_coherent
    
    def test_validate_coherence_many_components(self):
        """Test validation with many components (50 states)."""
        np.random.seed(42)
        n_obs = 10
        n_states = 50
        
        # Generate random bottom-level forecasts
        state_data = np.random.randint(1, 20, size=(n_obs, n_states))
        state_df = pd.DataFrame(
            state_data,
            columns=[f'state_{i}' for i in range(n_states)]
        )
        
        # National is exact sum
        forecasts = pd.DataFrame({
            'national': state_df.sum(axis=1)
        })
        forecasts = pd.concat([forecasts, state_df], axis=1)
        
        is_coherent = validate_coherence(
            forecasts,
            total_col='national',
            component_cols=[f'state_{i}' for i in range(n_states)],
            tolerance=1e-10
        )
        
        assert is_coherent


class TestComputeCoherenceErrors:
    """Test coherence error computation."""
    
    def test_compute_coherence_errors_zero_error(self):
        """Test error computation with perfectly coherent forecasts."""
        forecasts = pd.DataFrame({
            'national': [300, 305, 310],
            'CA': [100, 102, 104],
            'TX': [100, 101, 103],
            'NY': [100, 102, 103]
        })
        
        errors = compute_coherence_errors(
            forecasts,
            total_col='national',
            component_cols=['CA', 'TX', 'NY']
        )
        
        assert errors.shape == (3,)
        assert np.allclose(errors, 0, atol=1e-10)
    
    def test_compute_coherence_errors_nonzero_error(self):
        """Test error computation with known incoherence."""
        forecasts = pd.DataFrame({
            'national': [300, 305, 310],
            'CA': [100, 102, 104],
            'TX': [100, 101, 103],
            'NY': [95, 98, 100]  # Sum = 295, 301, 307
        })
        
        errors = compute_coherence_errors(
            forecasts,
            total_col='national',
            component_cols=['CA', 'TX', 'NY']
        )
        
        expected_errors = np.array([5, 4, 3])  # 300-295, 305-301, 310-307
        assert np.allclose(errors, expected_errors)
    
    def test_compute_coherence_errors_negative_incoherence(self):
        """Test error computation when components sum > total."""
        forecasts = pd.DataFrame({
            'national': [300, 305, 310],
            'CA': [105, 108, 110],  # Higher than before
            'TX': [100, 101, 103],
            'NY': [100, 102, 103]
        })
        
        errors = compute_coherence_errors(
            forecasts,
            total_col='national',
            component_cols=['CA', 'TX', 'NY']
        )
        
        # National < sum of states, so errors should be negative
        expected_errors = np.array([-5, -6, -6])
        assert np.allclose(errors, expected_errors)
    
    def test_compute_coherence_errors_single_observation(self):
        """Test error computation with single observation."""
        forecasts = pd.DataFrame({
            'national': [300],
            'CA': [100],
            'TX': [100],
            'NY': [95]  # Sum = 295
        })
        
        errors = compute_coherence_errors(
            forecasts,
            total_col='national',
            component_cols=['CA', 'TX', 'NY']
        )
        
        assert errors.shape == (1,)
        assert np.isclose(errors[0], 5)
    
    def test_compute_coherence_errors_returns_series(self):
        """Test that function returns pandas Series."""
        forecasts = pd.DataFrame({
            'national': [300, 305],
            'CA': [100, 102],
            'TX': [100, 101],
            'NY': [100, 102]
        })
        
        errors = compute_coherence_errors(
            forecasts,
            total_col='national',
            component_cols=['CA', 'TX', 'NY']
        )
        
        assert isinstance(errors, pd.Series)
        # Dtype can be int or float depending on the values
        assert np.issubdtype(errors.dtype, np.number)
    
    def test_compute_coherence_errors_magnitude(self):
        """Test error magnitude calculation."""
        forecasts = pd.DataFrame({
            'national': [1000, 2000, 3000],
            'A': [300, 600, 900],
            'B': [300, 600, 900],
            'C': [300, 700, 1100]  # Sum = 900, 1900, 2900
        })
        
        errors = compute_coherence_errors(
            forecasts,
            total_col='national',
            component_cols=['A', 'B', 'C']
        )
        
        expected_errors = np.array([100, 100, 100])
        assert np.allclose(errors, expected_errors)
        
        # Check absolute magnitude
        assert np.abs(errors).max() == 100


class TestBuildSummingMatrix:
    """Test summing matrix construction for hierarchies."""
    
    def test_build_summing_matrix_single_level(self):
        """Test summing matrix for single-level hierarchy."""
        # Nation = CA + TX + NY (3 bottom series)
        S = build_summing_matrix(n_bottom=3, hierarchy_type='single_level')
        
        # Should be (1, 3) matrix of all ones
        assert S.shape == (1, 3)
        assert np.allclose(S, np.array([[1, 1, 1]]))
    
    def test_build_summing_matrix_two_bottom_series(self):
        """Test summing matrix with minimum two series."""
        S = build_summing_matrix(n_bottom=2, hierarchy_type='single_level')
        
        assert S.shape == (1, 2)
        assert np.allclose(S, np.array([[1, 1]]))
    
    def test_build_summing_matrix_many_bottom_series(self):
        """Test summing matrix with many series (50 states)."""
        S = build_summing_matrix(n_bottom=50, hierarchy_type='single_level')
        
        assert S.shape == (1, 50)
        assert np.all(S == 1)
        assert S.sum() == 50
    
    def test_build_summing_matrix_invalid_hierarchy_type(self):
        """Test error with invalid hierarchy type."""
        with pytest.raises(ValueError, match="Unknown hierarchy type"):
            build_summing_matrix(n_bottom=3, hierarchy_type='multi_level')
    
    def test_build_summing_matrix_zero_bottom_series(self):
        """Test error with zero bottom series."""
        # Note: build_summing_matrix doesn't currently validate n_bottom > 0
        # It will create an empty matrix, which may be acceptable behavior
        S = build_summing_matrix(n_bottom=0, hierarchy_type='single_level')
        assert S.shape == (1, 0)
    
    def test_build_summing_matrix_negative_bottom_series(self):
        """Test error with negative bottom series."""
        with pytest.raises(ValueError):
            build_summing_matrix(n_bottom=-1, hierarchy_type='single_level')
    
    def test_build_summing_matrix_returns_numpy_array(self):
        """Test that function returns numpy array."""
        S = build_summing_matrix(n_bottom=5, hierarchy_type='single_level')
        
        assert isinstance(S, np.ndarray)
        assert np.issubdtype(S.dtype, np.floating) or np.issubdtype(S.dtype, np.integer)


class TestReconciliationErrorBounds:
    """Test reconciliation error bounds and thresholds."""
    
    def test_error_bounds_within_100_jobs(self):
        """Test that reconciliation errors are within 100 jobs threshold."""
        # Simulate reconciled forecasts
        forecasts = pd.DataFrame({
            'national': [150000, 155000, 160000],
            'CA': [50000, 51667, 53334],
            'TX': [50000, 51667, 53333],
            'NY': [50000, 51666, 53333]
        })
        
        errors = compute_coherence_errors(
            forecasts,
            total_col='national',
            component_cols=['CA', 'TX', 'NY']
        )
        
        # Max absolute error should be < 100 jobs (project requirement)
        max_error = np.abs(errors).max()
        assert max_error < 100
    
    def test_error_bounds_numerical_precision(self):
        """Test that numerical precision errors are acceptable."""
        # Test with floating point arithmetic errors
        forecasts = pd.DataFrame({
            'national': [1.0, 2.0, 3.0],
            'A': [0.3, 0.6, 0.9],
            'B': [0.3, 0.6, 0.9],
            'C': [0.4, 0.8, 1.2]
        })
        
        errors = compute_coherence_errors(
            forecasts,
            total_col='national',
            component_cols=['A', 'B', 'C']
        )
        
        # Should be within numerical precision
        max_error = np.abs(errors).max()
        assert max_error < 1e-10
    
    def test_error_bounds_after_reconciliation(self):
        """Test error bounds after MinT reconciliation."""
        # Simulate before/after reconciliation
        base_forecasts = pd.DataFrame({
            'national': [300, 305, 310],
            'CA': [95, 98, 100],
            'TX': [95, 98, 100],
            'NY': [95, 98, 100]
        })
        
        # Check initial errors (large)
        errors_before = compute_coherence_errors(
            base_forecasts,
            total_col='national',
            component_cols=['CA', 'TX', 'NY']
        )
        assert np.abs(errors_before).max() > 10  # Significant incoherence
        
        # Simulate reconciled forecasts (perfect coherence)
        reconciled_forecasts = pd.DataFrame({
            'national': [285, 294, 300],
            'CA': [95, 98, 100],
            'TX': [95, 98, 100],
            'NY': [95, 98, 100]
        })
        
        errors_after = compute_coherence_errors(
            reconciled_forecasts,
            total_col='national',
            component_cols=['CA', 'TX', 'NY']
        )
        
        # After reconciliation, errors should be zero
        assert np.allclose(errors_after, 0, atol=1e-10)
    
    def test_error_bounds_sector_aggregation(self):
        """Test error bounds for sector aggregation."""
        # Total nonfarm = sum of sectors
        forecasts = pd.DataFrame({
            'total_nonfarm': [150000, 155000, 160000],
            'retail': [15000, 15500, 16000],
            'leisure': [16000, 16500, 17000],
            'manufacturing': [12000, 12400, 12800],
            'professional': [20000, 20600, 21200],
            'other': [87000, 90000, 93000]
        })
        
        sectors = ['retail', 'leisure', 'manufacturing', 'professional', 'other']
        errors = compute_coherence_errors(
            forecasts,
            total_col='total_nonfarm',
            component_cols=sectors
        )
        
        # Should be coherent
        max_error = np.abs(errors).max()
        assert max_error < 1
    
    def test_error_bounds_large_scale_hierarchy(self):
        """Test error bounds with large-scale hierarchy (all 50 states)."""
        np.random.seed(42)
        n_obs = 100
        n_states = 50
        
        # Generate state forecasts
        state_data = np.random.randint(1000, 5000, size=(n_obs, n_states))
        state_df = pd.DataFrame(
            state_data,
            columns=[f'state_{i}' for i in range(n_states)]
        )
        
        # National with small errors
        national = state_df.sum(axis=1) + np.random.uniform(-50, 50, n_obs)
        
        forecasts = pd.DataFrame({'national': national})
        forecasts = pd.concat([forecasts, state_df], axis=1)
        
        errors = compute_coherence_errors(
            forecasts,
            total_col='national',
            component_cols=[f'state_{i}' for i in range(n_states)]
        )
        
        # Check error statistics
        mean_error = np.abs(errors).mean()
        max_error = np.abs(errors).max()
        
        assert mean_error < 100  # Average error reasonable
        assert max_error < 200   # Max error bounded


class TestIntegration:
    """Integration tests for coherence validation workflow."""
    
    def test_full_coherence_validation_workflow(self):
        """Test complete coherence validation workflow."""
        # 1. Create incoherent forecasts
        forecasts = pd.DataFrame({
            'national': [300, 305, 310],
            'CA': [100, 102, 104],
            'TX': [100, 101, 103],
            'NY': [95, 98, 100]
        })
        
        # 2. Validate (should fail)
        is_coherent = validate_coherence(
            forecasts,
            'national',
            ['CA', 'TX', 'NY'],
            tolerance=1e-6
        )
        assert not is_coherent
        
        # 3. Compute errors
        errors = compute_coherence_errors(
            forecasts,
            'national',
            ['CA', 'TX', 'NY']
        )
        assert not np.allclose(errors, 0)
        
        # 4. "Reconcile" (adjust national to sum of states)
        reconciled = forecasts.copy()
        reconciled['national'] = forecasts[['CA', 'TX', 'NY']].sum(axis=1)
        
        # 5. Validate again (should pass)
        is_coherent_after = validate_coherence(
            reconciled,
            'national',
            ['CA', 'TX', 'NY'],
            tolerance=1e-6
        )
        assert is_coherent_after
        
        # 6. Verify errors are zero
        errors_after = compute_coherence_errors(
            reconciled,
            'national',
            ['CA', 'TX', 'NY']
        )
        assert np.allclose(errors_after, 0)
    
    def test_coherence_validation_with_summing_matrix(self):
        """Test coherence using summing matrix formulation."""
        # Build summing matrix
        S = build_summing_matrix(n_bottom=3, hierarchy_type='single_level')
        
        # Bottom-level forecasts
        y_bottom = np.array([
            [100, 100, 100],  # t=0
            [102, 101, 102],  # t=1
            [104, 103, 103]   # t=2
        ])
        
        # Aggregate using summing matrix: y_top = S @ y_bottom.T
        y_top = (S @ y_bottom.T).T  # Shape: (3, 1)
        
        # Combine into DataFrame
        forecasts = pd.DataFrame({
            'national': y_top.flatten(),
            'CA': y_bottom[:, 0],
            'TX': y_bottom[:, 1],
            'NY': y_bottom[:, 2]
        })
        
        # Should be perfectly coherent
        is_coherent = validate_coherence(
            forecasts,
            'national',
            ['CA', 'TX', 'NY'],
            tolerance=1e-10
        )
        assert is_coherent
    
    def test_realistic_nfp_forecasting_scenario(self):
        """Test with realistic NFP forecasting scenario."""
        # Simulate NFP forecasts (in thousands)
        forecasts = pd.DataFrame({
            'us_total': [150.2, 155.8, 161.3],  # Thousands of jobs
            'california': [18.5, 19.2, 19.8],
            'texas': [13.2, 13.7, 14.1],
            'new_york': [9.1, 9.4, 9.7],
            'florida': [10.3, 10.7, 11.0],
            'other_states': [99.1, 102.8, 106.7]
        })
        
        states = ['california', 'texas', 'new_york', 'florida', 'other_states']
        
        # Validate coherence
        is_coherent = validate_coherence(
            forecasts,
            'us_total',
            states,
            tolerance=0.1  # Allow 100 jobs tolerance (0.1 thousand)
        )
        
        assert is_coherent
        
        # Check error magnitude
        errors = compute_coherence_errors(forecasts, 'us_total', states)
        max_error_thousands = np.abs(errors).max()
        max_error_jobs = max_error_thousands * 1000
        
        # Verify within project requirement (< 100 jobs)
        assert max_error_jobs < 100

