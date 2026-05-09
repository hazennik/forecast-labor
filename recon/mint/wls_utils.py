"""
WLS (Weighted Least Squares) Utilities for Hierarchical Forecast Reconciliation

Provides standalone utilities for computing variance weights, covariance matrices,
and weight matrices used in hierarchical forecast reconciliation methods (OLS, WLS, MinT).

Key Functions:
- compute_variance_weights: Diagonal variance weight matrix
- compute_diagonal_weights: Construct diagonal matrix from variances
- compute_sample_covariance: Sample covariance matrix estimation
- compute_shrinkage_covariance: Ledoit-Wolf shrinkage covariance
- ensure_positive_definite: Regularize matrices to be positive definite
- validate_weight_matrix: Validate weight matrix properties
- compute_wls_weights: Unified interface for all WLS weight methods
- compute_precision_matrix: Inverse covariance (precision) matrix

These utilities can be used independently or integrated into reconciliation classes.

References:
- Wickramasuriya et al. (2019): Optimal forecast reconciliation through trace minimization
- Ledoit & Wolf (2004): A well-conditioned estimator for large-dimensional covariance matrices
- Athanasopoulos et al. (2017): Forecast reconciliation: A review
"""

from typing import Optional, Tuple, Literal
import numpy as np
import pandas as pd
from loguru import logger
from sklearn.covariance import LedoitWolf


def compute_variance_weights(data: pd.DataFrame, min_variance: float = 1e-8) -> np.ndarray:
    """
    Compute diagonal variance weight matrix from data.

    Creates a diagonal matrix where diagonal elements are the sample variances
    of each series. Used for WLS (Weighted Least Squares) reconciliation.

    Args:
        data: Historical data or forecast errors (n_obs x n_series)
        min_variance: Minimum variance threshold (prevents division by zero)

    Returns:
        Diagonal variance weight matrix (n_series x n_series)

    Raises:
        ValueError: If data is empty or has insufficient observations

    Example:
        ```python
        errors = pd.DataFrame({
            'national': [10, -5, 3],
            'state1': [4, -2, 1],
            'state2': [6, -3, 2]
        })
        weights = compute_variance_weights(errors)
        # Returns diagonal matrix with variances on diagonal
        ```
    """
    if data.empty:
        raise ValueError("Data cannot be empty")

    if len(data) < 2:
        raise ValueError(
            f"At least 2 observations required for variance estimation, got {len(data)}"
        )

    # Compute sample variances
    variances = data.var().values

    # Apply minimum variance threshold
    variances = np.maximum(variances, min_variance)

    # Construct diagonal matrix
    weight_matrix = np.diag(variances)

    logger.debug(
        "Computed variance weights",
        n_series=len(data.columns),
        n_observations=len(data),
        mean_variance=float(variances.mean()),
        min_variance_used=float(variances.min()),
    )

    return weight_matrix


def compute_diagonal_weights(
    variances: np.ndarray, min_variance: float = 1e-8, allow_negative: bool = False
) -> np.ndarray:
    """
    Construct diagonal weight matrix from variance array.

    Args:
        variances: Array of variances (n_series,)
        min_variance: Minimum variance threshold for regularization
        allow_negative: If False, raises error on negative variances

    Returns:
        Diagonal weight matrix (n_series x n_series)

    Raises:
        ValueError: If variances are negative and allow_negative=False

    Example:
        ```python
        variances = np.array([1.0, 4.0, 9.0])
        weights = compute_diagonal_weights(variances)
        # Returns 3x3 diagonal matrix
        ```
    """
    if not allow_negative and np.any(variances < 0):
        raise ValueError(
            "Variances must be non-negative. " "Set allow_negative=True to allow negative values."
        )

    # Regularize small/negative variances
    regularized_variances = np.maximum(variances, min_variance)

    # Construct diagonal matrix
    weight_matrix = np.diag(regularized_variances)

    n_regularized = np.sum(variances < min_variance)
    if n_regularized > 0:
        logger.warning(
            f"Regularized {n_regularized}/{len(variances)} variances "
            f"(below threshold {min_variance})"
        )

    return weight_matrix


