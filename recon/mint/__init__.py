"""
MinT (Minimum Trace) hierarchical forecast reconciliation.

Ensures forecasts are coherent (state forecasts sum to national total)
while minimizing forecast error variance.
"""

from recon.mint.mint_reconciler import MinTReconciler

__all__ = ["MinTReconciler"]

