"""
Tests for DFM State-Space Utilities

Tests cover:
- State-space representation construction
- Transition matrix building
- Observation matrix building
- Matrix dimension validation
- State-space consistency checks
"""

import pytest
import numpy as np

from models_src.dfm.state_space import (
    StateSpaceRepresentation,
    build_transition_matrix,
    build_observation_matrix,
    validate_state_space_dimensions,
)


class TestStateSpaceRepresentation:
    """Test state-space representation class"""

    def test_initialization_with_valid_matrices(self):
        """Test initialization with valid matrices"""
        n_obs = 3  # Number of observed variables
        n_factors = 2  # Number of latent factors

        # Observation equation: X_t = Λ * F_t + e_t
        loadings = np.random.randn(n_obs, n_factors)

        # State equation: F_t = Φ * F_{t-1} + η_t
        transition = np.random.randn(n_factors, n_factors)

        state_space = StateSpaceRepresentation(loadings=loadings, transition=transition)

        assert state_space.n_obs == n_obs
        assert state_space.n_factors == n_factors
        assert np.array_equal(state_space.loadings, loadings)
        assert np.array_equal(state_space.transition, transition)

    def test_initialization_validates_dimensions(self):
        """Test that initialization validates matrix dimensions"""
        # Incompatible dimensions
        loadings = np.random.randn(3, 2)  # 3 obs, 2 factors
        transition = np.random.randn(3, 3)  # Wrong: should be 2x2

        with pytest.raises(ValueError, match="Incompatible dimensions"):
            StateSpaceRepresentation(loadings=loadings, transition=transition)

    def test_initialization_with_noise_covariances(self):
        """Test initialization with observation and state noise covariances"""
        n_obs = 3
        n_factors = 2

        loadings = np.random.randn(n_obs, n_factors)
        transition = np.random.randn(n_factors, n_factors)

        # Noise covariance matrices
        obs_noise_cov = np.eye(n_obs) * 0.1
        state_noise_cov = np.eye(n_factors) * 0.05

        state_space = StateSpaceRepresentation(
            loadings=loadings,
            transition=transition,
            obs_noise_cov=obs_noise_cov,
            state_noise_cov=state_noise_cov,
        )

        assert state_space.obs_noise_cov is not None
        assert state_space.state_noise_cov is not None
        assert state_space.obs_noise_cov.shape == (n_obs, n_obs)
        assert state_space.state_noise_cov.shape == (n_factors, n_factors)

    def test_is_stable_property(self):
        """Test is_stable property checks transition matrix eigenvalues"""
        n_factors = 2

        # Stable transition matrix (eigenvalues < 1)
        stable_transition = np.array([[0.8, 0.1], [0.0, 0.7]])
        loadings = np.random.randn(3, n_factors)

        stable_ss = StateSpaceRepresentation(loadings, stable_transition)
        assert stable_ss.is_stable is True

        # Unstable transition matrix (eigenvalues > 1)
        unstable_transition = np.array([[1.5, 0.1], [0.0, 1.2]])
        unstable_ss = StateSpaceRepresentation(loadings, unstable_transition)
        assert unstable_ss.is_stable is False

    def test_get_params(self):
        """Test get_params returns complete state-space parameters"""
        n_obs = 3
        n_factors = 2

        loadings = np.random.randn(n_obs, n_factors)
        transition = np.random.randn(n_factors, n_factors)

        state_space = StateSpaceRepresentation(loadings, transition)
        params = state_space.get_params()

        assert "n_obs" in params
        assert "n_factors" in params
        assert "is_stable" in params
        assert params["n_obs"] == n_obs
        assert params["n_factors"] == n_factors


class TestBuildTransitionMatrix:
    """Test transition matrix construction"""

    def test_build_ar1_transition_matrix(self):
        """Test building AR(1) transition matrix"""
        n_factors = 3
        ar_coef = 0.9

        transition = build_transition_matrix(n_factors=n_factors, ar_order=1, ar_coef=ar_coef)

        # Should be diagonal with AR coefficient
        assert transition.shape == (n_factors, n_factors)
        assert np.allclose(np.diag(transition), ar_coef)
        # Off-diagonals should be zero for AR(1)
        assert np.allclose(transition - np.diag(np.diag(transition)), 0)

    def test_build_var1_transition_matrix(self):
        """Test building VAR(1) transition matrix with cross-factor dynamics"""
        n_factors = 2

        # Provide full transition matrix
        full_transition = np.array([[0.8, 0.2], [0.1, 0.7]])

        transition = build_transition_matrix(
            n_factors=n_factors, ar_order=1, transition_matrix=full_transition
        )

        assert transition.shape == (n_factors, n_factors)
        assert np.allclose(transition, full_transition)

    def test_build_identity_transition(self):
        """Test building identity transition (random walk)"""
        n_factors = 3

        transition = build_transition_matrix(n_factors=n_factors, ar_order=1, ar_coef=1.0)

        assert np.allclose(transition, np.eye(n_factors))

    def test_validates_ar_coefficient(self):
        """Test that AR coefficient is validated for stability"""
        n_factors = 2

        # AR coefficient > 1 should warn but not fail
        transition = build_transition_matrix(n_factors=n_factors, ar_order=1, ar_coef=1.5)

        # Should still return a matrix
        assert transition.shape == (n_factors, n_factors)

    def test_validates_transition_matrix_dimensions(self):
        """Test that provided transition matrix dimensions are validated"""
        n_factors = 2

        # Wrong dimensions
        wrong_transition = np.random.randn(3, 3)

        with pytest.raises(ValueError, match="Transition matrix must be"):
            build_transition_matrix(
                n_factors=n_factors, ar_order=1, transition_matrix=wrong_transition
            )


