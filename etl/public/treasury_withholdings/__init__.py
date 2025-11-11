"""
Treasury Withholdings ETL Pipeline
Daily Treasury Tax Withholdings (IRS Collections)

Data Source: U.S. Treasury - Daily Treasury Statement
Frequency: Daily (business days)
Importance: #2 predictor of NFP (real-time payroll proxy)
"""

from .treasury_etl import TreasuryWithholdingsETL

__all__ = ["TreasuryWithholdingsETL"]

