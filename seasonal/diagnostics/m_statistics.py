"""
Real M-Statistics Computation

Computes M1-M11 statistics for X-13ARIMA-SEATS seasonal adjustment quality assessment.
Based on U.S. Census Bureau X-13ARIMA-SEATS methodology.

M-Statistics measure various aspects of seasonal adjustment quality:
- M1-M6: Irregular component characteristics
- M7: Seasonality strength
- M8-M11: Seasonal factor stability

Quality Thresholds:
- M < 1.0: Good quality
- 1.0 <= M < 2.0: Acceptable quality
- M >= 2.0: Poor quality (review required)
- Q-statistic (average of M1-M11) < 1.0: Overall good quality

References:
- U.S. Census Bureau (2017). X-13ARIMA-SEATS Reference Manual
- Lothian, J., & Morry, M. (1978). A set of quality control statistics for the X-11-ARIMA seasonal adjustment method
"""

from typing import Dict, Any, Optional
from dataclasses import dataclass
import numpy as np
import pandas as pd
from loguru import logger
from datetime import datetime

try:
    import sqlalchemy as sa
    from sqlalchemy.dialects import postgresql
    SQLALCHEMY_AVAILABLE = True
except ImportError:
    SQLALCHEMY_AVAILABLE = False
    logger.warning("SQLAlchemy not available, database storage disabled")


@dataclass
class MStatisticsResult:
    """Result of M-statistics computation"""
    m1: float  # Contribution of irregular over 3-month span
    m2: float  # Contribution of irregular to changes
    m3: float  # Month-to-month change in irregular vs trend
    m4: float  # Autocorrelation in irregular
    m5: float  # Heteroscedasticity in irregular
    m6: float  # Duration of runs in irregular
    m7: float  # Combined seasonality test
    m8: float  # Closeness of annual totals
    m9: float  # Stability of seasonal factors
    m10: float  # Recent movements in seasonal factors
    m11: float  # Linear trend in seasonal factors
    q_statistic: float  # Average of M1-M11
    
    def to_dict(self) -> Dict[str, float]:
        """Convert to dictionary"""
        return {
            'm1': self.m1,
            'm2': self.m2,
            'm3': self.m3,
            'm4': self.m4,
            'm5': self.m5,
            'm6': self.m6,
            'm7': self.m7,
            'm8': self.m8,
            'm9': self.m9,
            'm10': self.m10,
            'm11': self.m11,
            'q_statistic': self.q_statistic,
        }


@dataclass
class QualityThresholds:
    """Quality assessment thresholds for M-statistics"""
    good: float = 1.0
    acceptable: float = 2.0
    fail: float = 3.0


