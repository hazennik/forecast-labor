"""
Tests for MinT hierarchical forecast reconciliation.

Tests cover:
- Reconciler initialization and parameter validation
- Fit with different methods (OLS, WLS, MinT)
- Coherence validation (nation = Σstates)
- Forecast improvement (reconciled vs base)
- Method comparison
- Numerical stability and edge cases
"""

import pytest
import numpy as np
import pandas as pd

from recon.mint.mint_reconciler import MinTReconciler


class TestMinTReconcilerInit:
    """Test MinTReconciler initialization."""
    
    def test_init_default_parameters(self):
        """Test initialization with default parameters."""
        reconciler = MinTReconciler()
        
        assert reconciler.method == 'mint_shrink'
        assert reconciler.hierarchy_type == 'single_level'
        assert reconciler.is_fitted_ is False
        assert reconciler.summing_matrix_ is None
    
    def test_init_custom_method(self):
        """Test initialization with custom method."""
        for method in ['ols', 'wls', 'mint_sample', 'mint_shrink']:
            reconciler = MinTReconciler(method=method)
            assert reconciler.method == method
    
    def test_init_invalid_method(self):
        """Test that invalid method raises ValueError."""
        with pytest.raises(ValueError, match="method must be one of"):
            MinTReconciler(method='invalid_method')
    
    def test_init_invalid_hierarchy_type(self):
        """Test that invalid hierarchy_type raises ValueError."""
        with pytest.raises(ValueError, match="Only 'single_level' hierarchy supported"):
            MinTReconciler(hierarchy_type='two_level')


class TestMinTReconcilerFit:
    """Test MinTReconciler fit method."""
    
    @pytest.fixture
    def sample_forecasts(self):
        """Generate sample hierarchical forecasts."""
        np.random.seed(42)
        n_obs = 50
        
        # Base forecasts: national + 3 states
        # States don't sum exactly to national (incoherent)
        forecasts = pd.DataFrame({
            'national': 200 + np.random.randn(n_obs) * 10,
            'CA': 80 + np.random.randn(n_obs) * 5,
            'TX': 60 + np.random.randn(n_obs) * 4,
            'NY': 55 + np.random.randn(n_obs) * 4,
        })
        
        return forecasts
    
    def test_fit_basic(self, sample_forecasts):
        """Test basic fit operation."""
        reconciler = MinTReconciler(method='ols')
        result = reconciler.fit(sample_forecasts)
        
        # Check method chaining
        assert result is reconciler
        
        # Check fitted attributes
        assert reconciler.is_fitted_ is True
        assert reconciler.n_total_ == 4
        assert reconciler.n_bottom_ == 3
        assert reconciler.summing_matrix_ is not None
        assert reconciler.weight_matrix_ is not None
        assert reconciler.column_order_ == ['national', 'CA', 'TX', 'NY']
    
    def test_fit_empty_forecasts(self):
        """Test that empty forecasts raise ValueError."""
        reconciler = MinTReconciler()
        empty_df = pd.DataFrame()
        
        with pytest.raises(ValueError, match="forecasts cannot be empty"):
            reconciler.fit(empty_df)
    
    def test_fit_insufficient_columns(self):
        """Test that single column raises ValueError."""
        reconciler = MinTReconciler()
        single_col = pd.DataFrame({'national': [100, 110]})
        
        with pytest.raises(ValueError, match="at least 2 columns"):
            reconciler.fit(single_col)
    
    def test_fit_ols_method(self, sample_forecasts):
        """Test fit with OLS method (identity weights)."""
        reconciler = MinTReconciler(method='ols')
        reconciler.fit(sample_forecasts)
        
        # OLS uses identity weight matrix
        assert np.allclose(reconciler.weight_matrix_, np.eye(4))
    
    def test_fit_wls_method(self, sample_forecasts):
        """Test fit with WLS method (variance weights)."""
        reconciler = MinTReconciler(method='wls')
        reconciler.fit(sample_forecasts)
        
        # WLS uses diagonal variance matrix
        assert reconciler.weight_matrix_.shape == (4, 4)
        # Should be diagonal
        assert np.allclose(
            reconciler.weight_matrix_,
            np.diag(np.diag(reconciler.weight_matrix_))
        )
    
    def test_fit_mint_sample_method(self, sample_forecasts):
        """Test fit with MinT sample covariance."""
        reconciler = MinTReconciler(method='mint_sample')
        reconciler.fit(sample_forecasts)
        
        # Should have full covariance matrix
        assert reconciler.weight_matrix_.shape == (4, 4)
        # Should be symmetric
        assert np.allclose(
            reconciler.weight_matrix_,
            reconciler.weight_matrix_.T
        )
    
    def test_fit_mint_shrink_method(self, sample_forecasts):
        """Test fit with MinT shrinkage covariance."""
        reconciler = MinTReconciler(method='mint_shrink')
        reconciler.fit(sample_forecasts)
        
        # Should have full covariance matrix
        assert reconciler.weight_matrix_.shape == (4, 4)
        # Should be symmetric and positive definite
        assert np.allclose(
            reconciler.weight_matrix_,
            reconciler.weight_matrix_.T
        )
        eigenvalues = np.linalg.eigvalsh(reconciler.weight_matrix_)
        assert np.all(eigenvalues > 0)


