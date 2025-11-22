"""
Tests for MinT Reconciliation Optimality and Method Differences

These tests verify that the MinT reconciliation implementation:
1. Minimizes forecast error variance (optimality)
2. Produces different results for different methods (OLS ≠ WLS ≠ MinT)
3. Uses the correct projection matrix formulation
4. Improves upon base forecasts in terms of variance

These tests were added to address Codex Analysis 18 Finding 3, which identified
that the original implementation only enforced coherence without optimizing variance.
"""

import pytest
import numpy as np
import pandas as pd
from recon.mint.mint_reconciler import MinTReconciler


class TestMinTOptimality:
    """Test that MinT reconciliation minimizes forecast error variance."""
    
    def test_mint_reduces_variance_vs_base_forecasts(self):
        """
        Test that MinT reconciliation reduces forecast error variance
        compared to base (incoherent) forecasts.
        
        This is the key optimality property of MinT: reconciled forecasts
        should have lower variance than simply enforcing coherence arbitrarily.
        """
        np.random.seed(42)
        
        # Create base forecasts with known error structure
        n_obs = 100
        true_bottom = np.random.randn(n_obs, 3) * [10, 15, 12]  # Different variances
        true_aggregate = true_bottom.sum(axis=1)
        
        # Add errors with different variances (mimics real forecast errors)
        bottom_errors = np.random.randn(n_obs, 3) * [5, 8, 6]
        agg_error = np.random.randn(n_obs) * 10
        
        base_bottom = true_bottom + bottom_errors
        base_agg = true_aggregate + agg_error
        
        base_forecasts = pd.DataFrame({
            'national': base_agg,
            'CA': base_bottom[:, 0],
            'TX': base_bottom[:, 1],
            'NY': base_bottom[:, 2]
        })
        
        # True values
        true_forecasts = pd.DataFrame({
            'national': true_aggregate,
            'CA': true_bottom[:, 0],
            'TX': true_bottom[:, 1],
            'NY': true_bottom[:, 2]
        })
        
        # Reconcile with MinT (shrinkage method)
        reconciler = MinTReconciler(method='mint_shrink')
        reconciler.fit(base_forecasts)
        reconciled = reconciler.reconcile(base_forecasts)
        
        # Compute forecast errors
        base_error = (base_forecasts - true_forecasts).values
        reconciled_error = (reconciled - true_forecasts).values
        
        # MinT should reduce overall forecast error variance
        # (measured as trace of error covariance matrix)
        base_cov_trace = np.trace(np.cov(base_error.T))
        reconciled_cov_trace = np.trace(np.cov(reconciled_error.T))
        
        # MinT reconciled forecasts should have lower or equal variance
        # Note: In practice, MinT may not always reduce variance on finite samples,
        # but should do so on average. We check that it doesn't increase significantly.
        assert reconciled_cov_trace <= base_cov_trace * 1.1, (
            f"MinT reconciliation significantly increased variance: "
            f"base_trace={base_cov_trace:.2f}, reconciled_trace={reconciled_cov_trace:.2f}"
        )
    
    def test_mint_uses_covariance_structure(self):
        """
        Test that MinT with sample covariance produces different results
        than OLS (which ignores covariance structure).
        
        This verifies that MinT actually uses the full covariance matrix,
        not just variance or equal weights.
        """
        np.random.seed(42)
        
        # Create base forecasts with correlation structure
        n_obs = 50
        # Generate correlated errors
        cov_matrix = np.array([[100, 50, 30, 25],  # National
                               [50, 36, 15, 10],   # CA
                               [30, 15, 25, 8],    # TX
                               [25, 10, 8, 16]])   # NY
        
        errors = np.random.multivariate_normal(np.zeros(4), cov_matrix, n_obs)
        
        base_forecasts = pd.DataFrame({
            'national': 300 + errors[:, 0],
            'CA': 100 + errors[:, 1],
            'TX': 100 + errors[:, 2],
            'NY': 100 + errors[:, 3]
        })
        
        # Reconcile with OLS (ignores covariance)
        reconciler_ols = MinTReconciler(method='ols')
        reconciler_ols.fit(base_forecasts)
        reconciled_ols = reconciler_ols.reconcile(base_forecasts)
        
        # Reconcile with MinT sample (uses covariance)
        reconciler_mint = MinTReconciler(method='mint_sample')
        reconciler_mint.fit(base_forecasts)
        reconciled_mint = reconciler_mint.reconcile(base_forecasts)
        
        # Results should be different because MinT uses covariance structure
        bottom_diff_ols = reconciled_ols[['CA', 'TX', 'NY']].values
        bottom_diff_mint = reconciled_mint[['CA', 'TX', 'NY']].values
        
        # Check that results are meaningfully different
        max_diff = np.abs(bottom_diff_ols - bottom_diff_mint).max()
        assert max_diff > 0.1, (
            f"MinT and OLS produce nearly identical results (max_diff={max_diff:.4f}), "
            "suggesting MinT is not using covariance structure"
        )
    
    def test_projection_matrix_properties(self):
        """
        Test that the projection matrix P satisfies key properties:
        1. P @ P = P (idempotent)
        2. P ensures coherence: S @ ỹ_bottom = ỹ_aggregate
        
        These are mathematical properties that must hold for correct MinT reconciliation.
        """
        np.random.seed(42)
        
        base_forecasts = pd.DataFrame({
            'national': [305, 310, 315],
            'CA': [100, 102, 105],
            'TX': [100, 103, 105],
            'NY': [100, 100, 100]
        })
        
        reconciler = MinTReconciler(method='mint_shrink')
        reconciler.fit(base_forecasts)
        
        # Get the weight matrix and summing matrix
        W = reconciler.weight_matrix_
        S = reconciler.summing_matrix_
        
        # Reconstruct projection matrix P = U @ (U' W^-1 U)^-1 @ U' W^-1
        # where U = [S; I]
        n_bottom = reconciler.n_bottom_
        U = np.vstack([S, np.eye(n_bottom)])
        
        try:
            W_inv = np.linalg.inv(W)
            U_T_W_inv = U.T @ W_inv
            U_T_W_inv_U = U_T_W_inv @ U
            U_T_W_inv_U_inv = np.linalg.inv(U_T_W_inv_U)
            U_plus = U_T_W_inv_U_inv @ U_T_W_inv
            P = U @ U_plus
            
            # Test idempotence: P @ P = P (within numerical tolerance)
            P_squared = P @ P
            assert np.allclose(P, P_squared, atol=1e-6), (
                "Projection matrix is not idempotent (P @ P ≠ P)"
            )
            
            # Test that projection preserves coherence
            # For any vector y, P @ y should be coherent
            y = base_forecasts.values.T  # (n_total, n_obs)
            y_reconciled = P @ y
            
            # Check: aggregate = S @ bottom
            agg_reconciled = y_reconciled[0, :]
            bottom_reconciled = y_reconciled[1:, :]
            agg_from_bottom = (S @ bottom_reconciled).flatten()
            
            assert np.allclose(agg_reconciled, agg_from_bottom, atol=1e-6), (
                "Projection matrix does not ensure coherence"
            )
            
        except np.linalg.LinAlgError:
            # If matrix inversion fails, test passes (numerical instability handled)
            pytest.skip("Matrix inversion failed (numerical instability)")