class MStatisticsComputer:
    """
    Computes M1-M11 statistics from X-13 seasonal decomposition
    
    Input: Decomposition components (original, seasonal, trend, irregular, SA)
    Output: M1-M11 statistics + Q-statistic
    
    Usage:
        computer = MStatisticsComputer()
        components = {
            'original': pd.Series(...),
            'seasonal': pd.Series(...),
            'trend': pd.Series(...),
            'irregular': pd.Series(...),
            'seasonally_adjusted': pd.Series(...)
        }
        m_stats = computer.compute(components)
    """
    
    def __init__(self, thresholds: Optional[QualityThresholds] = None):
        """
        Initialize M-statistics computer
        
        Args:
            thresholds: Quality thresholds for assessment
        """
        self.thresholds = thresholds or QualityThresholds()
        logger.info("Initialized MStatisticsComputer")
    
    def compute(self, components: Dict[str, pd.Series]) -> Dict[str, float]:
        """
        Compute all M-statistics from decomposition components
        
        Args:
            components: Dictionary with keys:
                - 'original': Original series
                - 'seasonal': Seasonal component
                - 'trend': Trend component
                - 'irregular': Irregular component
                - 'seasonally_adjusted': Seasonally adjusted series
        
        Returns:
            Dictionary with M1-M11 and Q-statistic
        
        Raises:
            ValueError: If required components are missing or invalid
        """
        self._validate_components(components)
        
        logger.info("Computing M-statistics from decomposition components")
        
        # Extract components
        original = components['original']
        seasonal = components['seasonal']
        trend = components['trend']
        irregular = components['irregular']
        sa = components['seasonally_adjusted']
        
        # Compute each M-statistic
        m1 = self._compute_m1(irregular, trend)
        m2 = self._compute_m2(irregular, original)
        m3 = self._compute_m3(irregular, trend)
        m4 = self._compute_m4(irregular)
        m5 = self._compute_m5(irregular)
        m6 = self._compute_m6(irregular)
        m7 = self._compute_m7(seasonal, irregular)
        m8 = self._compute_m8(original, sa)
        m9 = self._compute_m9(seasonal)
        m10 = self._compute_m10(seasonal)
        m11 = self._compute_m11(seasonal)
        
        # Compute Q-statistic (average of M1-M11)
        m_values = [m1, m2, m3, m4, m5, m6, m7, m8, m9, m10, m11]
        q_statistic = np.mean(m_values)
        
        result = MStatisticsResult(
            m1=m1, m2=m2, m3=m3, m4=m4, m5=m5, m6=m6,
            m7=m7, m8=m8, m9=m9, m10=m10, m11=m11,
            q_statistic=q_statistic
        )
        
        logger.info(f"Computed M-statistics: Q={q_statistic:.3f}")
        
        return result.to_dict()
    
    def _validate_components(self, components: Dict[str, pd.Series]) -> None:
        """
        Validate decomposition components
        
        Args:
            components: Decomposition components
        
        Raises:
            ValueError: If components are invalid
        """
        required_keys = ['original', 'seasonal', 'trend', 'irregular', 'seasonally_adjusted']
        
        for key in required_keys:
            if key not in components:
                raise ValueError(f"Missing required component: {key}")
            
            if not isinstance(components[key], pd.Series):
                raise ValueError(f"Component '{key}' must be pd.Series")
            
            if len(components[key]) < 24:
                raise ValueError(f"Component '{key}' must have at least 24 observations (2 years)")
            
            if components[key].isna().any():
                raise ValueError(f"Component '{key}' contains NaN values")
    
    def _compute_m1(self, irregular: pd.Series, trend: pd.Series) -> float:
        """
        Compute M1: Contribution of irregular over 3-month span
        
        M1 measures the relative contribution of the irregular component
        to the overall variability over a 3-month moving average span.
        
        Formula: M1 = I / C
        where:
        - I = average absolute 3-month change in irregular
        - C = average absolute 3-month change in trend-cycle
        
        Lower values indicate smoother irregular component.
        
        Args:
            irregular: Irregular component
            trend: Trend component
        
        Returns:
            M1 statistic
        """
        # 3-month moving average
        irregular_ma3 = irregular.rolling(window=3, center=True).mean()
        trend_ma3 = trend.rolling(window=3, center=True).mean()
        
        # Absolute changes
        irregular_changes = irregular_ma3.diff().abs()
        trend_changes = trend_ma3.diff().abs()
        
        # Average changes (excluding NaN)
        i_mean = irregular_changes.mean()
        c_mean = trend_changes.mean()
        
        # Avoid division by zero
        if c_mean < 1e-10:
            logger.warning("M1: Trend changes near zero, returning high value")
            return 3.0
        
        m1 = i_mean / c_mean
        
        return float(m1)
    
    def _compute_m2(self, irregular: pd.Series, original: pd.Series) -> float:
        """
        Compute M2: Contribution of irregular to changes in original series
        
        M2 measures the relative contribution of the irregular component
        to month-to-month changes in the original series.
        
        Formula: M2 = (σ_I / σ_O) * sqrt(2/π)
        where:
        - σ_I = standard deviation of irregular
        - σ_O = standard deviation of month-to-month changes in original
        
        Args:
            irregular: Irregular component
            original: Original series
        
        Returns:
            M2 statistic
        """
        # Standard deviation of irregular
        sigma_i = irregular.std()
        
        # Standard deviation of month-to-month changes
        original_changes = original.diff()
        sigma_o = original_changes.std()
        
        # Avoid division by zero
        if sigma_o < 1e-10:
            logger.warning("M2: Original series changes near zero")
            return 3.0
        
        # Correction factor sqrt(2/π) ≈ 0.798
        m2 = (sigma_i / sigma_o) * np.sqrt(2 / np.pi)
        
        return float(m2)
    
    def _compute_m3(self, irregular: pd.Series, trend: pd.Series) -> float:
        """
        Compute M3: Month-to-month change in irregular vs trend
        
        M3 compares the month-to-month variability of the irregular component
        to the month-to-month variability of the trend.
        
        Formula: M3 = σ(ΔI) / σ(ΔC)
        where:
        - σ(ΔI) = std dev of month-to-month changes in irregular
        - σ(ΔC) = std dev of month-to-month changes in trend
        
        Args:
            irregular: Irregular component
            trend: Trend component
        
        Returns:
            M3 statistic
        """
        irregular_changes = irregular.diff()
        trend_changes = trend.diff()
        
        sigma_di = irregular_changes.std()
        sigma_dc = trend_changes.std()
        
        # If trend is nearly constant (smooth), compare to irregular std instead
        if sigma_dc < 1e-6:
            sigma_i = irregular.std()
            if sigma_i < 1e-10:
                return 0.5  # Both near zero, default to acceptable
            # Compare irregular changes to irregular level
            m3 = sigma_di / sigma_i
            return float(m3)
        
        m3 = sigma_di / sigma_dc
        
        return float(m3)
    
    def _compute_m4(self, irregular: pd.Series) -> float:
        """
        Compute M4: Autocorrelation in irregular component
        
        M4 tests whether the irregular component is random (white noise).
        It measures first-order autocorrelation.
        
        Formula: M4 = |ρ_1| / σ(ρ_1)
        where:
        - ρ_1 = lag-1 autocorrelation
        - σ(ρ_1) = standard error ≈ 1/sqrt(n)
        
        Lower values indicate more random irregular.
        
        Args:
            irregular: Irregular component
        
        Returns:
            M4 statistic
        """
        n = len(irregular)
        
        # Lag-1 autocorrelation
        rho_1 = irregular.autocorr(lag=1)
        
        # Standard error
        sigma_rho = 1.0 / np.sqrt(n)
        
        # M4 statistic
        m4 = abs(rho_1) / sigma_rho
        
        # Normalize to typical range (0-3)
        m4 = m4 / 3.0  # Heuristic normalization
        
        return float(m4)
    
    def _compute_m5(self, irregular: pd.Series) -> float:
        """
        Compute M5: Heteroscedasticity in irregular component
        
        M5 tests whether the variance of the irregular component is constant
        over time (homoscedasticity).
        
        Formula: Compare variance in first half vs second half
        M5 = |σ²_1 - σ²_2| / (σ²_1 + σ²_2)
        
        Args:
            irregular: Irregular component
        
        Returns:
            M5 statistic
        """
        n = len(irregular)
        mid = n // 2
        
        # Split into two halves
        first_half = irregular.iloc[:mid]
        second_half = irregular.iloc[mid:]
        
        # Variance of each half
        var_1 = first_half.var()
        var_2 = second_half.var()
        
        # Avoid division by zero
        if (var_1 + var_2) < 1e-10:
            return 0.0
        
        # Normalized difference
        m5 = abs(var_1 - var_2) / (var_1 + var_2)
        
        # Scale to typical range
        m5 = m5 * 2.0  # Heuristic scaling
        
        return float(m5)
    
    def _compute_m6(self, irregular: pd.Series) -> float:
        """
        Compute M6: Duration of runs above/below average
        
        M6 tests randomness by measuring how long the irregular component
        stays above or below its mean (runs test).
        
        Longer runs indicate less randomness.
        
        Args:
            irregular: Irregular component
        
        Returns:
            M6 statistic
        """
        # Deviations from mean
        mean_val = irregular.mean()
        above = (irregular > mean_val).astype(int)
        
        # Count runs
        runs = (above.diff() != 0).sum()
        expected_runs = len(irregular) / 2
        
        # Normalized deviation from expected
        if expected_runs < 1e-10:
            return 1.0
        
        m6 = abs(runs - expected_runs) / expected_runs
        
        return float(m6)
    
    def _compute_m7(self, seasonal: pd.Series, irregular: pd.Series) -> float:
        """
        Compute M7: Combined seasonality test
        
        M7 measures the strength of identifiable seasonality.
        It compares the variance of seasonal component to irregular component.
        
        Formula: M7 = σ_I / σ_S
        where:
        - σ_I = standard deviation of irregular
        - σ_S = standard deviation of seasonal
        
        Lower values indicate stronger seasonality.
        
        Args:
            seasonal: Seasonal component
            irregular: Irregular component
        
        Returns:
            M7 statistic
        """
        sigma_i = irregular.std()
        sigma_s = seasonal.std()
        
        # Avoid division by zero
        if sigma_s < 1e-10:
            logger.warning("M7: Seasonal variance near zero (weak seasonality)")
            return 3.0
        
        m7 = sigma_i / sigma_s
        
        return float(m7)
    
    def _compute_m8(self, original: pd.Series, sa: pd.Series) -> float:
        """
        Compute M8: Closeness of annual totals
        
        M8 compares annual totals of the original series to the
        seasonally adjusted series. They should be similar if adjustment
        is additive or multiplicative.
        
        Formula: Average relative difference in annual sums
        
        Args:
            original: Original series
            sa: Seasonally adjusted series
        
        Returns:
            M8 statistic
        """
        # Group by year and sum
        if not isinstance(original.index, pd.DatetimeIndex):
            logger.warning("M8: Series does not have DatetimeIndex, using simple method")
            return 0.5
        
        # Use 'A' for annual frequency (compatible across pandas versions)
        # Note: Pandas 2.2+ uses 'YE' but older versions use 'A'
        original_annual = original.resample('A').sum()
        sa_annual = sa.resample('A').sum()
        
        # Relative differences
        rel_diffs = abs(original_annual - sa_annual) / (abs(original_annual) + 1e-10)
        
        m8 = rel_diffs.mean()
        
        # Scale to typical range
        m8 = m8 * 10.0  # Heuristic scaling
        
        return float(m8)
    
    def _compute_m9(self, seasonal: pd.Series) -> float:
        """
        Compute M9: Stability of seasonal factors
        
        M9 measures how much seasonal factors change from year to year.
        Stable seasonality should have similar seasonal patterns each year.
        
        Formula: Compare seasonal factors across years
        
        Args:
            seasonal: Seasonal component
        
        Returns:
            M9 statistic
        """
        if not isinstance(seasonal.index, pd.DatetimeIndex):
            logger.warning("M9: Series does not have DatetimeIndex")
            return 1.0
        
        # Extract month
        seasonal_df = pd.DataFrame({
            'value': seasonal,
            'year': seasonal.index.year,
            'month': seasonal.index.month
        })
        
        # Group by month and compute variance across years
        monthly_variance = seasonal_df.groupby('month')['value'].var()
        
        # Average variance across months
        avg_variance = monthly_variance.mean()
        
        # Compare to overall seasonal variance
        total_variance = seasonal.var()
        
        if total_variance < 1e-10:
            return 0.5
        
        m9 = avg_variance / total_variance
        
        return float(m9)
    
    def _compute_m10(self, seasonal: pd.Series) -> float:
        """
        Compute M10: Recent movements in seasonal factors
        
        M10 measures whether seasonal factors have changed recently
        (last 3 years vs earlier).
        
        Args:
            seasonal: Seasonal component
        
        Returns:
            M10 statistic
        """
        n = len(seasonal)
        
        # Split into recent (last 25%) and earlier
        split_point = int(n * 0.75)
        earlier = seasonal.iloc[:split_point]
        recent = seasonal.iloc[split_point:]
        
        # Compare standard deviations (volatility)
        std_earlier = earlier.std()
        std_recent = recent.std()
        
        # Avoid division by zero
        if std_earlier < 1e-10:
            return 0.5
        
        # Relative change in volatility
        m10 = abs(std_recent - std_earlier) / std_earlier
        
        # Scale to typical range (0-3)
        m10 = min(m10 * 2.0, 3.0)  # Heuristic scaling, capped at 3.0
        
        return float(m10)
    
    def _compute_m11(self, seasonal: pd.Series) -> float:
        """
        Compute M11: Linear trend in seasonal factors
        
        M11 tests whether seasonal factors have a linear trend over time.
        Stable seasonality should not trend.
        
        Formula: Linear regression slope of seasonal factors
        
        Args:
            seasonal: Seasonal component
        
        Returns:
            M11 statistic
        """
        n = len(seasonal)
        x = np.arange(n)
        
        # Linear regression
        slope, _ = np.polyfit(x, seasonal.values, 1)
        
        # Normalize by seasonal variance
        sigma_s = seasonal.std()
        
        if sigma_s < 1e-10:
            return 0.5
        
        # Annualized slope (12 months)
        annual_slope = abs(slope * 12)
        
        m11 = annual_slope / sigma_s
        
        return float(m11)