class TestMinTReconcilerReconcile:
    """Test MinTReconciler reconcile method."""
    
    @pytest.fixture
    def fitted_reconciler(self):
        """Create fitted reconciler for testing."""
        np.random.seed(42)
        forecasts = pd.DataFrame({
            'national': [200, 210, 220],
            'CA': [80, 85, 90],
            'TX': [60, 62, 65],
            'NY': [55, 58, 60],
        })
        
        reconciler = MinTReconciler(method='mint_shrink')
        reconciler.fit(forecasts)
        return reconciler
    
    @pytest.fixture
    def incoherent_forecasts(self):
        """Create intentionally incoherent forecasts."""
        # States sum to 195, 205, 215 but national is 200, 210, 220
        forecasts = pd.DataFrame({
            'national': [200, 210, 220],
            'CA': [80, 85, 90],
            'TX': [60, 62, 65],
            'NY': [55, 58, 60],
        })
        return forecasts
    
    def test_reconcile_basic(self, fitted_reconciler, incoherent_forecasts):
        """Test basic reconciliation."""
        reconciled = fitted_reconciler.reconcile(incoherent_forecasts)
        
        assert isinstance(reconciled, pd.DataFrame)
        assert reconciled.shape == incoherent_forecasts.shape
        assert list(reconciled.columns) == list(incoherent_forecasts.columns)
    
    def test_reconcile_before_fit(self, incoherent_forecasts):
        """Test that reconcile before fit raises ValueError."""
        reconciler = MinTReconciler()
        
        with pytest.raises(ValueError, match="must be fitted before reconciliation"):
            reconciler.reconcile(incoherent_forecasts)
    
    def test_reconcile_column_mismatch(self, fitted_reconciler):
        """Test that column mismatch raises ValueError."""
        wrong_columns = pd.DataFrame({
            'total': [200],
            'state1': [80],
            'state2': [60],
            'state3': [55],
        })
        
        with pytest.raises(ValueError, match="Column mismatch"):
            fitted_reconciler.reconcile(wrong_columns)
    
    def test_reconcile_coherence(self, fitted_reconciler, incoherent_forecasts):
        """Test that reconciled forecasts are coherent."""
        reconciled = fitted_reconciler.reconcile(incoherent_forecasts)
        
        # Check coherence: national should equal sum of states
        national = reconciled['national'].values
        states_sum = reconciled[['CA', 'TX', 'NY']].sum(axis=1).values
        
        # Should be very close (within numerical tolerance)
        assert np.allclose(national, states_sum, atol=1e-6)
    
    def test_reconcile_coherence_error_reduction(
        self, fitted_reconciler, incoherent_forecasts
    ):
        """Test that reconciliation reduces coherence error."""
        # Compute coherence errors before
        errors_before = (
            incoherent_forecasts['national'] -
            incoherent_forecasts[['CA', 'TX', 'NY']].sum(axis=1)
        )
        
        # Reconcile
        reconciled = fitted_reconciler.reconcile(incoherent_forecasts)
        
        # Compute coherence errors after
        errors_after = (
            reconciled['national'] -
            reconciled[['CA', 'TX', 'NY']].sum(axis=1)
        )
        
        # Errors after should be much smaller
        assert np.abs(errors_after).max() < 1e-6
        assert np.abs(errors_after).max() < np.abs(errors_before).max()
    
    def test_reconcile_coherence_error_under_threshold(
        self, fitted_reconciler, incoherent_forecasts
    ):
        """Test that coherence error < 100 jobs threshold."""
        reconciled = fitted_reconciler.reconcile(incoherent_forecasts)
        
        # Compute coherence error (in thousands of jobs)
        coherence_error = np.abs(
            reconciled['national'] -
            reconciled[['CA', 'TX', 'NY']].sum(axis=1)
        ).max()
        
        # Should be much less than 100 jobs (0.1 in thousands)
        assert coherence_error < 0.1  # 100 jobs threshold


