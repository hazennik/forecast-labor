"""
Diagnostic Analyzers
Deep analysis of X-13 diagnostic statistics
"""

from typing import Dict, List, Any, Optional
from dataclasses import dataclass

import pandas as pd
import numpy as np
from loguru import logger


@dataclass
class DiagnosticThresholds:
    """Thresholds for diagnostic quality assessment"""
    # Q-statistic
    q_good: float = 1.0
    q_acceptable: float = 2.0
    
    # M-statistics
    m_good: float = 1.0
    m_warning: float = 2.0
    m_fail: float = 3.0
    
    # Ljung-Box p-value
    ljung_box_min: float = 0.05
    
    # Seasonality p-value
    seasonality_max: float = 0.01


class MStatAnalyzer:
    """
    Analyzer for M-statistics
    
    M-statistics measure different aspects of seasonal adjustment:
    - M1: Relative contribution of irregular to 3-month span
    - M2: Relative contribution of irregular to changes
    - M3: Irregular changes from month to month
    - M4-M6: Various randomness tests
    - M7: Combined seasonality test
    - M8-M11: Other quality measures
    """
    
    def __init__(self, thresholds: Optional[DiagnosticThresholds] = None):
        """Initialize M-stat analyzer"""
        self.thresholds = thresholds or DiagnosticThresholds()
    
    def analyze(self, diagnostics: Dict[str, Any]) -> Dict[str, Any]:
        """
        Analyze M-statistics
        
        Args:
            diagnostics: Diagnostic metrics containing M-stats
            
        Returns:
            Analysis results
        """
        m_stats = self._extract_m_stats(diagnostics)
        
        if not m_stats:
            return {"status": "no_data", "m_stats": {}}
        
        analysis = {
            "m_stats": m_stats,
            "quality_flags": self._check_quality(m_stats),
            "problem_areas": self._identify_problems(m_stats),
            "overall_score": self._calculate_score(m_stats),
        }
        
        return analysis
    
    def _extract_m_stats(self, diagnostics: Dict[str, Any]) -> Dict[str, float]:
        """Extract M-statistics from diagnostics"""
        m_stats = {}
        
        for i in range(1, 12):
            key = f"m{i}"
            if key in diagnostics:
                m_stats[key] = diagnostics[key]
        
        return m_stats
    
    def _check_quality(self, m_stats: Dict[str, float]) -> Dict[str, str]:
        """Check quality level for each M-statistic"""
        quality = {}
        
        for key, value in m_stats.items():
            if value < self.thresholds.m_good:
                quality[key] = "good"
            elif value < self.thresholds.m_warning:
                quality[key] = "acceptable"
            elif value < self.thresholds.m_fail:
                quality[key] = "warning"
            else:
                quality[key] = "fail"
        
        return quality
    
    def _identify_problems(self, m_stats: Dict[str, float]) -> List[str]:
        """Identify problem areas based on M-statistics"""
        problems = []
        
        # M1-M2: Irregular component issues
        if m_stats.get("m1", 0) > self.thresholds.m_warning:
            problems.append("Excessive irregular component (M1)")
        if m_stats.get("m2", 0) > self.thresholds.m_warning:
            problems.append("Irregular dominates changes (M2)")
        
        # M3-M6: Randomness issues
        if m_stats.get("m3", 0) > self.thresholds.m_warning:
            problems.append("Irregular not random enough (M3)")
        
        # M7: Seasonality issues
        if m_stats.get("m7", 0) > self.thresholds.m_warning:
            problems.append("Weak or unstable seasonality (M7)")
        
        # M8-M11: Other quality issues
        if m_stats.get("m8", 0) > self.thresholds.m_warning:
            problems.append("Seasonal factor changes too large (M8)")
        if m_stats.get("m9", 0) > self.thresholds.m_warning:
            problems.append("Trend changes too irregular (M9)")
        
        return problems
    
    def _calculate_score(self, m_stats: Dict[str, float]) -> float:
        """
        Calculate overall quality score from M-statistics
        
        Returns:
            Score between 0 (poor) and 100 (excellent)
        """
        if not m_stats:
            return 0.0
        
        # Convert M-stats to scores (lower M-stat = higher score)
        scores = []
        for value in m_stats.values():
            # Score: 100 if M < 1, decreases linearly to 0 at M = 3
            score = max(0, min(100, 100 * (1 - value / 3)))
            scores.append(score)
        
        # Average score
        return np.mean(scores)


