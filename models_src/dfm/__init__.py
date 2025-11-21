"""
Dynamic Factor Model (DFM) module

Provides mixed-frequency nowcasting using state-space models.
"""

from models_src.dfm.dfm_model import DynamicFactorModel
from models_src.dfm.state_space import (
    StateSpaceRepresentation,
    build_transition_matrix,
    build_observation_matrix,
    validate_state_space_dimensions,
)

__all__ = [
    'DynamicFactorModel',
    'StateSpaceRepresentation',
    'build_transition_matrix',
    'build_observation_matrix',
    'validate_state_space_dimensions',
]