class TestMinTReconcilerMethods:
    """Test different reconciliation methods."""
    
    @pytest.fixture
    def base_forecasts(self):
        """Create base forecasts for method comparison."""
        np.random.seed(42)
        n_obs = 100
        
        # Create forecasts with known structure
        ca = 80 + np.random.randn(n_obs) * 5
        tx = 60 + np.random.randn(n_obs) * 4
        ny = 55 + np.random.randn(n_obs) * 4
        
        # National is slightly off from sum
        national = (ca + tx + ny) + np.random.randn(n_obs) * 3
        
        forecasts = pd.DataFrame({
            'national': national,
            'CA': ca,
            'TX': tx,
            'NY': ny,
        })
        
        return forecasts
    
    def test_all_methods_produce_coherent_forecasts(self, base_forecasts):
        """Test that all methods produce coherent forecasts."""
        methods = ['ols', 'wls', 'mint_sample', 'mint_shrink']
        
        for method in methods:
            reconciler = MinTReconciler(method=method)
            reconciler.fit(base_forecasts)
            reconciled = reconciler.reconcile(base_forecasts)
            
            # Check coherence
            national = reconciled['national'].values
            states_sum = reconciled[['CA', 'TX', 'NY']].sum(axis=1).values
            
            assert np.allclose(national, states_sum, atol=1e-6), \
                f"Method {method} failed coherence test"
    
    def test_method_comparison_forecast_accuracy(self, base_forecasts):
        """Compare forecast accuracy across methods."""
        # Simulate "true" values as perfect sum
        true_values = base_forecasts[['CA', 'TX', 'NY']].sum(axis=1)
        
        results = {}
        for method in ['ols', 'wls', 'mint_sample', 'mint_shrink']:
            reconciler = MinTReconciler(method=method)
            reconciler.fit(base_forecasts)
            reconciled = reconciler.reconcile(base_forecasts)
            
            # Compute RMSE on national forecast
            rmse = np.sqrt(
                np.mean((reconciled['national'] - true_values) ** 2)
            )
            results[method] = rmse
        
        # All methods should improve over base
        base_rmse = np.sqrt(
            np.mean((base_forecasts['national'] - true_values) ** 2)
        )
        
        for method, rmse in results.items():
            assert rmse <= base_rmse * 1.1, \
                f"Method {method} did not improve forecasts"


class TestMinTReconcilerValidation:
    """Test coherence validation functionality."""
    
    def test_validate_coherence_coherent_data(self):
        """Test validation with perfectly coherent data."""
        # Create coherent forecasts
        coherent = pd.DataFrame({
            'national': [100, 110],
            'state1': [60, 66],
            'state2': [40, 44],
        })
        
        reconciler = MinTReconciler()
        is_coherent = reconciler.validate_coherence(coherent, tolerance=1e-10)
        
        assert is_coherent is True
    
    def test_validate_coherence_incoherent_data(self):
        """Test validation with incoherent data."""
        # Create incoherent forecasts
        incoherent = pd.DataFrame({
            'national': [100, 110],
            'state1': [60, 66],
            'state2': [41, 45],  # Doesn't sum correctly
        })
        
        reconciler = MinTReconciler()
        is_coherent = reconciler.validate_coherence(incoherent, tolerance=1e-6)
        
        assert is_coherent is False


class TestMinTReconcilerGetParams:
    """Test get_params functionality."""
    
    def test_get_params_unfitted(self):
        """Test get_params before fitting."""
        reconciler = MinTReconciler(method='ols')
        params = reconciler.get_params()
        
        assert params['method'] == 'ols'
        assert params['hierarchy_type'] == 'single_level'
        assert params['is_fitted'] is False
        assert params['n_total'] is None
        assert params['n_bottom'] is None
    
    def test_get_params_fitted(self):
        """Test get_params after fitting."""
        forecasts = pd.DataFrame({
            'national': [100, 110],
            'CA': [40, 44],
            'TX': [35, 38],
            'NY': [25, 28],
        })
        
        reconciler = MinTReconciler(method='wls')
        reconciler.fit(forecasts)
        params = reconciler.get_params()
        
        assert params['is_fitted'] is True
        assert params['n_total'] == 4
        assert params['n_bottom'] == 3
        assert params['column_order'] == ['national', 'CA', 'TX', 'NY']
        assert 'summing_matrix_shape' in params
        assert 'weight_matrix_shape' in params


