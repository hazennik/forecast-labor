"""
State-Space Representation Utilities for Dynamic Factor Models

Provides helper functions and classes for constructing and validating
state-space representations of DFM models:

State-Space Form:
    Observation equation: X_t = Λ * F_t + e_t
    State equation:       F_t = Φ * F_{t-1} + η_t

Where:
    X_t: Observed variables (N x 1)
    F_t: Latent factors (K x 1)
    Λ: Factor loadings / observation matrix (N x K)
    Φ: Transition matrix (K x K)
    e_t: Observation noise (N x 1)
    η_t: State noise (K x 1)

Key Features:
- State-space representation construction
- Transition matrix builders (AR, VAR)
- Observation matrix builders (random, PCA, structured)
- Dimension validation
- Stability checks (eigenvalue analysis)
"""

from typing import Optional, Literal, Union
from dataclasses import dataclass

import numpy as np
from loguru import logger


class StateSpaceRepresentation:
    """
    State-space representation of a dynamic factor model.
    
    Encapsulates the observation equation (X = Λ*F + e) and
    state equation (F = Φ*F_{t-1} + η).
    
    Attributes:
        loadings: Factor loadings matrix Λ (n_obs x n_factors)
        transition: Transition matrix Φ (n_factors x n_factors)
        obs_noise_cov: Observation noise covariance (n_obs x n_obs)
        state_noise_cov: State noise covariance (n_factors x n_factors)
        n_obs: Number of observed variables
        n_factors: Number of latent factors
        is_stable: Whether the system is stable (all eigenvalues < 1)
    
    Example:
        ```python
        # Create state-space representation
        loadings = np.random.randn(5, 2)
        transition = np.array([[0.9, 0.1], [0.0, 0.8]])
        
        ss = StateSpaceRepresentation(loadings, transition)
        
        if ss.is_stable:
            print("System is stable")
        ```
    """
    
    def __init__(
        self,
        loadings: np.ndarray,
        transition: np.ndarray,
        obs_noise_cov: Optional[np.ndarray] = None,
        state_noise_cov: Optional[np.ndarray] = None
    ):
        """
        Initialize state-space representation.
        
        Args:
            loadings: Observation matrix (n_obs x n_factors)
            transition: Transition matrix (n_factors x n_factors)
            obs_noise_cov: Observation noise covariance (n_obs x n_obs), optional
            state_noise_cov: State noise covariance (n_factors x n_factors), optional
            
        Raises:
            ValueError: If dimensions are incompatible
        """
        # Validate dimensions
        validate_state_space_dimensions(
            loadings=loadings,
            transition=transition,
            obs_noise_cov=obs_noise_cov,
            state_noise_cov=state_noise_cov
        )
        
        self.loadings = loadings
        self.transition = transition
        self.obs_noise_cov = obs_noise_cov
        self.state_noise_cov = state_noise_cov
        
        self.n_obs, self.n_factors = loadings.shape
        
        logger.debug(
            "Initialized StateSpaceRepresentation",
            extra={
                'n_obs': self.n_obs,
                'n_factors': self.n_factors,
                'is_stable': self.is_stable
            }
        )
    
    @property
    def is_stable(self) -> bool:
        """
        Check if the state-space system is stable.
        
        A system is stable if all eigenvalues of the transition matrix
        have absolute value less than 1.
        
        Returns:
            is_stable: True if system is stable, False otherwise
        """
        eigenvalues = np.linalg.eigvals(self.transition)
        return bool(np.all(np.abs(eigenvalues) < 1))
    
    def get_params(self) -> dict:
        """
        Get state-space parameters.
        
        Returns:
            params: Dictionary with system parameters
        """
        return {
            'n_obs': self.n_obs,
            'n_factors': self.n_factors,
            'is_stable': self.is_stable,
            'has_obs_noise': self.obs_noise_cov is not None,
            'has_state_noise': self.state_noise_cov is not None,
        }


