"""
Tests for WLS (Weighted Least Squares) Utilities

Tests variance weight computation, covariance matrix handling, and weight matrix
construction utilities for hierarchical forecast reconciliation.
"""

import pytest
import numpy as np
import pandas as pd
from unittest.mock import Mock

# Import will fail initially (TDD - write tests first)
from recon.mint.wls_utils import (
    compute_variance_weights,
    compute_diagonal_weights,
    compute_sample_covariance,
    compute_shrinkage_covariance,
    ensure_positive_definite,
    validate_weight_matrix,
    compute_wls_weights,
    compute_precision_matrix,
)


class TestVarianceWeights:
    """Test variance weight computation."""
    
    def test_compute_variance_weights_basic(self):
        """Test basic variance weight computation."""
        # Create simple data with known variances
        data = pd.DataFrame({
            'series1': [1, 2, 3, 4, 5],
            'series2': [10, 20, 30, 40, 50],
            'series3': [100, 200, 300, 400, 500]
        })
        
        weights = compute_variance_weights(data)
        
        # Should return diagonal matrix with variances
        assert weights.shape == (3, 3)
        assert np.allclose(np.diag(weights), data.var().values)
        # Off-diagonal should be zero (diagonal matrix)
        assert np.allclose(weights - np.diag(np.diag(weights)), 0)
    
    def test_compute_variance_weights_with_zeros(self):
        """Test variance weights with zero variance (constant series)."""
        data = pd.DataFrame({
            'constant': [5, 5, 5, 5, 5],
            'variable': [1, 2, 3, 4, 5]
        })
        
        weights = compute_variance_weights(data, min_variance=1e-8)
        
        # Constant series should get minimum variance
        assert weights[0, 0] >= 1e-8
        # Variable series should have actual variance
        assert weights[1, 1] > 1e-8
    
    def test_compute_variance_weights_empty(self):
        """Test variance weights with empty data."""
        data = pd.DataFrame()
        
        with pytest.raises(ValueError, match="Data cannot be empty"):
            compute_variance_weights(data)
    
    def test_compute_variance_weights_single_observation(self):
        """Test variance weights with single observation."""
        data = pd.DataFrame({'series1': [1], 'series2': [2]})
        
        with pytest.raises(ValueError, match="At least 2 observations"):
            compute_variance_weights(data)


class TestDiagonalWeights:
    """Test diagonal weight matrix construction."""
    
    def test_compute_diagonal_weights_basic(self):
        """Test basic diagonal weight matrix."""
        variances = np.array([1.0, 4.0, 9.0])
        
        weights = compute_diagonal_weights(variances)
        
        assert weights.shape == (3, 3)
        assert np.allclose(np.diag(weights), variances)
        assert np.allclose(weights - np.diag(np.diag(weights)), 0)
    
    def test_compute_diagonal_weights_regularization(self):
        """Test diagonal weights with regularization for small values."""
        variances = np.array([0.0, 1e-10, 1.0])
        
        weights = compute_diagonal_weights(variances, min_variance=1e-8)
        
        # First two should be regularized
        assert weights[0, 0] >= 1e-8
        assert weights[1, 1] >= 1e-8
        # Last should be unchanged
        assert np.isclose(weights[2, 2], 1.0)
    
    def test_compute_diagonal_weights_negative(self):
        """Test diagonal weights with negative variance (error case)."""
        variances = np.array([1.0, -1.0, 1.0])
        
        with pytest.raises(ValueError, match="Variances must be non-negative"):
            compute_diagonal_weights(variances, allow_negative=False)


class TestSampleCovariance:
    """Test sample covariance matrix computation."""
    
    def test_compute_sample_covariance_basic(self):
        """Test basic sample covariance."""
        data = pd.DataFrame({
            'series1': [1, 2, 3, 4, 5],
            'series2': [2, 4, 6, 8, 10]
        })
        
        cov_matrix = compute_sample_covariance(data)
        
        # Should match pandas cov()
        expected = data.cov().values
        assert np.allclose(cov_matrix, expected)
    
    def test_compute_sample_covariance_positive_definite(self):
        """Test that sample covariance is positive definite."""
        np.random.seed(42)
        data = pd.DataFrame(
            np.random.randn(100, 5),
            columns=[f'series{i}' for i in range(5)]
        )
        
        cov_matrix = compute_sample_covariance(data, ensure_pd=True)
        
        # Check positive definite (all eigenvalues > 0)
        eigenvalues = np.linalg.eigvalsh(cov_matrix)
        assert np.all(eigenvalues > 0)
    
    def test_compute_sample_covariance_insufficient_data(self):
        """Test sample covariance with insufficient data."""
        # More variables than observations (singular)
        data = pd.DataFrame(
            np.random.randn(3, 5),  # 3 obs, 5 variables
            columns=[f'series{i}' for i in range(5)]
        )
        
        cov_matrix = compute_sample_covariance(data, ensure_pd=True)
        
        # Should be regularized to be positive definite
        eigenvalues = np.linalg.eigvalsh(cov_matrix)
        assert np.all(eigenvalues > 0)


