"""
Real Q-Statistics Computation (Ljung-Box Test)

Computes Ljung-Box Q-statistics for testing autocorrelation in seasonal
adjustment residuals/irregular component.

Ljung-Box Test:
- Tests null hypothesis: No autocorrelation in residuals
- Q-statistic: Q = n(n+2) Σ(ρ²_k / (n-k)) for k=1 to h
- Under H0, Q ~ χ²(h) where h is number of lags tested
- p-value > 0.05: Residuals are random (good quality)
- p-value < 0.05: Residuals have autocorrelation (poor quality)

Quality Thresholds:
- p-value > 0.05: Good quality (residuals are random)
- p-value <= 0.05: Poor quality (significant autocorrelation)

References:
- Ljung, G. M., and Box, G. E. P. (1978). On a Measure of Lack of Fit in Time Series Models. 
  Biometrika, 65(2), 297-303.
- Box, G. E. P., and Pierce, D. A. (1970). Distribution of Residual Autocorrelations in 
  Autoregressive-Integrated Moving Average Time Series Models. JASA, 65(332), 1509-1526.
"""

from typing import Dict, Any, Optional
from dataclasses import dataclass
import numpy as np
import pandas as pd
from scipy import stats
from loguru import logger
from datetime import datetime


@dataclass
class QStatisticsResult:
    """Result of Q-statistics computation"""
    q_statistic: float  # Ljung-Box Q-statistic
    p_value: float  # p-value from chi-squared distribution
    lags_tested: int  # Number of lags tested
    degrees_of_freedom: int  # Degrees of freedom for chi-squared
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            'q_statistic': self.q_statistic,
            'p_value': self.p_value,
            'lags_tested': self.lags_tested,
            'degrees_of_freedom': self.degrees_of_freedom,
        }


