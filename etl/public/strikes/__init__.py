"""
Strikes ETL Pipeline
Labor Work Stoppages and Strike Data

Data Source: BLS Work Stoppages + FMCS
Frequency: Event-based / Monthly aggregation
Importance: Critical for adjusting NFP during disruption months
"""

from .strikes_etl import StrikesETL

__all__ = ["StrikesETL"]
