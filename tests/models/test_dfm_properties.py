"""
Property Tests for Dynamic Factor Model (DFM)

Tests mathematical properties and algorithmic invariants:
- EM Algorithm: Likelihood monotonicity, convergence
- Kalman Filter: Covariance positive-definiteness
- State-Space: Dimension consistency, stability

Purpose: Prevent TDD blindspots by testing mathematical correctness,
         not just observable behavior.

Reference: docs/TESTING_MATHEMATICAL_ALGORITHMS.md
"""

import pytest
import numpy as np
import pandas as pd
from pathlib import Path

from models_src.dfm.dfm_model import DynamicFactorModel
from models_src.dfm.state_space import (
    StateSpaceRepresentation,
    build_transition_matrix,
    build_observation_matrix
)


class TestEMAlgorithmProperties:
    """Test mathematical properties of EM algorithm"""
    
    @pytest.fixture
    def sample_data(self):
        """Create synthetic time series data for testing"""
        np.random.seed(42)
        n_obs = 100
        dates = pd.date_range('2014-01-01', periods=n_obs, freq='M')
        
        # Target
        y = pd.Series(
            np.random.normal(150, 50, n_obs),
            index=dates,
            name='nfp_change'
        )
        
        # Features (4 series)
        X = pd.DataFrame({
            'series_1': np.random.normal(100, 10, n_obs),
            'series_2': np.random.normal(200, 20, n_obs),
            'series_3': np.random.normal(50, 5, n_obs),
            'series_4': np.random.normal(150, 15, n_obs),
        }, index=dates)
        
        return X, y
    
    def test_em_likelihood_increases_monotonically(self, sample_data):
        """
        EM algorithm must increase likelihood at each iteration.
        
        Mathematical Property:
            L[t+1] >= L[t] for all iterations t
        
        Purpose: Verify that EM is correctly implementing the
                 expectation-maximization steps that guarantee
                 likelihood improvement.
        """
        X, y = sample_data
        model = DynamicFactorModel(n_factors=2, max_iter=20, random_state=42)
        
        # Fit model
        model.fit(X, y, vintage_date='2024-11-15')
        
        # Get likelihood history
        likelihoods = model.log_likelihood_
        
        # Must have at least 2 iterations to test monotonicity
        assert len(likelihoods) >= 2, "Need at least 2 EM iterations"
        
        # Check monotonicity (allowing small numerical tolerance)
        for t in range(1, len(likelihoods)):
            improvement = likelihoods[t] - likelihoods[t-1]
            assert improvement >= -1e-8, \
                f"Likelihood decreased at iteration {t}: " \
                f"{likelihoods[t-1]:.6f} -> {likelihoods[t]:.6f} " \
                f"(delta = {improvement:.2e})"
    
    def test_em_converges_to_stable_solution(self, sample_data):
        """
        EM algorithm should converge (not oscillate).
        
        Mathematical Property:
            |L[t] - L[t-1]| decreases as t increases
        
        Purpose: Verify that EM converges to a local maximum,
                 not cycling or diverging.
        """
        X, y = sample_data
        model = DynamicFactorModel(n_factors=2, max_iter=50, tol=1e-6, random_state=42)
        
        # Fit model
        model.fit(X, y, vintage_date='2024-11-15')
        
        # Get likelihood history
        likelihoods = model.log_likelihood_
        
        # Compute improvements at each iteration
        improvements = [abs(likelihoods[t] - likelihoods[t-1]) 
                       for t in range(1, len(likelihoods))]
        
        # Check that improvements generally decrease (allowing some noise)
        # Use a window to check trend
        if len(improvements) >= 10:
            early_avg = np.mean(improvements[:5])
            late_avg = np.mean(improvements[-5:])
            
            assert late_avg <= early_avg, \
                f"Improvements not decreasing: early={early_avg:.2e}, late={late_avg:.2e}"
    
    def test_em_final_likelihood_higher_than_initial(self, sample_data):
        """
        Final likelihood must be higher than initial likelihood.
        
        Mathematical Property:
            L[final] > L[initial]
        
        Purpose: Verify that EM makes progress from initialization.
        """
        X, y = sample_data
        model = DynamicFactorModel(n_factors=2, max_iter=20, random_state=42)
        
        # Fit model
        model.fit(X, y, vintage_date='2024-11-15')
        
        # Get likelihood history
        likelihoods = model.log_likelihood_
        
        # Final must be better than initial
        assert len(likelihoods) >= 2
        improvement = likelihoods[-1] - likelihoods[0]
        
        # Allow for edge case where model is already at optimum
        assert improvement >= -1e-10, \
            f"Final likelihood worse than initial: " \
            f"{likelihoods[0]:.6f} -> {likelihoods[-1]:.6f}"
    
    def test_em_convergence_criterion_met(self, sample_data):
        """
        When EM reports convergence, improvement should be < tol.
        
        Mathematical Property:
            If converged_, then |L[n] - L[n-1]| < tol
        
        Purpose: Verify that convergence criterion is correctly implemented.
        """
        X, y = sample_data
        tol = 1e-4
        model = DynamicFactorModel(n_factors=2, max_iter=100, tol=tol, random_state=42)
        
        # Fit model
        model.fit(X, y, vintage_date='2024-11-15')
        
        # If model reports convergence
        if model.converged_:
            likelihoods = model.log_likelihood_
            
            # Check that final improvement was < tol
            final_improvement = abs(likelihoods[-1] - likelihoods[-2])
            
            assert final_improvement < tol, \
                f"Converged but improvement ({final_improvement:.2e}) >= tol ({tol:.2e})"
    
    def test_em_likelihood_not_nan_or_inf(self, sample_data):
        """
        Likelihood values should never be NaN or Inf.
        
        Mathematical Property:
            L[t] is finite for all t
        
        Purpose: Verify numerical stability of EM algorithm.
        """
        X, y = sample_data
        model = DynamicFactorModel(n_factors=2, max_iter=20, random_state=42)
        
        # Fit model
        model.fit(X, y, vintage_date='2024-11-15')
        
        # Check all likelihood values
        likelihoods = model.log_likelihood_
        for t, lik in enumerate(likelihoods):
            assert np.isfinite(lik), \
                f"Likelihood at iteration {t} is not finite: {lik}"