class QStatisticsComputer:
    """
    Computes Ljung-Box Q-statistics for testing autocorrelation
    
    The Ljung-Box test is used to test whether autocorrelations of a time series
    are significantly different from zero. It's commonly used to check the
    randomness of residuals in seasonal adjustment.
    
    Usage:
        computer = QStatisticsComputer(lags=12)
        residuals = pd.Series(...)  # Irregular component or residuals
        q_stats = computer.compute(residuals)
        
        if q_stats['p_value'] > 0.05:
            print("Residuals are random (good quality)")
        else:
            print("Residuals have autocorrelation (poor quality)")
    """
    
    def __init__(self, lags: Optional[int] = None):
        """
        Initialize Q-statistics computer
        
        Args:
            lags: Number of lags to test (default: min(10, n//5) where n is series length)
        
        Raises:
            ValueError: If lags is not positive
        """
        if lags is not None and lags <= 0:
            raise ValueError(f"lags must be positive, got {lags}")
        
        self.lags = lags
        logger.info(f"Initialized QStatisticsComputer with lags={lags}")
    
    def compute(self, residuals: pd.Series) -> Dict[str, Any]:
        """
        Compute Ljung-Box Q-statistic for residuals
        
        Args:
            residuals: Time series residuals (irregular component)
        
        Returns:
            Dictionary with Q-statistic, p-value, lags tested, degrees of freedom
        
        Raises:
            ValueError: If series is too short or contains NaN values
        """
        self._validate_residuals(residuals)
        
        n = len(residuals)
        
        # Determine number of lags
        if self.lags is None:
            lags = min(10, n // 5)  # Default: 10 or 20% of series length
        else:
            lags = self.lags
        
        # Validate sufficient data
        if n < lags + 5:
            raise ValueError(
                f"Insufficient sample size: n={n} for lags={lags}. "
                f"Need at least {lags + 5} observations."
            )
        
        logger.info(f"Computing Ljung-Box Q-statistic for {n} observations, {lags} lags")
        
        # Compute Q-statistic
        q_statistic = self._compute_ljung_box_q(residuals, lags)
        
        # Compute p-value from chi-squared distribution
        p_value = 1 - stats.chi2.cdf(q_statistic, df=lags)
        
        result = QStatisticsResult(
            q_statistic=q_statistic,
            p_value=p_value,
            lags_tested=lags,
            degrees_of_freedom=lags
        )
        
        logger.info(
            f"Ljung-Box Q-statistic computed: Q={q_statistic:.3f}, "
            f"p-value={p_value:.4f}, lags={lags}"
        )
        
        return result.to_dict()
    
    def _validate_residuals(self, residuals: pd.Series) -> None:
        """
        Validate residuals series
        
        Args:
            residuals: Residuals to validate
        
        Raises:
            ValueError: If residuals are invalid
        """
        if not isinstance(residuals, pd.Series):
            raise ValueError("residuals must be pd.Series")
        
        if len(residuals) < 20:
            raise ValueError(
                f"residuals too short: {len(residuals)} observations, need at least 20"
            )
        
        if residuals.isna().any():
            raise ValueError("residuals contains NaN values")
    
    def _compute_ljung_box_q(self, residuals: pd.Series, lags: int) -> float:
        """
        Compute Ljung-Box Q-statistic
        
        Formula: Q = n(n+2) Σ(ρ²_k / (n-k)) for k=1 to h
        
        where:
        - n is the sample size
        - ρ_k is the sample autocorrelation at lag k
        - h is the number of lags tested
        
        Args:
            residuals: Time series residuals
            lags: Number of lags to test
        
        Returns:
            Ljung-Box Q-statistic
        """
        n = len(residuals)
        
        # Compute autocorrelations up to specified lags
        autocorrelations = self._compute_autocorrelations(residuals, lags)
        
        # Ljung-Box formula: Q = n(n+2) Σ(ρ²_k / (n-k))
        q_statistic = 0.0
        
        for k in range(1, lags + 1):
            rho_k = autocorrelations[k-1]
            q_statistic += (rho_k ** 2) / (n - k)
        
        q_statistic *= n * (n + 2)
        
        return float(q_statistic)
    
    def _compute_autocorrelations(self, series: pd.Series, lags: int) -> np.ndarray:
        """
        Compute sample autocorrelations up to specified lags
        
        Args:
            series: Time series
            lags: Number of lags
        
        Returns:
            Array of autocorrelations [ρ_1, ρ_2, ..., ρ_h]
        """
        autocorrs = np.zeros(lags)
        
        # Demean the series
        series_centered = series - series.mean()
        
        # Variance (lag-0 autocovariance)
        c0 = np.sum(series_centered ** 2) / len(series)
        
        # Compute autocorrelations for each lag
        for k in range(1, lags + 1):
            # Autocovariance at lag k
            ck = np.sum(series_centered.iloc[:-k].values * series_centered.iloc[k:].values) / len(series)
            
            # Autocorrelation = autocovariance / variance
            autocorrs[k-1] = ck / c0 if c0 > 1e-10 else 0.0
        
        return autocorrs


def compute_ljung_box(
    residuals: pd.Series,
    lags: Optional[int] = None
) -> Dict[str, Any]:
    """
    Convenience function to compute Ljung-Box Q-statistic
    
    Args:
        residuals: Time series residuals
        lags: Number of lags to test (default: min(10, n//5))
    
    Returns:
        Dictionary with Q-statistic, p-value, lags, degrees of freedom
    
    Example:
        >>> residuals = pd.Series(np.random.normal(0, 1, 100))
        >>> result = compute_ljung_box(residuals, lags=10)
        >>> print(f"Q = {result['q_statistic']:.2f}, p-value = {result['p_value']:.4f}")
    """
    computer = QStatisticsComputer(lags=lags)
    return computer.compute(residuals)


def validate_residual_randomness(
    q_stats: Dict[str, Any],
    alpha: float = 0.05
) -> Dict[str, Any]:
    """
    Validate residual randomness based on Q-statistics
    
    Args:
        q_stats: Dictionary with Q-statistic and p-value
        alpha: Significance level (default: 0.05)
    
    Returns:
        Dictionary with validation results:
        - quality: 'good' or 'poor'
        - pass: Boolean indicating if test passes
        - random: Boolean indicating if residuals are random
        - message: Interpretation message
    
    Example:
        >>> q_stats = {'q_statistic': 8.5, 'p_value': 0.58, 'lags_tested': 10}
        >>> validation = validate_residual_randomness(q_stats)
        >>> print(validation['quality'])  # 'good'
    """
    p_value = q_stats.get('p_value')
    q_statistic = q_stats.get('q_statistic')
    lags = q_stats.get('lags_tested', 'unknown')
    
    if p_value is None:
        raise ValueError("q_stats must contain 'p_value'")
    
    # Test passes if p-value > alpha (fail to reject null hypothesis)
    passes = p_value > alpha
    
    if passes:
        quality = 'good'
        message = (
            f"No significant autocorrelation detected (p-value={p_value:.4f} > {alpha}). "
            f"Residuals appear random."
        )
    else:
        quality = 'poor'
        message = (
            f"Significant autocorrelation detected (p-value={p_value:.4f} <= {alpha}). "
            f"Residuals are not random. Q={q_statistic:.2f} with {lags} lags."
        )
    
    return {
        'quality': quality,
        'pass': passes,
        'random': passes,
        'message': message,
        'alpha': alpha,
        'p_value': p_value,
    }


def store_q_statistics_to_db(
    q_statistics: Dict[str, Any],
    engine: Optional[Any] = None
) -> Optional[int]:
    """
    Store Q-statistics diagnostics to database
    
    Args:
        q_statistics: Dictionary containing:
            - series_name: Series identifier
            - vintage_date: Vintage date
            - q_statistic: Q-statistic value
            - p_value: p-value
            - lags_tested: Number of lags
            - quality_assessment: Dict with validation results
            - computation_timestamp: When computed
        engine: SQLAlchemy engine (if None, creates from env)
    
    Returns:
        Record ID of stored diagnostics
    
    Raises:
        ValueError: If required fields are missing
    """
    required_fields = ['series_name', 'vintage_date', 'q_statistic', 'p_value']
    
    for field in required_fields:
        if field not in q_statistics:
            raise ValueError(f"Missing required field: {field}")
    
    # For now, store in same table as M-statistics (raw.seasonal_specs)
    # Q-statistics will be stored in m_stats JSONB column alongside M-stats
    
    if engine is None:
        try:
            import sqlalchemy as sa
            import os
            db_url = os.getenv('DATABASE_URL', 'postgresql://forecast_user:forecast_pass@localhost:5432/forecast_db')
            engine = sa.create_engine(db_url)
        except ImportError:
            logger.warning("SQLAlchemy not available, cannot store to database")
            return None
    
    # Prepare record with Q-statistics
    import json
    record = {
        'series_name': q_statistics['series_name'],
        'vintage_date': q_statistics['vintage_date'],
        'computation_timestamp': q_statistics.get('computation_timestamp', datetime.now()),
        'q_statistics': {
            'q_statistic': q_statistics['q_statistic'],
            'p_value': q_statistics['p_value'],
            'lags_tested': q_statistics.get('lags_tested'),
            'degrees_of_freedom': q_statistics.get('degrees_of_freedom'),
            'quality_assessment': q_statistics.get('quality_assessment', {})
        }
    }
    
    # Insert or update
    try:
        import sqlalchemy as sa
        with engine.begin() as conn:
            # Check if record exists
            query = sa.text("""
                SELECT spec_id FROM raw.seasonal_specs
                WHERE series_name = :series_name
            """)
            result = conn.execute(query, {'series_name': record['series_name']})
            existing = result.fetchone()
            
            if existing:
                # Update existing - merge Q-stats into m_stats JSONB
                update_query = sa.text("""
                    UPDATE raw.seasonal_specs
                    SET m_stats = COALESCE(m_stats, '{}'::jsonb) || :q_stats::jsonb,
                        last_updated = :updated_at
                    WHERE series_name = :series_name
                    RETURNING spec_id
                """)
                result = conn.execute(update_query, {
                    'series_name': record['series_name'],
                    'q_stats': json.dumps(record['q_statistics']),
                    'updated_at': record['computation_timestamp']
                })
                record_id = result.fetchone()[0]
                logger.info(f"Updated Q-statistics for {record['series_name']}, ID={record_id}")
            else:
                # Insert new
                insert_query = sa.text("""
                    INSERT INTO raw.seasonal_specs (series_name, m_stats, last_updated)
                    VALUES (:series_name, :q_stats::jsonb, :updated_at)
                    RETURNING spec_id
                """)
                result = conn.execute(insert_query, {
                    'series_name': record['series_name'],
                    'q_stats': json.dumps(record['q_statistics']),
                    'updated_at': record['computation_timestamp']
                })
                record_id = result.fetchone()[0]
                logger.info(f"Inserted Q-statistics for {record['series_name']}, ID={record_id}")
        
        return record_id
    
    except Exception as e:
        logger.error(f"Failed to store Q-statistics to database: {e}", exc_info=True)
        return None


if __name__ == "__main__":
    # Example usage
    import matplotlib.pyplot as plt
    
    # Example 1: Random residuals (should pass)
    print("Example 1: Random Residuals")
    print("-" * 60)
    np.random.seed(42)
    random_residuals = pd.Series(np.random.normal(0, 1, 100))
    
    computer = QStatisticsComputer(lags=12)
    result = computer.compute(random_residuals)
    
    print(f"Q-statistic: {result['q_statistic']:.3f}")
    print(f"p-value: {result['p_value']:.4f}")
    print(f"Lags tested: {result['lags_tested']}")
    
    validation = validate_residual_randomness(result)
    print(f"Quality: {validation['quality']}")
    print(f"Message: {validation['message']}")
    print()
    
    # Example 2: Autocorrelated residuals (should fail)
    print("Example 2: Autocorrelated Residuals (AR(1))")
    print("-" * 60)
    ar_residuals = np.zeros(100)
    epsilon = np.random.normal(0, 1, 100)
    ar_residuals[0] = epsilon[0]
    
    for i in range(1, 100):
        ar_residuals[i] = 0.7 * ar_residuals[i-1] + epsilon[i]
    
    ar_residuals = pd.Series(ar_residuals)
    
    result_ar = computer.compute(ar_residuals)
    
    print(f"Q-statistic: {result_ar['q_statistic']:.3f}")
    print(f"p-value: {result_ar['p_value']:.4f}")
    print(f"Lags tested: {result_ar['lags_tested']}")
    
    validation_ar = validate_residual_randomness(result_ar)
    print(f"Quality: {validation_ar['quality']}")
    print(f"Message: {validation_ar['message']}")

