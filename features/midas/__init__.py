"""
MIDAS (Mixed Data Sampling) feature constructors.

Components:
- lag_constructor: Build lag features for mixed-frequency regression
"""

from features.midas.lag_constructor import (
    MIDASLagConstructor,
    get_frequency_ratio,
    infer_series_frequency,
    align_series_to_dates,
)
from features.midas.bridge import MIDASBridge
from features.midas.source_config import DEFAULT_SOURCE_CONFIGS, SourceConfig

__all__ = [
    "MIDASLagConstructor",
    "MIDASBridge",
    "SourceConfig",
    "DEFAULT_SOURCE_CONFIGS",
    "get_frequency_ratio",
    "infer_series_frequency",
    "align_series_to_dates",
]
