"""
Property Tests for MIDAS Regression

Tests mathematical properties and algorithmic invariants:
- Almon Weights: Sum to 1, non-negative, decay pattern
- NLS Convergence: Final loss better than baseline
- Gradient Properties: Optimization converged
- Weight Structure: Reasonable lag decay

Purpose: Prevent TDD blindspots by testing mathematical correctness,
         not just observable behavior.

Reference: docs/TESTING_MATHEMATICAL_ALGORITHMS.md
"""

import pytest
import numpy as np
import pandas as pd
from datetime import datetime

from models_src.midas.midas_model import MIDASRegression


class TestAlmonWeightProperties:
    """Test mathematical properties of Almon polynomial weights"""
    
    @pytest.fixture
    def fitted_model(self):
        """Create a fitted MIDAS model"""
        np.random.seed(42)
        n_obs = 100
        dates = pd.date_range('2014-01-01', periods=n_obs, freq='ME')
        
        # Create high-frequency lags
        X = pd.DataFrame({
            f'lag_{i}': np.random.normal(100, 10, n_obs) + i * 0.5
            for i in range(20)
        }, index=dates)
        
        # Target with trend
        y = pd.Series(
            np.random.normal(150, 50, n_obs) + np.arange(n_obs) * 0.5,
            index=dates,
            name='nfp_change'
        )
        
        model = MIDASRegression(almon_degree=2, n_lags=20, random_state=42)
        model.fit(X, y, vintage_date='2024-11-15')
        
        return model
    
    def test_almon_weights_sum_to_one(self, fitted_model):
        """
        Almon polynomial weights must sum to 1.0.
        
        Mathematical Property:
            Σ w_i = 1.0 (normalized weights)
        
        Purpose: Verify that weights form a valid probability distribution
                 over lags, ensuring interpretability.
        
        Note: This property is already tested in test_midas.py:166-172,
              but we include it here as it's a fundamental property.
        """
        weights = fitted_model.almon_weights_
        
        weight_sum = np.sum(weights)
        
        assert np.abs(weight_sum - 1.0) < 1e-6, \
            f"Almon weights sum to {weight_sum:.8f}, expected 1.0"
    
    def test_almon_weights_non_negative(self, fitted_model):
        """
        Almon weights should be non-negative.
        
        Mathematical Property:
            w_i >= 0 for all i
        
        Purpose: Verify that weight constraints are satisfied.
                 Negative weights would indicate problematic lag structure.
        """
        weights = fitted_model.almon_weights_
        
        min_weight = np.min(weights)
        
        # Allow small negative values due to numerical precision
        assert min_weight >= -1e-10, \
            f"Almon weights have negative values: min = {min_weight:.2e}"
    
    def test_almon_weights_decay_pattern(self, fitted_model):
        """
        Almon weights should generally follow a decay pattern.
        
        Mathematical Property:
            Weights typically decrease with lag (older data less important)
        
        Purpose: Verify that weights have reasonable structure.
                 Erratic patterns might indicate optimization failure.
        
        Note: This is a soft constraint - some applications might
              have increasing patterns. We just check for smoothness.
        """
        weights = fitted_model.almon_weights_
        
        # Check that weights don't have wild oscillations
        # Compute second differences (measure of smoothness)
        second_diffs = np.diff(weights, n=2)
        max_oscillation = np.max(np.abs(second_diffs))
        
        # Weights should be relatively smooth
        # (arbitrary threshold based on typical patterns)
        assert max_oscillation < 0.5, \
            f"Almon weights have large oscillations: max 2nd diff = {max_oscillation:.4f}"
    
    def test_almon_weights_all_finite(self, fitted_model):
        """
        Almon weights must be finite (no NaN or Inf).
        
        Mathematical Property:
            w_i is finite for all i
        
        Purpose: Verify numerical stability of weight computation.
        """
        weights = fitted_model.almon_weights_
        
        assert np.all(np.isfinite(weights)), \
            f"Almon weights contain non-finite values: {weights}"