class TestBuildObservationMatrix:
    """Test observation matrix (loadings) construction"""

    def test_build_random_observation_matrix(self):
        """Test building observation matrix with random initialization"""
        n_obs = 5
        n_factors = 2
        seed = 42

        loadings = build_observation_matrix(n_obs=n_obs, n_factors=n_factors, random_state=seed)

        assert loadings.shape == (n_obs, n_factors)

        # Should be reproducible with same seed
        loadings2 = build_observation_matrix(n_obs=n_obs, n_factors=n_factors, random_state=seed)
        assert np.allclose(loadings, loadings2)

    def test_build_observation_matrix_with_structure(self):
        """Test building observation matrix with block structure"""
        n_obs = 6
        n_factors = 2

        # Block structure: first 3 obs load on factor 1, next 3 on factor 2
        loadings = build_observation_matrix(
            n_obs=n_obs, n_factors=n_factors, structure="block", random_state=42
        )

        assert loadings.shape == (n_obs, n_factors)

        # Check that loadings are structured (not all equal)
        # Variance across observations should be significant
        assert np.var(loadings[:, 0]) > 0.01
        assert np.var(loadings[:, 1]) > 0.01

    def test_build_observation_matrix_normalized(self):
        """Test building normalized observation matrix"""
        n_obs = 4
        n_factors = 2

        loadings = build_observation_matrix(
            n_obs=n_obs, n_factors=n_factors, normalize=True, random_state=42
        )

        assert loadings.shape == (n_obs, n_factors)

        # Each column should have unit norm
        column_norms = np.linalg.norm(loadings, axis=0)
        assert np.allclose(column_norms, 1.0)

    def test_build_observation_matrix_from_pca(self):
        """Test building observation matrix from PCA on data"""
        # Generate synthetic data
        np.random.seed(42)
        n_samples = 100
        n_obs = 5
        n_factors = 2

        # True factors
        factors = np.random.randn(n_samples, n_factors)
        # True loadings
        true_loadings = np.random.randn(n_obs, n_factors)
        # Observed data
        X = factors @ true_loadings.T + np.random.randn(n_samples, n_obs) * 0.1

        # Build loadings from PCA
        loadings = build_observation_matrix(n_obs=n_obs, n_factors=n_factors, data=X, method="pca")

        assert loadings.shape == (n_obs, n_factors)

        # Check that PCA loadings are reasonable
        # They should have similar scale to the data
        assert np.abs(loadings).max() > 0  # Not all zeros
        assert np.abs(loadings).max() < 100  # Not huge values

    def test_validates_dimensions(self):
        """Test dimension validation"""
        with pytest.raises(ValueError, match="n_obs must be positive"):
            build_observation_matrix(n_obs=0, n_factors=2)

        with pytest.raises(ValueError, match="n_factors must be positive"):
            build_observation_matrix(n_obs=5, n_factors=0)

        with pytest.raises(ValueError, match="n_factors .* cannot exceed n_obs"):
            build_observation_matrix(n_obs=2, n_factors=5)