class TestShrinkageCovariance:
    """Test shrinkage covariance estimation."""
    
    def test_compute_shrinkage_covariance_basic(self):
        """Test basic shrinkage covariance (Ledoit-Wolf)."""
        np.random.seed(42)
        data = pd.DataFrame(
            np.random.randn(50, 4),
            columns=[f'series{i}' for i in range(4)]
        )
        
        cov_matrix = compute_shrinkage_covariance(data)
        
        # Should be symmetric
        assert np.allclose(cov_matrix, cov_matrix.T)
        # Should be positive definite
        eigenvalues = np.linalg.eigvalsh(cov_matrix)
        assert np.all(eigenvalues > 0)
    
    def test_compute_shrinkage_covariance_small_sample(self):
        """Test shrinkage with small sample (high shrinkage expected)."""
        np.random.seed(42)
        # Small sample relative to dimensions
        data = pd.DataFrame(
            np.random.randn(10, 8),
            columns=[f'series{i}' for i in range(8)]
        )
        
        cov_matrix = compute_shrinkage_covariance(data)
        
        # Should still be well-conditioned due to shrinkage
        condition_number = np.linalg.cond(cov_matrix)
        assert condition_number < 1e10


class TestPositiveDefinite:
    """Test positive definite matrix utilities."""
    
    def test_ensure_positive_definite_already_pd(self):
        """Test with already positive definite matrix."""
        # Create PD matrix via correlation
        np.random.seed(42)
        A = np.random.randn(4, 10)
        matrix = A @ A.T  # Guaranteed PD
        
        result = ensure_positive_definite(matrix)
        
        # Should be unchanged (or nearly so)
        assert np.allclose(result, matrix, atol=1e-6)
        # Should still be PD
        eigenvalues = np.linalg.eigvalsh(result)
        assert np.all(eigenvalues > 0)
    
    def test_ensure_positive_definite_negative_eigenvalues(self):
        """Test with matrix having negative eigenvalues."""
        # Create matrix with negative eigenvalue
        matrix = np.array([
            [1, 0, 0],
            [0, -1, 0],  # Negative eigenvalue
            [0, 0, 1]
        ])
        
        result = ensure_positive_definite(matrix, min_eigenvalue=1e-6)
        
        # All eigenvalues should be positive
        eigenvalues = np.linalg.eigvalsh(result)
        assert np.all(eigenvalues >= 1e-6)
    
    def test_ensure_positive_definite_symmetry(self):
        """Test that result is symmetric."""
        # Create slightly asymmetric matrix
        matrix = np.array([
            [2, 1, 0],
            [1.001, 2, 1],  # Slight asymmetry
            [0, 1, 2]
        ])
        
        result = ensure_positive_definite(matrix)
        
        # Should be symmetric
        assert np.allclose(result, result.T)


class TestWeightMatrixValidation:
    """Test weight matrix validation utilities."""
    
    def test_validate_weight_matrix_valid_diagonal(self):
        """Test validation of valid diagonal weight matrix."""
        weights = np.diag([1, 2, 3, 4])
        
        is_valid, message = validate_weight_matrix(weights, matrix_type='diagonal')
        
        assert is_valid
        assert message == "Valid diagonal weight matrix"
    
    def test_validate_weight_matrix_valid_full(self):
        """Test validation of valid full covariance matrix."""
        # Create valid covariance matrix
        np.random.seed(42)
        A = np.random.randn(3, 10)
        weights = A @ A.T  # Positive definite
        
        is_valid, message = validate_weight_matrix(weights, matrix_type='full')
        
        assert is_valid
        assert "Valid full covariance" in message
    
    def test_validate_weight_matrix_not_square(self):
        """Test validation with non-square matrix."""
        weights = np.array([[1, 2], [3, 4], [5, 6]])
        
        is_valid, message = validate_weight_matrix(weights)
        
        assert not is_valid
        assert "not square" in message.lower()
    
    def test_validate_weight_matrix_negative_diagonal(self):
        """Test validation with negative diagonal element."""
        weights = np.diag([1, -1, 1])
        
        is_valid, message = validate_weight_matrix(weights, matrix_type='diagonal')
        
        assert not is_valid
        assert "negative" in message.lower()
    
    def test_validate_weight_matrix_not_positive_definite(self):
        """Test validation with non-PD matrix."""
        weights = np.array([
            [1, 0, 0],
            [0, -1, 0],  # Negative diagonal will be caught first
            [0, 0, 1]
        ])
        
        is_valid, message = validate_weight_matrix(weights, matrix_type='full')
        
        assert not is_valid
        # Negative diagonal is detected before PD check
        assert "negative" in message.lower() or "not positive definite" in message.lower()