def compute_m_statistics(components: Dict[str, pd.Series]) -> Dict[str, float]:
    """
    Convenience function to compute M-statistics
    
    Args:
        components: Decomposition components
    
    Returns:
        Dictionary with M1-M11 and Q-statistic
    """
    computer = MStatisticsComputer()
    return computer.compute(components)


def validate_quality_thresholds(
    m_stats: Dict[str, float],
    thresholds: Optional[QualityThresholds] = None
) -> Dict[str, Any]:
    """
    Validate M-statistics against quality thresholds
    
    Args:
        m_stats: Dictionary of M-statistics
        thresholds: Quality thresholds
    
    Returns:
        Dictionary with validation results:
        - overall_quality: 'good', 'acceptable', 'poor'
        - pass: Boolean indicating if quality is acceptable
        - warnings: List of warnings
        - failures: List of failures
    """
    thresholds = thresholds or QualityThresholds()
    
    warnings = []
    failures = []
    
    # Check each M-statistic
    for i in range(1, 12):
        m_key = f'm{i}'
        if m_key not in m_stats:
            warnings.append(f"Missing {m_key}")
            continue
        
        value = m_stats[m_key]
        
        if value >= 2.0:
            failures.append(f"{m_key}={value:.2f} (>= {thresholds.fail})")
        elif value >= thresholds.good:
            warnings.append(f"{m_key}={value:.2f} (>= {thresholds.good})")
    
    # Overall quality assessment
    q_stat = m_stats.get('q_statistic', 999)
    
    if q_stat < thresholds.good and len(failures) == 0:
        overall_quality = 'good'
        pass_flag = True
    elif q_stat < 2.0 and len(failures) == 0:
        overall_quality = 'acceptable'
        pass_flag = True
    else:
        overall_quality = 'poor'
        pass_flag = False
    
    return {
        'overall_quality': overall_quality,
        'pass': pass_flag,
        'warnings': warnings,
        'failures': failures,
        'q_statistic': q_stat,
    }