def compute_sample_covariance(
    data: pd.DataFrame, ensure_pd: bool = True, min_eigenvalue: float = 1e-6
) -> np.ndarray:
    """
    Compute sample covariance matrix from data.

    Args:
        data: Historical data or forecast errors (n_obs x n_series)
        ensure_pd: If True, regularize to ensure positive definite
        min_eigenvalue: Minimum eigenvalue for PD regularization

    Returns:
        Sample covariance matrix (n_series x n_series)

    Raises:
        ValueError: If data is empty or has insufficient observations

    Example:
        ```python
        errors = pd.DataFrame(np.random.randn(100, 4))
        cov_matrix = compute_sample_covariance(errors)
        ```
    """
    if data.empty:
        raise ValueError("Data cannot be empty")

    # Compute sample covariance
    cov_matrix = data.cov().values

    # Ensure positive definite if requested
    if ensure_pd:
        cov_matrix = ensure_positive_definite(cov_matrix, min_eigenvalue=min_eigenvalue)

    logger.debug(
        "Computed sample covariance",
        n_series=len(data.columns),
        n_observations=len(data),
        condition_number=float(np.linalg.cond(cov_matrix)),
    )

    return cov_matrix


def compute_shrinkage_covariance(data: pd.DataFrame, min_eigenvalue: float = 1e-6) -> np.ndarray:
    """
    Compute shrinkage covariance matrix using Ledoit-Wolf estimator.

    The Ledoit-Wolf estimator shrinks the sample covariance towards a structured
    estimator (typically diagonal or constant correlation), which is beneficial
    when:
    - Number of observations is small relative to number of series
    - Sample covariance is poorly conditioned
    - Regularization is needed for stability

    Args:
        data: Historical data or forecast errors (n_obs x n_series)
        min_eigenvalue: Minimum eigenvalue for additional regularization

    Returns:
        Shrinkage covariance matrix (n_series x n_series)

    Raises:
        ValueError: If data is empty or has insufficient observations

    Example:
        ```python
        # Small sample, high dimension
        errors = pd.DataFrame(np.random.randn(20, 10))
        cov_matrix = compute_shrinkage_covariance(errors)
        # Returns well-conditioned covariance matrix
        ```
    """
    if data.empty:
        raise ValueError("Data cannot be empty")

    if len(data) < 2:
        raise ValueError(f"At least 2 observations required, got {len(data)}")

    # Ledoit-Wolf shrinkage estimator
    lw = LedoitWolf()
    cov_matrix = lw.fit(data.values).covariance_

    # Additional regularization if needed
    cov_matrix = ensure_positive_definite(cov_matrix, min_eigenvalue=min_eigenvalue)

    logger.debug(
        "Computed shrinkage covariance",
        n_series=len(data.columns),
        n_observations=len(data),
        shrinkage=float(lw.shrinkage_) if hasattr(lw, "shrinkage_") else None,
        condition_number=float(np.linalg.cond(cov_matrix)),
    )

    return cov_matrix