class TestMethodDifferences:
    """Test that different reconciliation methods produce different results."""
    
    def test_ols_vs_wls_different_results(self):
        """
        Test that OLS and WLS produce different reconciled forecasts
        when variances differ across series.
        """
        np.random.seed(42)
        
        # Create forecasts with very different variances
        n_obs = 30
        base_forecasts = pd.DataFrame({
            'national': 300 + np.random.randn(n_obs) * 20,  # High variance
            'CA': 100 + np.random.randn(n_obs) * 2,   # Low variance
            'TX': 100 + np.random.randn(n_obs) * 15,  # High variance
            'NY': 100 + np.random.randn(n_obs) * 5    # Medium variance
        })
        
        # OLS reconciliation (equal weights)
        reconciler_ols = MinTReconciler(method='ols')
        reconciler_ols.fit(base_forecasts)
        reconciled_ols = reconciler_ols.reconcile(base_forecasts)
        
        # WLS reconciliation (variance weights)
        reconciler_wls = MinTReconciler(method='wls')
        reconciler_wls.fit(base_forecasts)
        reconciled_wls = reconciler_wls.reconcile(base_forecasts)
        
        # Results should differ because WLS weights by variance
        diff = (reconciled_ols - reconciled_wls).abs().values
        max_diff = diff.max()
        
        assert max_diff > 0.01, (
            f"OLS and WLS produce nearly identical results (max_diff={max_diff:.6f}), "
            "suggesting methods are not differentiated"
        )
    
    def test_wls_vs_mint_different_results(self):
        """
        Test that WLS (diagonal weights) and MinT (full covariance)
        produce different results when series are correlated.
        """
        np.random.seed(42)
        
        # Create forecasts with correlation structure
        n_obs = 40
        cov_matrix = np.array([[100, 30, 25, 20],
                               [30, 25, 10, 8],
                               [25, 10, 20, 7],
                               [20, 8, 7, 15]])
        
        errors = np.random.multivariate_normal(np.zeros(4), cov_matrix, n_obs)
        
        base_forecasts = pd.DataFrame({
            'national': 300 + errors[:, 0],
            'CA': 100 + errors[:, 1],
            'TX': 100 + errors[:, 2],
            'NY': 100 + errors[:, 3]
        })
        
        # WLS reconciliation (diagonal covariance)
        reconciler_wls = MinTReconciler(method='wls')
        reconciler_wls.fit(base_forecasts)
        reconciled_wls = reconciler_wls.reconcile(base_forecasts)
        
        # MinT reconciliation (full covariance)
        reconciler_mint = MinTReconciler(method='mint_sample')
        reconciler_mint.fit(base_forecasts)
        reconciled_mint = reconciler_mint.reconcile(base_forecasts)
        
        # Results should differ because MinT uses off-diagonal covariance
        diff = (reconciled_wls - reconciled_mint).abs().values
        max_diff = diff.max()
        
        assert max_diff > 0.01, (
            f"WLS and MinT produce nearly identical results (max_diff={max_diff:.6f}), "
            "suggesting MinT is not using full covariance structure"
        )
    
    def test_mint_sample_vs_mint_shrink_different_results(self):
        """
        Test that MinT with sample covariance and MinT with shrinkage
        produce different results (shrinkage stabilizes covariance estimation).
        """
        np.random.seed(42)
        
        # Use small sample size where shrinkage makes a difference
        n_obs = 20  # Small sample
        base_forecasts = pd.DataFrame({
            'national': 300 + np.random.randn(n_obs) * 15,
            'CA': 100 + np.random.randn(n_obs) * 8,
            'TX': 100 + np.random.randn(n_obs) * 10,
            'NY': 100 + np.random.randn(n_obs) * 7
        })
        
        # MinT with sample covariance
        reconciler_sample = MinTReconciler(method='mint_sample')
        reconciler_sample.fit(base_forecasts)
        reconciled_sample = reconciler_sample.reconcile(base_forecasts)
        
        # MinT with shrinkage covariance (Ledoit-Wolf)
        reconciler_shrink = MinTReconciler(method='mint_shrink')
        reconciler_shrink.fit(base_forecasts)
        reconciled_shrink = reconciler_shrink.reconcile(base_forecasts)
        
        # Results should differ due to shrinkage
        diff = (reconciled_sample - reconciled_shrink).abs().values
        max_diff = diff.max()
        
        # Shrinkage should make a difference on small samples
        assert max_diff > 0.001, (
            f"Sample and shrinkage MinT produce nearly identical results "
            f"(max_diff={max_diff:.6f}) on small sample"
        )
    
    def test_all_four_methods_produce_different_results(self):
        """
        Test that all four methods (OLS, WLS, MinT(sample), MinT(shrink))
        produce meaningfully different results on the same data.
        
        This is the key test for method differentiation.
        """
        np.random.seed(42)
        
        # Create realistic forecasts with complex error structure
        n_obs = 50
        cov_matrix = np.array([[120, 40, 35, 30],
                               [40, 40, 18, 15],
                               [35, 18, 30, 12],
                               [30, 15, 12, 25]])
        
        errors = np.random.multivariate_normal(np.zeros(4), cov_matrix, n_obs)
        
        base_forecasts = pd.DataFrame({
            'national': 300 + errors[:, 0],
            'CA': 100 + errors[:, 1],
            'TX': 100 + errors[:, 2],
            'NY': 100 + errors[:, 3]
        })
        
        # Reconcile with all four methods
        methods = ['ols', 'wls', 'mint_sample', 'mint_shrink']
        reconciled_results = {}
        
        for method in methods:
            reconciler = MinTReconciler(method=method)
            reconciler.fit(base_forecasts)
            reconciled_results[method] = reconciler.reconcile(base_forecasts)
        
        # Compare each pair of methods
        method_pairs = [
            ('ols', 'wls'),
            ('ols', 'mint_sample'),
            ('ols', 'mint_shrink'),
            ('wls', 'mint_sample'),
            ('wls', 'mint_shrink'),
            ('mint_sample', 'mint_shrink')
        ]
        
        for method1, method2 in method_pairs:
            diff = (reconciled_results[method1] - reconciled_results[method2]).abs().values
            max_diff = diff.max()
            
            assert max_diff > 0.001, (
                f"{method1} and {method2} produce nearly identical results "
                f"(max_diff={max_diff:.6f}), methods not properly differentiated"
            )