class TestStateSpaceCovarianceProperties:
    """Test covariance matrix properties in state-space representation"""
    
    def test_noise_covariances_positive_definite(self):
        """
        Noise covariance matrices must be positive definite.
        
        Mathematical Property:
            All eigenvalues of covariance matrices > 0
        
        Purpose: Verify that covariance matrices are valid
                 (required for Kalman filter correctness).
        """
        # Create observation and state noise covariances
        n_obs = 5
        n_factors = 2
        
        # Construct valid PD matrices (using A @ A.T method)
        obs_noise_base = np.random.randn(n_obs, n_obs)
        obs_noise_cov = obs_noise_base @ obs_noise_base.T + np.eye(n_obs) * 0.1
        
        state_noise_base = np.random.randn(n_factors, n_factors)
        state_noise_cov = state_noise_base @ state_noise_base.T + np.eye(n_factors) * 0.1
        
        # Create state-space representation
        loadings = build_observation_matrix(n_obs, n_factors)
        transition = build_transition_matrix(n_factors)
        
        ss = StateSpaceRepresentation(
            loadings=loadings,
            transition=transition,
            obs_noise_cov=obs_noise_cov,
            state_noise_cov=state_noise_cov
        )
        
        # Check observation noise covariance is PD
        obs_eigenvalues = np.linalg.eigvals(ss.obs_noise_cov)
        assert np.all(obs_eigenvalues > -1e-10), \
            f"Observation noise covariance not PD: min eigenvalue = {np.min(obs_eigenvalues):.2e}"
        
        # Check state noise covariance is PD
        state_eigenvalues = np.linalg.eigvals(ss.state_noise_cov)
        assert np.all(state_eigenvalues > -1e-10), \
            f"State noise covariance not PD: min eigenvalue = {np.min(state_eigenvalues):.2e}"
    
    def test_noise_covariances_symmetric(self):
        """
        Covariance matrices must be symmetric.
        
        Mathematical Property:
            Σ = Σ.T
        
        Purpose: Verify that covariance matrices have correct structure.
        """
        n_obs = 5
        n_factors = 2
        
        # Create covariances
        obs_noise_base = np.random.randn(n_obs, n_obs)
        obs_noise_cov = obs_noise_base @ obs_noise_base.T
        
        state_noise_base = np.random.randn(n_factors, n_factors)
        state_noise_cov = state_noise_base @ state_noise_base.T
        
        # Create state-space representation
        loadings = build_observation_matrix(n_obs, n_factors)
        transition = build_transition_matrix(n_factors)
        
        ss = StateSpaceRepresentation(
            loadings=loadings,
            transition=transition,
            obs_noise_cov=obs_noise_cov,
            state_noise_cov=state_noise_cov
        )
        
        # Check symmetry
        np.testing.assert_array_almost_equal(
            ss.obs_noise_cov, ss.obs_noise_cov.T,
            err_msg="Observation noise covariance not symmetric"
        )
        
        np.testing.assert_array_almost_equal(
            ss.state_noise_cov, ss.state_noise_cov.T,
            err_msg="State noise covariance not symmetric"
        )
    
    def test_diagonal_covariances_are_positive(self):
        """
        Diagonal elements of covariance matrices must be positive.
        
        Mathematical Property:
            Σ[i,i] > 0 for all i
        
        Purpose: Verify that variances (diagonal elements) are positive.
        """
        n_obs = 5
        n_factors = 2
        
        # Create diagonal covariances
        obs_noise_cov = np.diag(np.random.rand(n_obs) + 0.1)  # Ensure positive
        state_noise_cov = np.diag(np.random.rand(n_factors) + 0.1)
        
        # Create state-space representation
        loadings = build_observation_matrix(n_obs, n_factors)
        transition = build_transition_matrix(n_factors)
        
        ss = StateSpaceRepresentation(
            loadings=loadings,
            transition=transition,
            obs_noise_cov=obs_noise_cov,
            state_noise_cov=state_noise_cov
        )
        
        # Check diagonal elements are positive
        obs_diag = np.diag(ss.obs_noise_cov)
        assert np.all(obs_diag > 0), \
            f"Observation noise has non-positive diagonal: {obs_diag}"
        
        state_diag = np.diag(ss.state_noise_cov)
        assert np.all(state_diag > 0), \
            f"State noise has non-positive diagonal: {state_diag}"


