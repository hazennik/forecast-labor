"""
Aggregation functions for hierarchical forecasting.

Components:
- state_aggregator: State → National aggregation (LAUS data)
- sector_aggregator: Sector → Total aggregation (CES data)
- hierarchical: MinT structure preparation and coherence validation
- utils: Weight computation utilities
"""

from features.aggregations.state_aggregator import StateAggregator
from features.aggregations.sector_aggregator import SectorAggregator
from features.aggregations.hierarchical import (
    prepare_mint_structure,
    validate_coherence,
)
from features.aggregations.utils import (
    compute_employment_weights,
    compute_population_weights,
)

__all__ = [
    "StateAggregator",
    "SectorAggregator",
    "prepare_mint_structure",
    "validate_coherence",
    "compute_employment_weights",
    "compute_population_weights",
]