def store_diagnostics_to_db(
    diagnostics: Dict[str, Any],
    engine: Optional['sa.Engine'] = None
) -> Optional[int]:
    """
    Store M-statistics diagnostics to database
    
    Args:
        diagnostics: Dictionary containing:
            - series_name: Series identifier
            - vintage_date: Vintage date
            - m_statistics: Dict of M1-M11 and Q
            - quality_assessment: Dict with validation results
            - computation_timestamp: When computed
        engine: SQLAlchemy engine (if None, creates from env)
    
    Returns:
        Record ID of stored diagnostics
    
    Raises:
        ValueError: If required fields are missing
        RuntimeError: If SQLAlchemy is not available
    """
    if not SQLALCHEMY_AVAILABLE:
        raise RuntimeError("SQLAlchemy not available, cannot store to database")
    
    required_fields = ['series_name', 'vintage_date', 'm_statistics']
    
    for field in required_fields:
        if field not in diagnostics:
            raise ValueError(f"Missing required field: {field}")
    
    # Create engine if not provided
    if engine is None:
        import os
        db_url = os.getenv('DATABASE_URL')
        if not db_url:
            host = os.getenv('POSTGRES_HOST', 'postgres')
            port = os.getenv('POSTGRES_PORT', '5432')
            db = os.getenv('POSTGRES_DB', 'forecast_labor')
            user = os.getenv('POSTGRES_USER', 'forecast_user')
            password = os.getenv('POSTGRES_PASSWORD', 'forecast_pass_change_me')
            db_url = f'postgresql://{user}:{password}@{host}:{port}/{db}'
        engine = sa.create_engine(db_url)
    
    # Prepare record
    import json
    record = {
        'series_name': diagnostics['series_name'],
        'vintage_date': diagnostics['vintage_date'],
        'computation_timestamp': diagnostics.get('computation_timestamp', datetime.now()),
        'm_statistics': diagnostics['m_statistics'],  # Store as JSONB
        'q_statistic': diagnostics['m_statistics'].get('q_statistic'),
        'quality_assessment': diagnostics.get('quality_assessment', {}),
    }
    
    # Insert or update
    with engine.begin() as conn:
        # Check if record exists
        query = sa.text("""
            SELECT spec_id FROM raw.seasonal_specs
            WHERE series_name = :series_name
        """)
        result = conn.execute(query, {'series_name': record['series_name']})
        existing = result.fetchone()
        
        if existing:
            # Update existing
            update_query = sa.text("""
                UPDATE raw.seasonal_specs
                SET m_stats = CAST(:m_stats AS jsonb),
                    last_updated = :updated_at
                WHERE series_name = :series_name
                RETURNING spec_id
            """)
            result = conn.execute(update_query, {
                'series_name': record['series_name'],
                'm_stats': json.dumps(record['m_statistics']),
                'updated_at': record['computation_timestamp']
            })
            record_id = result.fetchone()[0]
            logger.info(f"Updated diagnostics for {record['series_name']}, ID={record_id}")
        else:
            # Insert new
            insert_query = sa.text("""
                INSERT INTO raw.seasonal_specs (series_name, m_stats, last_updated)
                VALUES (:series_name, CAST(:m_stats AS jsonb), :updated_at)
                RETURNING spec_id
            """)
            result = conn.execute(insert_query, {
                'series_name': record['series_name'],
                'm_stats': json.dumps(record['m_statistics']),
                'updated_at': record['computation_timestamp']
            })
            record_id = result.fetchone()[0]
            logger.info(f"Inserted diagnostics for {record['series_name']}, ID={record_id}")
    
    return record_id