class TestNLSOptimizationProperties:
    """Test properties of NLS optimization"""
    
    @pytest.fixture
    def sample_data(self):
        """Create synthetic data for testing"""
        np.random.seed(42)
        n_obs = 100
        dates = pd.date_range('2014-01-01', periods=n_obs, freq='ME')
        
        # Create high-frequency lags
        X = pd.DataFrame({
            f'lag_{i}': np.random.normal(100, 10, n_obs) + i * 0.5
            for i in range(20)
        }, index=dates)
        
        # Target with linear relationship
        true_weights = np.exp(-np.arange(20) * 0.1)
        true_weights /= true_weights.sum()
        
        y_signal = (X.values * true_weights).sum(axis=1)
        y = pd.Series(
            y_signal + np.random.normal(0, 10, n_obs),
            index=dates,
            name='nfp_change'
        )
        
        return X, y
    
    def test_nls_achieves_lower_loss_than_baseline(self, sample_data):
        """
        NLS optimization must achieve lower loss than naive baseline.
        
        Mathematical Property:
            Loss(fitted model) < Loss(mean prediction)
        
        Purpose: Verify that optimization makes progress from initialization.
        """
        X, y = sample_data
        
        # Fit MIDAS model
        model = MIDASRegression(almon_degree=2, random_state=42)
        model.fit(X, y, vintage_date='2024-11-15')
        
        # Get MIDAS loss
        midas_loss = model.training_loss_
        
        # Compute baseline loss (just predict mean)
        baseline_pred = np.mean(y)
        baseline_loss = np.sum((y - baseline_pred) ** 2)
        
        # MIDAS should beat baseline
        assert midas_loss < baseline_loss, \
            f"MIDAS loss ({midas_loss:.2f}) >= baseline loss ({baseline_loss:.2f})"
    
    def test_nls_loss_finite(self, sample_data):
        """
        Final loss must be finite (no NaN or Inf).
        
        Mathematical Property:
            Loss is finite
        
        Purpose: Verify numerical stability of optimization.
        """
        X, y = sample_data
        
        model = MIDASRegression(almon_degree=2, random_state=42)
        model.fit(X, y, vintage_date='2024-11-15')
        
        loss = model.training_loss_
        
        assert np.isfinite(loss), \
            f"Training loss is not finite: {loss}"
    
    def test_nls_loss_non_negative(self, sample_data):
        """
        Sum of squared errors must be non-negative.
        
        Mathematical Property:
            Loss = Σ(y - ŷ)² >= 0
        
        Purpose: Verify that loss function is correctly computed.
        """
        X, y = sample_data
        
        model = MIDASRegression(almon_degree=2, random_state=42)
        model.fit(X, y, vintage_date='2024-11-15')
        
        loss = model.training_loss_
        
        assert loss >= 0, \
            f"Training loss is negative: {loss:.2e}"
    
    def test_nls_predictions_match_loss(self, sample_data):
        """
        Verify that training loss matches sum of squared residuals.
        
        Mathematical Property:
            Loss = Σ(y - model.predict(X))²
        
        Purpose: Verify consistency between loss and predictions.
        """
        X, y = sample_data
        
        model = MIDASRegression(almon_degree=2, random_state=42)
        model.fit(X, y, vintage_date='2024-11-15')
        
        # Compute loss from predictions
        predictions = model.predict(X)
        residuals = y.values - predictions
        computed_loss = np.sum(residuals ** 2)
        
        # Should match stored training loss
        assert np.abs(computed_loss - model.training_loss_) < 1e-6, \
            f"Computed loss ({computed_loss:.6f}) != stored loss ({model.training_loss_:.6f})"