class QStatAnalyzer:
    """
    Analyzer for Q-statistic
    
    Q-statistic is the average of M1-M11
    Provides overall assessment of seasonal adjustment quality
    """
    
    def __init__(self, thresholds: Optional[DiagnosticThresholds] = None):
        """Initialize Q-stat analyzer"""
        self.thresholds = thresholds or DiagnosticThresholds()
    
    def analyze(self, diagnostics: Dict[str, Any]) -> Dict[str, Any]:
        """
        Analyze Q-statistic
        
        Args:
            diagnostics: Diagnostic metrics
            
        Returns:
            Analysis results
        """
        q_stat = diagnostics.get("q_statistic")
        
        if q_stat is None:
            return {"status": "no_data"}
        
        # Determine quality level
        if q_stat < self.thresholds.q_good:
            quality = "good"
            message = "Excellent seasonal adjustment"
        elif q_stat < self.thresholds.q_acceptable:
            quality = "acceptable"
            message = "Acceptable seasonal adjustment, minor issues"
        else:
            quality = "poor"
            message = "Poor seasonal adjustment, review required"
        
        analysis = {
            "q_statistic": q_stat,
            "quality": quality,
            "message": message,
            "pass": q_stat < self.thresholds.q_acceptable,
        }
        
        return analysis


class StabilityAnalyzer:
    """
    Analyzer for seasonal adjustment stability over time
    
    Tracks how diagnostics change as new data is added
    Detects degradation in adjustment quality
    """
    
    def __init__(self):
        """Initialize stability analyzer"""
        self.history = []
    
    def add_observation(
        self,
        timestamp: str,
        diagnostics: Dict[str, Any]
    ):
        """
        Add diagnostic observation to history
        
        Args:
            timestamp: Observation timestamp
            diagnostics: Diagnostic metrics
        """
        observation = {
            "timestamp": timestamp,
            **diagnostics
        }
        self.history.append(observation)
    
    def analyze_stability(self, window: int = 12) -> Dict[str, Any]:
        """
        Analyze stability of diagnostics over time
        
        Args:
            window: Number of recent observations to analyze
            
        Returns:
            Stability analysis
        """
        if len(self.history) < 2:
            return {"status": "insufficient_data"}
        
        # Get recent history
        recent = self.history[-window:]
        df = pd.DataFrame(recent)
        
        if "q_statistic" not in df.columns:
            return {"status": "no_q_statistic"}
        
        # Calculate stability metrics
        q_values = df["q_statistic"].dropna()
        
        analysis = {
            "observations": len(recent),
            "q_mean": q_values.mean(),
            "q_std": q_values.std(),
            "q_trend": self._calculate_trend(q_values),
            "q_current": q_values.iloc[-1] if len(q_values) > 0 else None,
            "stable": q_values.std() < 0.2,  # Low variability
            "degrading": self._is_degrading(q_values),
        }
        
        return analysis
    
    def _calculate_trend(self, series: pd.Series) -> float:
        """
        Calculate trend in series using linear regression
        
        Returns:
            Slope (positive = increasing, negative = decreasing)
        """
        if len(series) < 3:
            return 0.0
        
        x = np.arange(len(series))
        y = series.values
        
        # Simple linear regression
        slope = np.polyfit(x, y, 1)[0]
        
        return slope
    
    def _is_degrading(self, series: pd.Series, threshold: float = 0.05) -> bool:
        """
        Check if quality is degrading over time
        
        Args:
            series: Q-statistic time series
            threshold: Minimum slope to consider degrading
            
        Returns:
            True if degrading
        """
        trend = self._calculate_trend(series)
        
        # Positive trend in Q-stat means degrading quality
        return trend > threshold
    
    def get_history_dataframe(self) -> pd.DataFrame:
        """
        Get diagnostic history as DataFrame
        
        Returns:
            DataFrame with all observations
        """
        return pd.DataFrame(self.history)


# Example usage
if __name__ == "__main__":
    # Sample diagnostics
    diagnostics = {
        "m1": 0.45,
        "m2": 0.52,
        "m3": 0.41,
        "m4": 0.38,
        "m5": 0.46,
        "m6": 0.50,
        "m7": 0.44,
        "m8": 0.47,
        "m9": 0.42,
        "m10": 0.49,
        "m11": 0.51,
        "q_statistic": 0.46,
    }
    
    # M-stat analysis
    m_analyzer = MStatAnalyzer()
    m_analysis = m_analyzer.analyze(diagnostics)
    
    print("M-Statistic Analysis:")
    print(f"  Overall Score: {m_analysis['overall_score']:.1f}/100")
    print(f"  Problems: {m_analysis['problem_areas']}")
    
    # Q-stat analysis
    q_analyzer = QStatAnalyzer()
    q_analysis = q_analyzer.analyze(diagnostics)
    
    print(f"\nQ-Statistic Analysis:")
    print(f"  Q = {q_analysis['q_statistic']:.3f}")
    print(f"  Quality: {q_analysis['quality']}")
    print(f"  Message: {q_analysis['message']}")

