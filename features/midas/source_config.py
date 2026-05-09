"""
Source configuration for MIDAS bridge feature construction.

This module maps ETL outputs to the columns and frequencies required by the
MIDAS bridge layer. Keeping this metadata explicit avoids hardcoded source
handling in model code.
"""

from dataclasses import dataclass
from typing import Dict, Literal


Frequency = Literal["D", "W", "M"]
AggregationMethod = Literal["last", "mean", "sum"]


@dataclass(frozen=True)
class SourceConfig:
    """
    Configuration for one data source consumed by MIDASBridge.

    Args:
        source_name: Canonical source identifier.
        frequency: Native source frequency: daily, weekly, or monthly.
        date_column: Column containing observation dates when input is a DataFrame.
        value_column: Column containing the numeric signal to bridge.
        n_lags: Number of high-frequency lags to expose. Monthly sources use 1.
        aggregation: Alignment method for monthly pass-through sources.
    """

    source_name: str
    frequency: Frequency
    date_column: str
    value_column: str
    n_lags: int
    aggregation: AggregationMethod = "last"

    def __post_init__(self) -> None:
        """Validate source configuration."""
        if self.frequency not in {"D", "W", "M"}:
            raise ValueError(f"frequency must be one of D/W/M, got {self.frequency}")
        if self.n_lags <= 0:
            raise ValueError(f"n_lags must be positive, got {self.n_lags}")
        if self.aggregation not in {"last", "mean", "sum"}:
            raise ValueError(f"aggregation must be last/mean/sum, got {self.aggregation}")
        if self.frequency == "M" and self.n_lags != 1:
            raise ValueError("monthly source configs must use n_lags=1")


DEFAULT_SOURCE_CONFIGS: Dict[str, SourceConfig] = {
    "treasury_withholdings": SourceConfig(
        source_name="treasury_withholdings",
        frequency="D",
        date_column="date",
        value_column="daily_withholding",
        n_lags=20,
        aggregation="sum",
    ),
    "ui_claims": SourceConfig(
        source_name="ui_claims",
        frequency="W",
        date_column="report_date",
        value_column="initial_claims",
        n_lags=8,
        aggregation="last",
    ),
    "bls_ces": SourceConfig(
        source_name="bls_ces",
        frequency="M",
        date_column="date",
        value_column="all_employees",
        n_lags=1,
        aggregation="last",
    ),
}