class TestWLSWeights:
    """Test WLS weight computation for reconciliation."""
    
    def test_compute_wls_weights_ols(self):
        """Test WLS weights for OLS (identity)."""
        n_series = 5
        
        weights = compute_wls_weights(
            n_series=n_series,
            method='ols'
        )
        
        # Should be identity matrix
        assert np.allclose(weights, np.eye(n_series))
    
    def test_compute_wls_weights_diagonal(self):
        """Test WLS weights with diagonal variance."""
        variances = np.array([1, 4, 9, 16])
        
        weights = compute_wls_weights(
            variances=variances,
            method='diagonal'
        )
        
        # Should be diagonal matrix with variances
        assert np.allclose(np.diag(weights), variances)
    
    def test_compute_wls_weights_from_data(self):
        """Test WLS weights computed from data."""
        data = pd.DataFrame({
            'series1': [1, 2, 3, 4, 5],
            'series2': [10, 20, 30, 40, 50]
        })
        
        weights = compute_wls_weights(
            data=data,
            method='sample'
        )
        
        # Should match sample covariance
        expected = data.cov().values
        assert np.allclose(weights, expected, atol=1e-10)
    
    def test_compute_wls_weights_invalid_method(self):
        """Test WLS weights with invalid method."""
        with pytest.raises(ValueError, match="Invalid method"):
            compute_wls_weights(n_series=3, method='invalid')


class TestPrecisionMatrix:
    """Test precision matrix (inverse covariance) computation."""
    
    def test_compute_precision_matrix_basic(self):
        """Test basic precision matrix computation."""
        # Create covariance matrix
        cov = np.array([
            [2, 1],
            [1, 2]
        ])
        
        precision = compute_precision_matrix(cov)
        
        # Should be inverse
        assert np.allclose(cov @ precision, np.eye(2))
        assert np.allclose(precision @ cov, np.eye(2))
    
    def test_compute_precision_matrix_diagonal(self):
        """Test precision of diagonal covariance."""
        cov = np.diag([1, 4, 9])
        
        precision = compute_precision_matrix(cov)
        
        # Inverse of diagonal is diagonal of inverses
        expected = np.diag([1, 0.25, 1/9])
        assert np.allclose(precision, expected)
    
    def test_compute_precision_matrix_singular(self):
        """Test precision matrix with singular covariance (regularization)."""
        # Singular matrix (not invertible)
        cov = np.array([
            [1, 1],
            [1, 1]
        ])
        
        precision = compute_precision_matrix(cov, regularization=1e-6)
        
        # Should be invertible after regularization
        assert not np.isnan(precision).any()
        assert not np.isinf(precision).any()


class TestIntegration:
    """Integration tests for WLS utilities."""
    
    def test_full_wls_workflow(self):
        """Test complete WLS weight computation workflow."""
        np.random.seed(42)
        
        # 1. Create sample data (historical forecast errors)
        data = pd.DataFrame(
            np.random.randn(100, 4),
            columns=['national', 'state1', 'state2', 'state3']
        )
        
        # 2. Compute variance weights (diagonal)
        weights_diag = compute_wls_weights(data=data, method='diagonal')
        is_valid, _ = validate_weight_matrix(weights_diag, matrix_type='diagonal')
        assert is_valid
        
        # 3. Compute full covariance weights
        weights_full = compute_wls_weights(data=data, method='sample')
        is_valid, _ = validate_weight_matrix(weights_full, matrix_type='full')
        assert is_valid
        
        # 4. Compute shrinkage weights (for small samples)
        weights_shrink = compute_wls_weights(data=data, method='shrinkage')
        is_valid, _ = validate_weight_matrix(weights_shrink, matrix_type='full')
        assert is_valid
    
    def test_wls_weights_consistency(self):
        """Test consistency across different weight computation methods."""
        np.random.seed(42)
        data = pd.DataFrame(
            np.random.randn(50, 3),
            columns=['total', 'component1', 'component2']
        )
        
        # Different methods should produce valid weight matrices
        for method in ['ols', 'diagonal', 'sample', 'shrinkage']:
            weights = compute_wls_weights(data=data, method=method)
            is_valid, message = validate_weight_matrix(weights)
            assert is_valid, f"Failed for method {method}: {message}"