def ensure_positive_definite(matrix: np.ndarray, min_eigenvalue: float = 1e-6) -> np.ndarray:
    """
    Ensure matrix is positive definite by regularizing eigenvalues.

    Performs eigenvalue decomposition and sets all eigenvalues to be at least
    min_eigenvalue, then reconstructs the matrix. This ensures the matrix is
    positive definite and invertible.

    Args:
        matrix: Input matrix (typically covariance matrix)
        min_eigenvalue: Minimum eigenvalue threshold

    Returns:
        Positive definite matrix with same dimensions

    Example:
        ```python
        # Matrix with negative eigenvalues
        matrix = np.array([[1, 0], [0, -1]])
        pd_matrix = ensure_positive_definite(matrix)
        # All eigenvalues now positive
        ```
    """
    # Eigenvalue decomposition
    eigenvalues, eigenvectors = np.linalg.eigh(matrix)

    # Count how many eigenvalues need regularization
    n_regularized = np.sum(eigenvalues < min_eigenvalue)

    # Regularize small/negative eigenvalues
    eigenvalues_regularized = np.maximum(eigenvalues, min_eigenvalue)

    # Reconstruct matrix
    regularized = eigenvectors @ np.diag(eigenvalues_regularized) @ eigenvectors.T

    # Ensure symmetry (numerical stability)
    regularized = (regularized + regularized.T) / 2

    if n_regularized > 0:
        logger.debug(
            "Regularized matrix to be positive definite",
            n_eigenvalues_regularized=n_regularized,
            min_eigenvalue_before=float(eigenvalues.min()),
            min_eigenvalue_after=float(eigenvalues_regularized.min()),
        )

    return regularized


def validate_weight_matrix(
    matrix: np.ndarray,
    matrix_type: Literal["diagonal", "full", "auto"] = "auto",
    tolerance: float = 1e-6,
) -> Tuple[bool, str]:
    """
    Validate properties of a weight matrix.

    Checks:
    - Matrix is square
    - Matrix is symmetric (for full matrices)
    - Diagonal elements are positive
    - Matrix is positive definite (for full matrices)

    Args:
        matrix: Weight matrix to validate
        matrix_type: Type of matrix ('diagonal', 'full', or 'auto' to detect)
        tolerance: Numerical tolerance for checks

    Returns:
        Tuple of (is_valid, message)
        - is_valid: True if all checks pass
        - message: Description of validation result or error

    Example:
        ```python
        weights = np.diag([1, 2, 3])
        is_valid, msg = validate_weight_matrix(weights, 'diagonal')
        print(f"Valid: {is_valid}, Message: {msg}")
        ```
    """
    # Check if square
    if matrix.ndim != 2 or matrix.shape[0] != matrix.shape[1]:
        return False, f"Matrix is not square: shape {matrix.shape}"

    matrix.shape[0]

    # Auto-detect matrix type
    if matrix_type == "auto":
        is_diagonal = np.allclose(matrix - np.diag(np.diag(matrix)), 0, atol=tolerance)
        matrix_type = "diagonal" if is_diagonal else "full"

    # Check diagonal elements are positive
    diagonal = np.diag(matrix)
    if np.any(diagonal <= 0):
        negative_indices = np.where(diagonal <= 0)[0]
        return False, f"Negative or zero diagonal elements at indices {negative_indices.tolist()}"

    if matrix_type == "diagonal":
        # For diagonal matrices, just check diagonal is positive (already done)
        return True, "Valid diagonal weight matrix"

    elif matrix_type == "full":
        # Check symmetry
        if not np.allclose(matrix, matrix.T, atol=tolerance):
            return False, "Matrix is not symmetric"

        # Check positive definite (all eigenvalues > 0)
        try:
            eigenvalues = np.linalg.eigvalsh(matrix)
            if np.any(eigenvalues <= tolerance):
                return (
                    False,
                    f"Matrix is not positive definite (min eigenvalue: {eigenvalues.min():.2e})",
                )
        except np.linalg.LinAlgError as e:
            return False, f"Failed to compute eigenvalues: {e}"

        # Check condition number (warn if ill-conditioned)
        condition_number = np.linalg.cond(matrix)
        if condition_number > 1e10:
            logger.warning(
                f"Weight matrix is ill-conditioned (condition number: {condition_number:.2e})"
            )

        return (
            True,
            f"Valid full covariance weight matrix (condition number: {condition_number:.2e})",
        )

    else:
        return False, f"Unknown matrix_type: {matrix_type}"