def build_transition_matrix(
    n_factors: int,
    ar_order: int = 1,
    ar_coef: Optional[float] = None,
    transition_matrix: Optional[np.ndarray] = None
) -> np.ndarray:
    """
    Build transition matrix for factor dynamics.
    
    Supports:
    - AR(1) process: Diagonal matrix with AR coefficient
    - VAR(1) process: Full transition matrix with cross-factor dynamics
    - Custom: User-provided transition matrix
    
    Args:
        n_factors: Number of latent factors
        ar_order: Autoregressive order (currently only AR(1) supported)
        ar_coef: AR coefficient for diagonal AR(1) model (e.g., 0.9)
        transition_matrix: Custom transition matrix (n_factors x n_factors)
            If provided, overrides ar_coef
            
    Returns:
        transition: Transition matrix (n_factors x n_factors)
        
    Raises:
        ValueError: If dimensions are invalid or parameters inconsistent
        
    Example:
        ```python
        # Build AR(1) transition matrix
        Φ = build_transition_matrix(n_factors=3, ar_coef=0.9)
        # Φ = diag([0.9, 0.9, 0.9])
        
        # Build custom VAR(1) transition matrix
        custom_Φ = np.array([[0.8, 0.2], [0.1, 0.7]])
        Φ = build_transition_matrix(n_factors=2, transition_matrix=custom_Φ)
        ```
    """
    if ar_order != 1:
        raise NotImplementedError(
            f"Only AR(1) currently supported, got ar_order={ar_order}"
        )
    
    # If custom transition matrix provided, use it
    if transition_matrix is not None:
        if transition_matrix.shape != (n_factors, n_factors):
            raise ValueError(
                f"Transition matrix must be ({n_factors}, {n_factors}), "
                f"got {transition_matrix.shape}"
            )
        
        # Warn if system is unstable
        eigenvalues = np.linalg.eigvals(transition_matrix)
        if np.any(np.abs(eigenvalues) >= 1):
            logger.warning(
                "Transition matrix has eigenvalues >= 1 (unstable system)",
                extra={'max_eigenvalue': float(np.max(np.abs(eigenvalues)))}
            )
        
        return transition_matrix
    
    # Build AR(1) transition matrix
    if ar_coef is None:
        ar_coef = 0.9  # Default stable AR coefficient
    
    # Diagonal matrix with AR coefficient
    transition = np.eye(n_factors) * ar_coef
    
    # Warn if AR coefficient suggests instability
    if abs(ar_coef) >= 1:
        logger.warning(
            f"AR coefficient {ar_coef} >= 1 (unstable system). "
            "Consider using |ar_coef| < 1 for stability."
        )
    
    logger.debug(
        "Built transition matrix",
        extra={
            'n_factors': n_factors,
            'ar_coef': ar_coef,
            'is_diagonal': True
        }
    )
    
    return transition


def build_observation_matrix(
    n_obs: int,
    n_factors: int,
    method: Literal['random', 'pca', 'block'] = 'random',
    structure: Optional[str] = None,
    normalize: bool = False,
    random_state: int = 42,
    data: Optional[np.ndarray] = None
) -> np.ndarray:
    """
    Build observation matrix (factor loadings).
    
    Methods:
    - 'random': Random initialization (default)
    - 'pca': Principal components from data
    - 'block': Block structure (groups of obs load on different factors)
    
    Args:
        n_obs: Number of observed variables
        n_factors: Number of latent factors
        method: Construction method
        structure: Structure type (for block method)
        normalize: Whether to normalize columns to unit norm
        random_state: Random seed for reproducibility
        data: Data for PCA initialization (n_samples x n_obs)
        
    Returns:
        loadings: Observation matrix (n_obs x n_factors)
        
    Raises:
        ValueError: If dimensions are invalid or data is incompatible
        
    Example:
        ```python
        # Random loadings
        Λ = build_observation_matrix(n_obs=5, n_factors=2)
        
        # PCA loadings from data
        X = np.random.randn(100, 5)
        Λ = build_observation_matrix(n_obs=5, n_factors=2, method='pca', data=X)
        
        # Block structure
        Λ = build_observation_matrix(n_obs=6, n_factors=2, structure='block')
        ```
    """
    # Validate dimensions
    if n_obs <= 0:
        raise ValueError(f"n_obs must be positive, got {n_obs}")
    
    if n_factors <= 0:
        raise ValueError(f"n_factors must be positive, got {n_factors}")
    
    if n_factors > n_obs:
        raise ValueError(
            f"n_factors ({n_factors}) cannot exceed n_obs ({n_obs})"
        )
    
    # Set random seed
    np.random.seed(random_state)
    
    if method == 'random':
        # Random initialization (small values)
        loadings = np.random.randn(n_obs, n_factors) * 0.5
        
    elif method == 'pca':
        # PCA initialization from data
        if data is None:
            raise ValueError("Data required for PCA initialization")
        
        if data.shape[1] != n_obs:
            raise ValueError(
                f"Data has {data.shape[1]} columns, expected {n_obs}"
            )
        
        # Standardize data
        data_centered = data - data.mean(axis=0)
        
        # Compute covariance matrix
        cov = data_centered.T @ data_centered / len(data)
        
        # Eigen decomposition
        eigenvalues, eigenvectors = np.linalg.eigh(cov)
        
        # Sort by eigenvalue (descending)
        idx = np.argsort(eigenvalues)[::-1]
        eigenvectors = eigenvectors[:, idx]
        
        # Take top n_factors eigenvectors as loadings
        loadings = eigenvectors[:, :n_factors]
        
        # Scale by sqrt(eigenvalue) for proper PCA loadings
        loadings = loadings * np.sqrt(eigenvalues[idx[:n_factors]])
        
    elif method == 'block' or structure == 'block':
        # Block structure: groups of observations load on different factors
        loadings = np.random.randn(n_obs, n_factors) * 0.1
        
        # Assign stronger loadings in blocks
        obs_per_factor = n_obs // n_factors
        for k in range(n_factors):
            start_idx = k * obs_per_factor
            end_idx = start_idx + obs_per_factor if k < n_factors - 1 else n_obs
            loadings[start_idx:end_idx, k] += np.random.randn(end_idx - start_idx) * 0.8
    
    else:
        raise ValueError(f"Unknown method: {method}")
    
    # Normalize columns if requested
    if normalize:
        column_norms = np.linalg.norm(loadings, axis=0)
        loadings = loadings / column_norms
    
    logger.debug(
        "Built observation matrix",
        extra={
            'n_obs': n_obs,
            'n_factors': n_factors,
            'method': method,
            'normalized': normalize
        }
    )
    
    return loadings