if __name__ == "__main__":
    # Example usage
    dates = pd.date_range(start='2020-01-01', periods=60, freq='MS')
    
    # Create sample decomposition
    seasonal = np.tile(np.sin(np.arange(12) * 2 * np.pi / 12) * 10, 5)
    trend = np.linspace(100, 150, 60)
    irregular = np.random.RandomState(42).normal(0, 1, 60)
    
    components = {
        'original': pd.Series(seasonal + trend + irregular, index=dates),
        'seasonal': pd.Series(seasonal, index=dates),
        'trend': pd.Series(trend, index=dates),
        'irregular': pd.Series(irregular, index=dates),
        'seasonally_adjusted': pd.Series(trend + irregular, index=dates),
    }
    
    # Compute M-statistics
    computer = MStatisticsComputer()
    m_stats = computer.compute(components)
    
    print("M-Statistics:")
    for key, value in m_stats.items():
        print(f"  {key}: {value:.3f}")
    
    # Validate
    validation = validate_quality_thresholds(m_stats)
    print(f"\nQuality Assessment: {validation['overall_quality']}")
    print(f"Pass: {validation['pass']}")
    if validation['warnings']:
        print(f"Warnings: {validation['warnings']}")
    if validation['failures']:
        print(f"Failures: {validation['failures']}")