class TestMIDASCoefficientsProperties:
    """Test properties of MIDAS coefficients"""
    
    @pytest.fixture
    def fitted_model(self):
        """Create a fitted MIDAS model"""
        np.random.seed(42)
        n_obs = 100
        dates = pd.date_range('2014-01-01', periods=n_obs, freq='ME')
        
        # Create high-frequency lags
        X = pd.DataFrame({
            f'lag_{i}': np.random.normal(100, 10, n_obs) + i * 0.5
            for i in range(20)
        }, index=dates)
        
        # Target
        y = pd.Series(
            np.random.normal(150, 50, n_obs),
            index=dates,
            name='nfp_change'
        )
        
        model = MIDASRegression(almon_degree=2, n_lags=20, random_state=42)
        model.fit(X, y, vintage_date='2024-11-15')
        
        return model
    
    def test_coefficients_all_finite(self, fitted_model):
        """
        All coefficients must be finite.
        
        Mathematical Property:
            β_i is finite for all i
        
        Purpose: Verify numerical stability of parameter estimation.
        """
        coefs = fitted_model.coefficients_
        
        assert np.all(np.isfinite(coefs)), \
            f"Coefficients contain non-finite values: {coefs}"
    
    def test_intercept_finite(self, fitted_model):
        """
        Intercept must be finite.
        
        Mathematical Property:
            β_0 is finite
        
        Purpose: Verify numerical stability of intercept estimation.
        """
        intercept = fitted_model.intercept_
        
        assert np.isfinite(intercept), \
            f"Intercept is not finite: {intercept}"
    
    def test_coefficients_reasonable_magnitude(self, fitted_model):
        """
        Coefficients should have reasonable magnitudes.
        
        Mathematical Property:
            |β_i| < 1e6 (not exploding)
        
        Purpose: Detect potential numerical issues or optimization failures.
                 Very large coefficients suggest problems.
        """
        coefs = fitted_model.coefficients_
        max_coef = np.max(np.abs(coefs))
        
        assert max_coef < 1e6, \
            f"Coefficients have very large magnitude: max |β| = {max_coef:.2e}"


class TestMIDASIntegrationWithProperties:
    """Integration tests that combine multiple mathematical properties"""
    
    def test_weights_and_loss_consistency(self):
        """
        Verify that weight properties and loss are consistent.
        
        Mathematical Property:
            Valid weights + finite loss = consistent model
        
        Purpose: Ensure all pieces work together correctly.
        """
        np.random.seed(42)
        n_obs = 100
        dates = pd.date_range('2014-01-01', periods=n_obs, freq='ME')
        
        X = pd.DataFrame({
            f'lag_{i}': np.random.normal(100, 10, n_obs)
            for i in range(15)
        }, index=dates)
        
        y = pd.Series(
            np.random.normal(150, 50, n_obs),
            index=dates,
            name='nfp_change'
        )
        
        model = MIDASRegression(almon_degree=2, n_lags=15, random_state=42)
        model.fit(X, y, vintage_date='2024-11-15')
        
        # Check all properties together
        weights = model.almon_weights_
        loss = model.training_loss_
        
        # Weights valid
        assert np.abs(np.sum(weights) - 1.0) < 1e-6
        assert np.all(weights >= -1e-10)
        assert np.all(np.isfinite(weights))
        
        # Loss valid
        assert np.isfinite(loss)
        assert loss >= 0
        
        # Predictions consistent
        predictions = model.predict(X)
        assert np.all(np.isfinite(predictions))
    
    def test_reproducibility_implies_stable_optimization(self):
        """
        Reproducibility implies optimization is deterministic.
        
        Mathematical Property:
            Same seed → same weights → same loss
        
        Purpose: Verify that NLS optimization is stable.
        
        Note: This is already tested in test_midas.py, but we verify
              it here to ensure optimization stability.
        """
        np.random.seed(42)
        n_obs = 50
        dates = pd.date_range('2014-01-01', periods=n_obs, freq='ME')
        
        X = pd.DataFrame({
            f'lag_{i}': np.random.normal(100, 10, n_obs)
            for i in range(10)
        }, index=dates)
        
        y = pd.Series(
            np.random.normal(150, 50, n_obs),
            index=dates,
            name='nfp_change'
        )
        
        # Fit twice with same seed
        model1 = MIDASRegression(almon_degree=2, random_state=42)
        model1.fit(X, y, vintage_date='2024-11-15')
        
        model2 = MIDASRegression(almon_degree=2, random_state=42)
        model2.fit(X, y, vintage_date='2024-11-15')
        
        # Weights should be identical
        np.testing.assert_array_almost_equal(
            model1.almon_weights_,
            model2.almon_weights_,
            decimal=10,
            err_msg="Weights not reproducible across runs"
        )
        
        # Loss should be identical
        assert np.abs(model1.training_loss_ - model2.training_loss_) < 1e-10, \
            f"Loss not reproducible: {model1.training_loss_} vs {model2.training_loss_}"