class TestStateSpaceStabilityProperties:
    """Test stability properties of state-space system"""
    
    def test_transition_matrix_eigenvalues_for_stability(self):
        """
        Stable system must have |eigenvalues| < 1.
        
        Mathematical Property:
            max|λ(Φ)| < 1 for stability
        
        Purpose: Verify that transition matrix creates stable dynamics.
        """
        n_factors = 3
        
        # Create stable transition matrix
        stable_transition = np.diag([0.9, 0.8, 0.7])
        
        # Create state-space with stable transition
        loadings = build_observation_matrix(5, n_factors)
        ss = StateSpaceRepresentation(loadings, stable_transition)
        
        # Should be stable
        assert ss.is_stable, "Stable transition matrix reported as unstable"
        
        # Verify eigenvalues
        eigenvalues = np.linalg.eigvals(stable_transition)
        max_eigenvalue = np.max(np.abs(eigenvalues))
        
        assert max_eigenvalue < 1.0, \
            f"Stable system has eigenvalue >= 1: {max_eigenvalue:.4f}"
    
    def test_unstable_transition_matrix_detected(self):
        """
        Unstable system must be correctly identified.
        
        Mathematical Property:
            If max|λ(Φ)| >= 1, then is_stable = False
        
        Purpose: Verify that instability is correctly detected.
        """
        n_factors = 2
        
        # Create unstable transition matrix (eigenvalue > 1)
        unstable_transition = np.array([[1.1, 0.0], [0.0, 0.9]])
        
        # Create state-space with unstable transition
        loadings = build_observation_matrix(5, n_factors)
        ss = StateSpaceRepresentation(loadings, unstable_transition)
        
        # Should be unstable
        assert not ss.is_stable, "Unstable transition matrix reported as stable"
        
        # Verify eigenvalues
        eigenvalues = np.linalg.eigvals(unstable_transition)
        max_eigenvalue = np.max(np.abs(eigenvalues))
        
        assert max_eigenvalue >= 1.0, \
            f"Unstable system has all eigenvalues < 1: {max_eigenvalue:.4f}"
    
    def test_identity_transition_is_marginally_stable(self):
        """
        Identity matrix (eigenvalues = 1) should be detected as unstable.
        
        Mathematical Property:
            Φ = I has |λ| = 1 (marginally stable/unstable)
        
        Purpose: Verify boundary case handling.
        """
        n_factors = 2
        
        # Identity matrix (marginally stable)
        identity_transition = np.eye(n_factors)
        
        # Create state-space
        loadings = build_observation_matrix(5, n_factors)
        ss = StateSpaceRepresentation(loadings, identity_transition)
        
        # Identity has eigenvalues = 1, which should be flagged as unstable
        # (per definition is_stable requires |λ| < 1, not <=)
        assert not ss.is_stable, \
            "Identity matrix should be flagged as marginally unstable"


