"""
UI Claims ETL Pipeline
Unemployment Insurance Initial and Continuing Claims (Weekly)

Data Source: U.S. Department of Labor
Frequency: Weekly (Thursday mornings)
Series: National + State level
Importance: #1 predictor of NFP
"""

from .claims_etl import UIClaimsETL

__all__ = ["UIClaimsETL"]