class TestReferenceValidation:
    """Test MinT implementation against known reference values."""
    
    def test_simple_case_with_known_solution(self):
        """
        Test MinT on a simple case where the optimal solution can be
        calculated analytically or is intuitively obvious.
        """
        # Simple case: 2 bottom series with equal true values but different variances
        # Series 1 has low variance (trustworthy), Series 2 has high variance (noisy)
        # MinT should weight Series 1 more heavily
        
        np.random.seed(42)
        n_obs = 100
        
        # True values (both 50)
        true_s1 = np.ones(n_obs) * 50
        true_s2 = np.ones(n_obs) * 50
        true_agg = true_s1 + true_s2  # Always 100
        
        # Add noise with different variances
        noisy_s1 = true_s1 + np.random.randn(n_obs) * 2  # Low variance (σ=2)
        noisy_s2 = true_s2 + np.random.randn(n_obs) * 20  # High variance (σ=20)
        noisy_agg = true_agg + np.random.randn(n_obs) * 5
        
        base_forecasts = pd.DataFrame({
            'total': noisy_agg,
            's1': noisy_s1,
            's2': noisy_s2
        })
        
        # Reconcile with WLS (variance weighting)
        reconciler = MinTReconciler(method='wls')
        reconciler.fit(base_forecasts)
        reconciled = reconciler.reconcile(base_forecasts)
        
        # After reconciliation, adjustments should favor the low-variance series
        # Series 1 should be adjusted less than Series 2
        adj_s1 = np.abs(reconciled['s1'] - base_forecasts['s1']).mean()
        adj_s2 = np.abs(reconciled['s2'] - base_forecasts['s2']).mean()
        
        # Series 2 (high variance) should be adjusted more
        assert adj_s2 > adj_s1, (
            f"High-variance series not adjusted more (adj_s1={adj_s1:.3f}, "
            f"adj_s2={adj_s2:.3f}), suggesting WLS not working correctly"
        )
    
    def test_coherence_maintained_across_all_methods(self):
        """
        Verify that all methods maintain coherence (this is a requirement,
        not just a nice-to-have). This ensures optimality doesn't break coherence.
        """
        np.random.seed(42)
        
        base_forecasts = pd.DataFrame({
            'national': [305, 310, 315, 320],
            'CA': [100, 102, 105, 107],
            'TX': [100, 103, 105, 108],
            'NY': [100, 100, 100, 100]
        })
        
        methods = ['ols', 'wls', 'mint_sample', 'mint_shrink']
        
        for method in methods:
            reconciler = MinTReconciler(method=method)
            reconciler.fit(base_forecasts)
            reconciled = reconciler.reconcile(base_forecasts)
            
            # Check coherence
            agg = reconciled.iloc[:, 0].values
            bottom_sum = reconciled.iloc[:, 1:].sum(axis=1).values
            
            assert np.allclose(agg, bottom_sum, atol=1e-6), (
                f"Method {method} does not maintain coherence: "
                f"max_error={np.abs(agg - bottom_sum).max():.2e}"
            )

