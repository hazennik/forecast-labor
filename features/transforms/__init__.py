"""
Feature transformations.

Components:
- frequency: Frequency conversion (daily → weekly → monthly)
- calendar: Calendar adjustments and pay-period handling
- scaling: Standardization, normalization, winsorization
- pipeline: Transform pipeline for chaining operations
"""

from features.transforms.frequency import FrequencyConverter
from features.transforms.calendar import (
    PayPeriodIdentifier,
    identify_five_friday_months,
    count_business_days,
    compute_calendar_adjustment,
    get_holiday_calendar,
)
from features.transforms.scaling import (
    StandardScaler,
    MinMaxScaler,
    RobustScaler,
    Winsorizer,
)
from features.transforms.pipeline import TransformPipeline

__all__ = [
    "FrequencyConverter",
    "PayPeriodIdentifier",
    "identify_five_friday_months",
    "count_business_days",
    "compute_calendar_adjustment",
    "get_holiday_calendar",
    "StandardScaler",
    "MinMaxScaler",
    "RobustScaler",
    "Winsorizer",
    "TransformPipeline",
]
