"""
BLS CES ETL Pipeline
Current Employment Statistics (Nonfarm Payrolls)

Data Source: Bureau of Labor Statistics
Frequency: Monthly (first Friday)
Importance: PRIMARY TARGET VARIABLE
Critical: Must maintain vintages for revision modeling
"""

from .ces_etl import CESETL

__all__ = ["CESETL"]
