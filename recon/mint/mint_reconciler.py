"""
MinT (Minimum Trace) Reconciliation for Hierarchical Forecasts

Reconciles hierarchical forecasts (e.g., state → national) to ensure coherence
while minimizing forecast error variance. Implements multiple reconciliation methods:

1. **OLS**: Ordinary Least Squares (identity weights)
2. **WLS**: Weighted Least Squares (variance-based weights)
3. **MinT(Sample)**: Minimum Trace with sample covariance
4. **MinT(Shrink)**: Minimum Trace with shrinkage covariance (Ledoit-Wolf)

Key Features:
- Ensures coherence: national = Σstates (within numerical tolerance)
- Minimizes trace of forecast error covariance matrix
- Supports multiple weighting schemes
- Deterministic reconciliation (no randomness)
- Handles numerical stability issues

References:
- Wickramasuriya et al. (2019): "Optimal forecast reconciliation for hierarchical 
  and grouped time series through trace minimization"
- Hyndman et al. (2011): "Optimal combination forecasts for hierarchical time series"
- Athanasopoulos et al. (2017): "Forecast reconciliation: A review"
"""

from typing import Dict, Any, Optional, Literal
import numpy as np
import pandas as pd
from loguru import logger
from sklearn.covariance import LedoitWolf

# Import Phase 4 hierarchical utilities
from features.aggregations.hierarchical import (
    build_summing_matrix,
    validate_coherence,
    compute_coherence_errors
)