def compute_wls_weights(
    n_series: Optional[int] = None,
    variances: Optional[np.ndarray] = None,
    data: Optional[pd.DataFrame] = None,
    method: Literal["ols", "diagonal", "sample", "shrinkage"] = "ols",
) -> np.ndarray:
    """
    Unified interface for computing WLS weight matrices.

    Supports multiple methods:
    - 'ols': Identity matrix (no weighting)
    - 'diagonal': Diagonal matrix from variances or data
    - 'sample': Sample covariance from data
    - 'shrinkage': Ledoit-Wolf shrinkage covariance from data

    Args:
        n_series: Number of series (required for 'ols' if data not provided)
        variances: Variance array (required for 'diagonal' if data not provided)
        data: Historical data or forecast errors (required for 'sample'/'shrinkage')
        method: Weight matrix computation method

    Returns:
        Weight matrix (n_series x n_series)

    Raises:
        ValueError: If required arguments missing for chosen method

    Example:
        ```python
        # OLS (identity)
        weights = compute_wls_weights(n_series=5, method='ols')

        # OLS from data (infers n_series)
        data = pd.DataFrame(np.random.randn(50, 4))
        weights = compute_wls_weights(data=data, method='ols')

        # WLS with variances
        weights = compute_wls_weights(
            variances=np.array([1, 4, 9]),
            method='diagonal'
        )

        # MinT with shrinkage
        errors = pd.DataFrame(np.random.randn(50, 4))
        weights = compute_wls_weights(data=errors, method='shrinkage')
        ```
    """
    if method == "ols":
        # Infer n_series from data if not provided
        if n_series is None:
            if data is not None:
                n_series = len(data.columns)
            else:
                raise ValueError("Either 'n_series' or 'data' required for 'ols' method")
        return np.eye(n_series)

    elif method == "diagonal":
        if variances is not None:
            return compute_diagonal_weights(variances)
        elif data is not None:
            return compute_variance_weights(data)
        else:
            raise ValueError("Either 'variances' or 'data' required for 'diagonal' method")

    elif method == "sample":
        if data is None:
            raise ValueError("'data' required for 'sample' method")
        return compute_sample_covariance(data, ensure_pd=True)

    elif method == "shrinkage":
        if data is None:
            raise ValueError("'data' required for 'shrinkage' method")
        return compute_shrinkage_covariance(data)

    else:
        raise ValueError(
            f"Invalid method '{method}'. Choose from: 'ols', 'diagonal', 'sample', 'shrinkage'"
        )


def compute_precision_matrix(covariance: np.ndarray, regularization: float = 0.0) -> np.ndarray:
    """
    Compute precision matrix (inverse of covariance matrix).

    The precision matrix is the inverse of the covariance matrix and represents
    partial correlations between variables. Used in optimal forecast reconciliation.

    Args:
        covariance: Covariance matrix (must be positive definite)
        regularization: Ridge regularization parameter (added to diagonal)

    Returns:
        Precision matrix (inverse of covariance)

    Raises:
        ValueError: If matrix is singular and regularization not sufficient

    Example:
        ```python
        cov = np.array([[2, 1], [1, 2]])
        precision = compute_precision_matrix(cov)
        # precision @ cov ≈ I
        ```
    """
    # Add regularization if specified
    if regularization > 0:
        regularized = covariance + regularization * np.eye(covariance.shape[0])
    else:
        regularized = covariance

    # Compute inverse
    try:
        precision = np.linalg.inv(regularized)
    except np.linalg.LinAlgError as e:
        logger.error(
            "Failed to invert covariance matrix",
            error=str(e),
            condition_number=float(np.linalg.cond(covariance)),
            regularization=regularization,
        )
        raise ValueError(
            f"Covariance matrix is singular. "
            f"Increase regularization (current: {regularization})"
        ) from e

    logger.debug(
        "Computed precision matrix",
        matrix_size=covariance.shape[0],
        regularization=regularization,
        condition_number=float(np.linalg.cond(precision)),
    )

    return precision