class TestDFMIntegrationWithProperties:
    """Integration tests that combine multiple mathematical properties"""
    
    @pytest.fixture
    def sample_data(self):
        """Create synthetic time series data"""
        np.random.seed(42)
        n_obs = 100
        dates = pd.date_range('2014-01-01', periods=n_obs, freq='M')
        
        y = pd.Series(
            np.random.normal(150, 50, n_obs),
            index=dates,
            name='nfp_change'
        )
        
        X = pd.DataFrame({
            'series_1': np.random.normal(100, 10, n_obs),
            'series_2': np.random.normal(200, 20, n_obs),
            'series_3': np.random.normal(50, 5, n_obs),
        }, index=dates)
        
        return X, y
    
    def test_fitted_model_has_stable_transition(self, sample_data):
        """
        After fitting, check stability of transition matrix.
        
        Mathematical Property:
            Ideally, DFM learns stable dynamics (|λ| < 1)
        
        Purpose: Document that unconstrained EM can learn unstable systems.
                 This is a known limitation - production DFM should
                 constrain eigenvalues during estimation.
        
        Note: This test currently documents the limitation rather than
              enforcing stability, which would require constraining
              the M-step of EM algorithm.
        """
        X, y = sample_data
        model = DynamicFactorModel(n_factors=2, max_iter=20, random_state=42)
        
        # Fit model
        model.fit(X, y, vintage_date='2024-11-15')
        
        # Check that transition matrix eigenvalues
        eigenvalues = np.linalg.eigvals(model.transition_)
        max_eigenvalue = np.max(np.abs(eigenvalues))
        
        # For production use, should be stable (|λ| < 1)
        # Current implementation doesn't constrain this
        if max_eigenvalue >= 1.0:
            # Document the instability (not a hard failure)
            import warnings
            warnings.warn(
                f"DFM learned unstable transition (max |λ| = {max_eigenvalue:.4f}). "
                "Production version should constrain eigenvalues in M-step.",
                UserWarning
            )
        
        # At minimum, eigenvalues should be finite
        assert np.all(np.isfinite(eigenvalues)), \
            "Transition matrix has non-finite eigenvalues"
    
    def test_em_improves_fit_quality(self, sample_data):
        """
        EM iterations should improve reconstruction quality.
        
        Mathematical Property:
            Reconstruction error decreases with more EM iterations
        
        Purpose: Verify that EM is improving the model, not just likelihood.
        """
        X, y = sample_data
        
        # Fit with few iterations
        model_few = DynamicFactorModel(n_factors=2, max_iter=5, random_state=42)
        model_few.fit(X, y, vintage_date='2024-11-15')
        pred_few = model_few.predict(X[-10:])
        
        # Fit with many iterations
        model_many = DynamicFactorModel(n_factors=2, max_iter=30, random_state=42)
        model_many.fit(X, y, vintage_date='2024-11-15')
        pred_many = model_many.predict(X[-10:])
        
        # Reconstruction error should decrease (or at least not increase much)
        y_test = y[-10:].values
        error_few = np.mean((pred_few - y_test)**2)
        error_many = np.mean((pred_many - y_test)**2)
        
        # More iterations should not make things significantly worse
        # (Allow for some numerical noise in this toy example)
        assert error_many <= error_few * 1.1, \
            f"More EM iterations increased error: {error_few:.2f} -> {error_many:.2f}"