class MinTReconciler:
    """
    MinT reconciliation for hierarchical forecasts.
    
    Ensures forecasts are coherent (sum correctly across hierarchy levels)
    while minimizing the trace of the forecast error covariance matrix.
    
    Reconciliation Methods:
    - 'ols': Identity weight matrix (W = I)
    - 'wls': Diagonal weight matrix (W = diag(var))
    - 'mint_sample': Sample covariance weight matrix
    - 'mint_shrink': Ledoit-Wolf shrinkage covariance
    
    Parameters:
        method: Reconciliation method
        hierarchy_type: Type of hierarchy ('single_level' for state→national)
        
    Attributes:
        summing_matrix_: Summing matrix S (after fit)
        weight_matrix_: Weight matrix W (after fit)
        n_bottom_: Number of bottom-level series
        n_total_: Total number of series (bottom + aggregates)
        is_fitted_: Whether reconciler has been fitted
        
    Example:
        ```python
        # Base forecasts (may not sum correctly)
        base_forecasts = pd.DataFrame({
            'national': [200, 205, 210],
            'CA': [80, 82, 84],
            'TX': [60, 62, 64],
            'NY': [55, 56, 57]  # Sum ≠ national
        })
        
        # Reconcile
        reconciler = MinTReconciler(method='mint_shrink')
        reconciler.fit(base_forecasts)
        reconciled = reconciler.reconcile(base_forecasts)
        
        # Now: reconciled['national'] = reconciled[['CA', 'TX', 'NY']].sum(axis=1)
        ```
    """
    
    def __init__(
        self,
        method: Literal['ols', 'wls', 'mint_sample', 'mint_shrink'] = 'mint_shrink',
        hierarchy_type: str = 'single_level'
    ):
        """
        Initialize MinT reconciler.
        
        Args:
            method: Reconciliation method
                - 'ols': Ordinary Least Squares (W = I)
                - 'wls': Weighted Least Squares (W = diag(var))
                - 'mint_sample': Sample covariance (W = Σ)
                - 'mint_shrink': Ledoit-Wolf shrinkage (W = Σ_shrink)
            hierarchy_type: Hierarchy structure ('single_level' only for now)
            
        Raises:
            ValueError: If method or hierarchy_type invalid
        """
        valid_methods = ['ols', 'wls', 'mint_sample', 'mint_shrink']
        if method not in valid_methods:
            raise ValueError(
                f"method must be one of {valid_methods}, got {method}"
            )
        
        if hierarchy_type != 'single_level':
            raise ValueError(
                f"Only 'single_level' hierarchy supported, got {hierarchy_type}"
            )
        
        self.method = method
        self.hierarchy_type = hierarchy_type
        
        # Fitted attributes (set during fit)
        self.summing_matrix_: Optional[np.ndarray] = None
        self.weight_matrix_: Optional[np.ndarray] = None
        self.n_bottom_: Optional[int] = None
        self.n_total_: Optional[int] = None
        self.is_fitted_: bool = False
        self.column_order_: Optional[list] = None
        
        logger.info(
            "Initialized MinTReconciler",
            method=method,
            hierarchy_type=hierarchy_type
        )
    
    def fit(
        self,
        forecasts: pd.DataFrame,
        forecast_errors: Optional[pd.DataFrame] = None
    ) -> 'MinTReconciler':
        """
        Fit reconciler to base forecasts.
        
        Computes summing matrix and weight matrix based on forecast structure
        and historical forecast errors.
        
        Args:
            forecasts: Base forecasts (columns: total, bottom_1, ..., bottom_n)
                      First column assumed to be aggregate (national)
            forecast_errors: Historical forecast errors for variance/covariance
                            estimation. If None, uses identity or sample variance
                            from forecasts themselves.
                            
        Returns:
            self: For method chaining
            
        Raises:
            ValueError: If inputs invalid
            
        Example:
            ```python
            base_forecasts = pd.DataFrame({
                'national': [200, 205],
                'CA': [80, 82],
                'TX': [60, 62],
                'NY': [55, 56]
            })
            reconciler.fit(base_forecasts)
            ```
        """
        # Validate inputs
        if forecasts.empty:
            raise ValueError("forecasts cannot be empty")
        
        if len(forecasts.columns) < 2:
            raise ValueError(
                "forecasts must have at least 2 columns (1 total + 1 bottom)"
            )
        
        # Store column order for consistent reconciliation
        self.column_order_ = list(forecasts.columns)
        
        # Extract dimensions
        self.n_total_ = len(forecasts.columns)
        self.n_bottom_ = self.n_total_ - 1  # First column is aggregate
        
        logger.info(
            "Fitting MinT reconciler",
            method=self.method,
            n_total_series=self.n_total_,
            n_bottom_series=self.n_bottom_,
            n_observations=len(forecasts)
        )
        
        # Build summing matrix (from Phase 4 utilities)
        self.summing_matrix_ = build_summing_matrix(
            n_bottom=self.n_bottom_,
            hierarchy_type=self.hierarchy_type
        )
        
        # Build weight matrix based on method
        if self.method == 'ols':
            # OLS: Identity weights (W = I)
            self.weight_matrix_ = np.eye(self.n_total_)
            
        elif self.method == 'wls':
            # WLS: Diagonal variance weights
            if forecast_errors is not None:
                variances = forecast_errors.var(axis=0).values
            else:
                # Use sample variance from forecasts
                variances = forecasts.var(axis=0).values
            
            # Avoid division by zero
            variances = np.maximum(variances, 1e-8)
            self.weight_matrix_ = np.diag(variances)
            
        elif self.method == 'mint_sample':
            # MinT with sample covariance
            if forecast_errors is not None:
                cov_matrix = forecast_errors.cov().values
            else:
                cov_matrix = forecasts.cov().values
            
            # Ensure positive definite
            self.weight_matrix_ = self._ensure_positive_definite(cov_matrix)
            
        elif self.method == 'mint_shrink':
            # MinT with Ledoit-Wolf shrinkage covariance
            if forecast_errors is not None:
                data = forecast_errors.values
            else:
                data = forecasts.values
            
            # Ledoit-Wolf shrinkage estimator
            lw = LedoitWolf()
            cov_matrix = lw.fit(data).covariance_
            
            self.weight_matrix_ = self._ensure_positive_definite(cov_matrix)
        
        self.is_fitted_ = True
        
        logger.info(
            "MinT reconciler fitted",
            method=self.method,
            summing_matrix_shape=self.summing_matrix_.shape,
            weight_matrix_shape=self.weight_matrix_.shape
        )
        
        return self
    
    def reconcile(
        self,
        forecasts: pd.DataFrame
    ) -> pd.DataFrame:
        """
        Reconcile forecasts to ensure coherence using MinT projection matrix.
        
        Applies MinT reconciliation via projection matrix formulation:
            ỹ = (I - W S⁺) y
        
        Where S⁺ = (S' W^-1 S)^-1 S' W^-1 is the generalized inverse (Moore-Penrose).
        
        This projection minimizes the trace of the forecast error covariance matrix
        subject to the linear coherence constraints: S ỹ_bottom = y_top (aggregate).
        
        Mathematics:
        - For single-level hierarchy: y = [y_top; y_bottom] where y_top = S @ y_bottom
        - Reconciled forecasts minimize tr(Var(ỹ - y_true)) subject to S ỹ_bottom = sum
        - Optimal solution: ỹ = y - W @ S⁺ @ (y_top - S @ y_bottom)
        - Equivalently: ỹ = (I - W @ S⁺) @ y where projection ensures coherence
        
        Args:
            forecasts: Base forecasts to reconcile (same structure as fit)
                      [aggregate_col, bottom_col_1, ..., bottom_col_n]
            
        Returns:
            Reconciled forecasts (coherent: national = Σstates, variance-minimized)
            
        Raises:
            ValueError: If not fitted or structure mismatch
            
        Example:
            ```python
            reconciled = reconciler.reconcile(base_forecasts)
            # Verify coherence
            assert np.allclose(
                reconciled['national'],
                reconciled[['CA', 'TX', 'NY']].sum(axis=1)
            )
            ```
        
        References:
            Wickramasuriya et al. (2019): "Optimal forecast reconciliation for 
            hierarchical and grouped time series through trace minimization"
        """
        if not self.is_fitted_:
            raise ValueError(
                "Reconciler must be fitted before reconciliation. Call fit() first."
            )
        
        # Validate structure matches fit
        if list(forecasts.columns) != self.column_order_:
            raise ValueError(
                f"Column mismatch. Expected {self.column_order_}, "
                f"got {list(forecasts.columns)}"
            )
        
        logger.debug(
            "Reconciling forecasts",
            n_observations=len(forecasts),
            method=self.method
        )
        
        # Convert to numpy for computation
        y = forecasts.values.T  # (n_total, n_obs) - Transpose for matrix ops
        S = self.summing_matrix_  # (n_agg, n_bottom) = (1, n_bottom)
        W = self.weight_matrix_  # (n_total, n_total)
        
        n_total = y.shape[0]
        n_obs = y.shape[1]
        
        # MinT reconciliation using projection matrix P = (I - W @ S⁺)
        # where S⁺ = (S' W^-1 S)^-1 S' W^-1 is the generalized inverse
        
        try:
            # Compute W^-1 (inverse of weight matrix)
            W_inv = np.linalg.inv(W)
            
            # For single-level hierarchy, we need to construct full projection matrix
            # Forecasts structure: [aggregate; bottom_series]
            # We need projection that enforces: aggregate = S @ bottom_series
            
            # Build selection matrix to extract bottom series
            # J = [0; I] selects bottom series from full vector
            J = np.vstack([np.zeros((1, self.n_bottom_)), np.eye(self.n_bottom_)])
            
            # Build summing structure matrix: U = [S; I]
            # This stacks aggregate = S @ bottom on top of bottom identity
            U = np.vstack([S, np.eye(self.n_bottom_)])  # (n_total, n_bottom)
            
            # Compute generalized inverse (Moore-Penrose): U⁺ = (U' W^-1 U)^-1 U' W^-1
            # This is the optimal reconciliation matrix
            U_T_W_inv = U.T @ W_inv  # (n_bottom, n_total)
            U_T_W_inv_U = U_T_W_inv @ U  # (n_bottom, n_bottom)
            
            # Invert (should be well-conditioned for proper hierarchy)
            U_T_W_inv_U_inv = np.linalg.inv(U_T_W_inv_U)  # (n_bottom, n_bottom)
            
            # Generalized inverse
            U_plus = U_T_W_inv_U_inv @ U_T_W_inv  # (n_bottom, n_total)
            
            # Projection matrix: P = U @ U⁺ = U @ (U' W^-1 U)^-1 @ U' W^-1
            # This projects onto coherent subspace while minimizing variance
            P = U @ U_plus  # (n_total, n_total)
            
            # Apply projection to reconcile forecasts
            y_reconciled = P @ y  # (n_total, n_obs)
            
            # Transpose back to (n_obs, n_total)
            reconciled = y_reconciled.T
            
        except np.linalg.LinAlgError as e:
            # Fallback if matrix inversion fails (numerical instability)
            logger.warning(
                f"Matrix inversion failed in MinT reconciliation: {e}. "
                "Falling back to simple coherence enforcement."
            )
            
            # Simple fallback: enforce coherence by averaging adjustments
            y_bottom = y[1:, :]  # (n_bottom, n_obs)
            y_top = y[0:1, :]  # (1, n_obs)
            
            # Compute incoherence
            y_bottom_sum = y_bottom.sum(axis=0, keepdims=True)  # (1, n_obs)
            incoherence = y_top - y_bottom_sum  # (1, n_obs)
            
            # Distribute equally (OLS-like)
            adjustments = incoherence / self.n_bottom_  # (1, n_obs)
            y_bottom_reconciled = y_bottom + adjustments
            y_top_reconciled = y_bottom_reconciled.sum(axis=0, keepdims=True)
            
            reconciled = np.vstack([y_top_reconciled, y_bottom_reconciled]).T
        
        # Convert back to DataFrame
        reconciled_df = pd.DataFrame(
            reconciled,
            index=forecasts.index,
            columns=forecasts.columns
        )
        
        # Log reconciliation statistics
        coherence_errors_before = compute_coherence_errors(
            forecasts,
            forecasts.columns[0],
            list(forecasts.columns[1:])
        )
        
        coherence_errors_after = compute_coherence_errors(
            reconciled_df,
            reconciled_df.columns[0],
            list(reconciled_df.columns[1:])
        )
        
        logger.info(
            "Reconciliation complete",
            mean_coherence_error_before=float(coherence_errors_before.mean()),
            mean_coherence_error_after=float(coherence_errors_after.mean()),
            max_coherence_error_after=float(np.abs(coherence_errors_after).max()),
            method=self.method
        )
        
        return reconciled_df
    
    def validate_coherence(
        self,
        forecasts: pd.DataFrame,
        tolerance: float = 1e-6
    ) -> bool:
        """
        Validate that forecasts are coherent (sum correctly).
        
        Args:
            forecasts: Forecasts to validate
            tolerance: Numerical tolerance for equality check
            
        Returns:
            True if coherent, False otherwise
        """
        return validate_coherence(
            forecasts,
            forecasts.columns[0],  # First column is total
            list(forecasts.columns[1:]),  # Rest are components
            tolerance=tolerance
        )
    
    def get_params(self) -> Dict[str, Any]:
        """
        Get reconciler parameters and metadata.
        
        Returns:
            Dictionary with configuration and fitted state
        """
        params = {
            'method': self.method,
            'hierarchy_type': self.hierarchy_type,
            'is_fitted': self.is_fitted_,
            'n_total': self.n_total_,
            'n_bottom': self.n_bottom_,
            'column_order': self.column_order_,
        }
        
        if self.is_fitted_:
            params['summing_matrix_shape'] = self.summing_matrix_.shape
            params['weight_matrix_shape'] = self.weight_matrix_.shape
        
        return params
    
    def _ensure_positive_definite(
        self,
        matrix: np.ndarray,
        min_eigenvalue: float = 1e-6
    ) -> np.ndarray:
        """
        Ensure matrix is positive definite by regularizing eigenvalues.
        
        Args:
            matrix: Covariance matrix (may not be positive definite)
            min_eigenvalue: Minimum eigenvalue threshold
            
        Returns:
            Positive definite matrix
        """
        # Eigenvalue decomposition
        eigenvalues, eigenvectors = np.linalg.eigh(matrix)
        
        # Regularize small/negative eigenvalues
        eigenvalues = np.maximum(eigenvalues, min_eigenvalue)
        
        # Reconstruct matrix
        regularized = eigenvectors @ np.diag(eigenvalues) @ eigenvectors.T
        
        # Ensure symmetry
        regularized = (regularized + regularized.T) / 2
        
        return regularized

