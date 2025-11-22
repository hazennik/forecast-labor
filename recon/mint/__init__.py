"""
MinT (Minimum Trace) hierarchical forecast reconciliation.

Ensures forecasts are coherent (state forecasts sum to national total)
while minimizing forecast error variance.
"""

from recon.mint.mint_reconciler import MinTReconciler
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

__all__ = [
    "MinTReconciler",
    "compute_variance_weights",
    "compute_diagonal_weights",
    "compute_sample_covariance",
    "compute_shrinkage_covariance",
    "ensure_positive_definite",
    "validate_weight_matrix",
    "compute_wls_weights",
    "compute_precision_matrix",
]