def validate_state_space_dimensions(
    loadings: np.ndarray,
    transition: np.ndarray,
    obs_noise_cov: Optional[np.ndarray] = None,
    state_noise_cov: Optional[np.ndarray] = None
) -> None:
    """
    Validate dimensions of state-space matrices.
    
    Checks:
    - Loadings is 2D (n_obs x n_factors)
    - Transition is 2D and square (n_factors x n_factors)
    - Dimensions are compatible
    - Noise covariances have correct dimensions (if provided)
    
    Args:
        loadings: Observation matrix (n_obs x n_factors)
        transition: Transition matrix (n_factors x n_factors)
        obs_noise_cov: Observation noise covariance (n_obs x n_obs), optional
        state_noise_cov: State noise covariance (n_factors x n_factors), optional
        
    Raises:
        ValueError: If any dimension checks fail
        
    Example:
        ```python
        loadings = np.random.randn(5, 2)
        transition = np.random.randn(2, 2)
        
        # Will pass
        validate_state_space_dimensions(loadings, transition)
        
        # Will fail
        bad_transition = np.random.randn(3, 3)
        validate_state_space_dimensions(loadings, bad_transition)
        # ValueError: Incompatible dimensions
        ```
    """
    # Check loadings
    if loadings.ndim != 2:
        raise ValueError(
            f"Loadings must be 2D array, got shape {loadings.shape}"
        )
    
    n_obs, n_factors = loadings.shape
    
    # Check transition
    if transition.ndim != 2:
        raise ValueError(
            f"Transition must be 2D array, got shape {transition.shape}"
        )
    
    if transition.shape[0] != transition.shape[1]:
        raise ValueError(
            f"Transition must be square matrix, got shape {transition.shape}"
        )
    
    # Check dimension compatibility
    if transition.shape[0] != n_factors:
        raise ValueError(
            f"Incompatible dimensions: loadings has {n_factors} factors, "
            f"but transition is {transition.shape[0]}x{transition.shape[1]}"
        )
    
    # Check observation noise covariance
    if obs_noise_cov is not None:
        if obs_noise_cov.shape != (n_obs, n_obs):
            raise ValueError(
                f"Observation noise covariance must be ({n_obs}, {n_obs}), "
                f"got {obs_noise_cov.shape}"
            )
    
    # Check state noise covariance
    if state_noise_cov is not None:
        if state_noise_cov.shape != (n_factors, n_factors):
            raise ValueError(
                f"State noise covariance must be ({n_factors}, {n_factors}), "
                f"got {state_noise_cov.shape}"
            )
    
    logger.debug(
        "State-space dimensions validated",
        extra={
            'n_obs': n_obs,
            'n_factors': n_factors,
            'has_obs_noise': obs_noise_cov is not None,
            'has_state_noise': state_noise_cov is not None
        }
    )