class TestValidateStateSpaceDimensions:
    """Test state-space dimension validation"""

    def test_valid_dimensions(self):
        """Test validation passes with valid dimensions"""
        n_obs = 5
        n_factors = 2

        loadings = np.random.randn(n_obs, n_factors)
        transition = np.random.randn(n_factors, n_factors)

        # Should not raise
        validate_state_space_dimensions(loadings=loadings, transition=transition)

    def test_validates_loadings_shape(self):
        """Test validation of loadings matrix shape"""
        loadings = np.random.randn(5, 2, 3)  # Wrong: 3D array
        transition = np.random.randn(2, 2)

        with pytest.raises(ValueError, match="Loadings must be 2D"):
            validate_state_space_dimensions(loadings, transition)

    def test_validates_transition_shape(self):
        """Test validation of transition matrix shape"""
        loadings = np.random.randn(5, 2)
        transition = np.random.randn(2)  # Wrong: 1D array

        with pytest.raises(ValueError, match="Transition must be 2D"):
            validate_state_space_dimensions(loadings, transition)

    def test_validates_transition_square(self):
        """Test that transition matrix must be square"""
        loadings = np.random.randn(5, 2)
        transition = np.random.randn(2, 3)  # Wrong: not square

        with pytest.raises(ValueError, match="Transition must be square"):
            validate_state_space_dimensions(loadings, transition)

    def test_validates_dimension_compatibility(self):
        """Test that loadings and transition dimensions are compatible"""
        loadings = np.random.randn(5, 2)  # 2 factors
        transition = np.random.randn(3, 3)  # Wrong: 3 factors

        with pytest.raises(ValueError, match="Incompatible dimensions"):
            validate_state_space_dimensions(loadings, transition)

    def test_validates_with_noise_covariances(self):
        """Test validation with noise covariance matrices"""
        n_obs = 5
        n_factors = 2

        loadings = np.random.randn(n_obs, n_factors)
        transition = np.random.randn(n_factors, n_factors)
        obs_noise_cov = np.eye(n_obs)
        state_noise_cov = np.eye(n_factors)

        # Should not raise
        validate_state_space_dimensions(
            loadings=loadings,
            transition=transition,
            obs_noise_cov=obs_noise_cov,
            state_noise_cov=state_noise_cov,
        )

    def test_validates_obs_noise_cov_dimensions(self):
        """Test validation of observation noise covariance dimensions"""
        n_obs = 5
        n_factors = 2

        loadings = np.random.randn(n_obs, n_factors)
        transition = np.random.randn(n_factors, n_factors)
        obs_noise_cov = np.eye(3)  # Wrong: should be 5x5

        with pytest.raises(ValueError, match="Observation noise covariance"):
            validate_state_space_dimensions(loadings, transition, obs_noise_cov=obs_noise_cov)

    def test_validates_state_noise_cov_dimensions(self):
        """Test validation of state noise covariance dimensions"""
        n_obs = 5
        n_factors = 2

        loadings = np.random.randn(n_obs, n_factors)
        transition = np.random.randn(n_factors, n_factors)
        state_noise_cov = np.eye(3)  # Wrong: should be 2x2

        with pytest.raises(ValueError, match="State noise covariance"):
            validate_state_space_dimensions(loadings, transition, state_noise_cov=state_noise_cov)


class TestStateSpaceConsistency:
    """Test state-space consistency checks"""

    def test_consistent_state_space_model(self):
        """Test that a properly constructed state-space model is consistent"""
        np.random.seed(42)
        n_obs = 5
        n_factors = 2
        n_samples = 100

        # Build state-space model
        loadings = build_observation_matrix(n_obs, n_factors, random_state=42)
        transition = build_transition_matrix(n_factors, ar_order=1, ar_coef=0.9)

        StateSpaceRepresentation(loadings, transition)

        # Generate synthetic data
        factors = np.random.randn(n_samples, n_factors)
        for t in range(1, n_samples):
            factors[t] = transition @ factors[t - 1] + np.random.randn(n_factors) * 0.1

        observations = factors @ loadings.T + np.random.randn(n_samples, n_obs) * 0.1

        # Check consistency
        assert observations.shape == (n_samples, n_obs)
        assert not np.any(np.isnan(observations))
        assert not np.any(np.isinf(observations))

    def test_stable_system_properties(self):
        """Test properties of stable state-space systems"""
        n_factors = 2

        # Build stable system
        stable_transition = np.array([[0.8, 0.1], [0.0, 0.7]])
        loadings = np.random.randn(3, n_factors)

        state_space = StateSpaceRepresentation(loadings, stable_transition)

        # Check eigenvalues
        eigenvalues = np.linalg.eigvals(state_space.transition)
        assert np.all(np.abs(eigenvalues) < 1), "Stable system should have eigenvalues < 1"
        assert state_space.is_stable is True

    def test_unstable_system_detection(self):
        """Test detection of unstable state-space systems"""
        n_factors = 2

        # Build unstable system
        unstable_transition = np.array([[1.2, 0.0], [0.0, 1.1]])
        loadings = np.random.randn(3, n_factors)

        state_space = StateSpaceRepresentation(loadings, unstable_transition)

        # Check eigenvalues
        eigenvalues = np.linalg.eigvals(state_space.transition)
        assert np.any(np.abs(eigenvalues) >= 1), "Unstable system should have eigenvalues >= 1"
        assert state_space.is_stable is False