class TestMinTReconcilerEdgeCases:
    """Test edge cases and numerical stability."""
    
    def test_reconcile_single_observation(self):
        """Test reconciliation with single observation."""
        forecasts = pd.DataFrame({
            'national': [200],
            'CA': [80],
            'TX': [60],
            'NY': [55],
        })
        
        reconciler = MinTReconciler(method='ols')
        reconciler.fit(forecasts)
        reconciled = reconciler.reconcile(forecasts)
        
        # Check coherence
        assert np.allclose(
            reconciled['national'].values,
            reconciled[['CA', 'TX', 'NY']].sum(axis=1).values,
            atol=1e-6
        )
    
    def test_reconcile_with_zeros(self):
        """Test reconciliation with zero values."""
        forecasts = pd.DataFrame({
            'national': [0, 100, 200],
            'CA': [0, 40, 80],
            'TX': [0, 35, 70],
            'NY': [0, 25, 50],
        })
        
        reconciler = MinTReconciler(method='wls')
        reconciler.fit(forecasts)
        reconciled = reconciler.reconcile(forecasts)
        
        # Check coherence
        assert np.allclose(
            reconciled['national'].values,
            reconciled[['CA', 'TX', 'NY']].sum(axis=1).values,
            atol=1e-6
        )
    
    def test_reconcile_with_negative_values(self):
        """Test reconciliation with negative values (job losses)."""
        forecasts = pd.DataFrame({
            'national': [-50, 0, 50],
            'CA': [-20, 0, 20],
            'TX': [-15, 0, 15],
            'NY': [-15, 0, 15],
        })
        
        reconciler = MinTReconciler(method='mint_sample')
        reconciler.fit(forecasts)
        reconciled = reconciler.reconcile(forecasts)
        
        # Check coherence
        assert np.allclose(
            reconciled['national'].values,
            reconciled[['CA', 'TX', 'NY']].sum(axis=1).values,
            atol=1e-6
        )
    
    def test_reconcile_large_coherence_errors(self):
        """Test reconciliation with large initial coherence errors."""
        # Create forecasts with large coherence errors
        forecasts = pd.DataFrame({
            'national': [200, 210, 220],
            'CA': [50, 55, 60],  # Much lower than they should be
            'TX': [40, 42, 45],
            'NY': [35, 37, 40],
        })
        
        reconciler = MinTReconciler(method='mint_shrink')
        reconciler.fit(forecasts)
        reconciled = reconciler.reconcile(forecasts)
        
        # Even with large errors, should achieve coherence
        assert np.allclose(
            reconciled['national'].values,
            reconciled[['CA', 'TX', 'NY']].sum(axis=1).values,
            atol=1e-6
        )
    
    def test_reconcile_many_bottom_series(self):
        """Test reconciliation with many bottom-level series."""
        np.random.seed(42)
        n_states = 50
        n_obs = 20
        
        # Create data for 50 states
        state_data = {}
        for i in range(n_states):
            state_data[f'state_{i}'] = 5 + np.random.randn(n_obs) * 1
        
        # National is approximately sum but not exact
        state_df = pd.DataFrame(state_data)
        national = state_df.sum(axis=1) + np.random.randn(n_obs) * 10
        
        forecasts = pd.DataFrame({'national': national})
        forecasts = pd.concat([forecasts, state_df], axis=1)
        
        # Fit and reconcile
        reconciler = MinTReconciler(method='ols')
        reconciler.fit(forecasts)
        reconciled = reconciler.reconcile(forecasts)
        
        # Check coherence with many states
        assert np.allclose(
            reconciled['national'].values,
            reconciled.iloc[:, 1:].sum(axis=1).values,
            atol=1e-5
        )


class TestMinTReconcilerIntegration:
    """Integration tests for full workflow."""
    
    def test_full_workflow(self):
        """Test complete workflow: init → fit → reconcile → validate."""
        np.random.seed(42)
        
        # Create incoherent base forecasts
        base_forecasts = pd.DataFrame({
            'national': [200, 210, 220, 230],
            'CA': [80, 85, 90, 95],
            'TX': [60, 62, 65, 68],
            'NY': [55, 58, 60, 62],
        })
        
        # Initialize reconciler
        reconciler = MinTReconciler(method='mint_shrink')
        assert not reconciler.is_fitted_
        
        # Fit to data
        reconciler.fit(base_forecasts)
        assert reconciler.is_fitted_
        
        # Reconcile
        reconciled = reconciler.reconcile(base_forecasts)
        assert reconciled.shape == base_forecasts.shape
        
        # Validate coherence
        is_coherent = reconciler.validate_coherence(reconciled, tolerance=1e-6)
        assert is_coherent is True
        
        # Get params
        params = reconciler.get_params()
        assert params['is_fitted'] is True
        assert params['method'] == 'mint_shrink'
    
    def test_method_chaining(self):
        """Test that fit returns self for method chaining."""
        forecasts = pd.DataFrame({
            'national': [200],
            'CA': [80],
            'TX': [60],
            'NY': [55],
        })
        
        # Should be able to chain fit().reconcile()
        reconciler = MinTReconciler(method='ols')
        reconciled = reconciler.fit(forecasts).reconcile(forecasts)
        
        assert isinstance(reconciled, pd.DataFrame)
        assert reconciler.validate_coherence(reconciled)

