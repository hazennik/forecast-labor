"""
Quality Degradation Monitor

Monitors M/Q statistics over time, detects degradation trends, and generates alerts.
Integrates with seasonal adjustment pipeline for continuous quality monitoring.

Phase 5.11.4: Quality Degradation Alerts
"""

from typing import Dict, List, Any, Optional
from datetime import datetime
from collections import deque, defaultdict
import numpy as np
from loguru import logger


class QualityMonitor:
    """
    Monitors seasonal adjustment quality over time and detects degradation trends.
    
    Features:
    - Tracks M/Q statistics across multiple runs
    - Detects increasing trends (quality degradation)
    - Generates structured alerts for ops monitoring
    - Supports multiple series independently
    - Database-compatible storage format
    
    Usage:
        monitor = QualityMonitor(window_size=10, alert_threshold=3)
        
        # Record diagnostics after each run
        monitor.record_diagnostics(
            series_name="CES0000000001",
            diagnostics={"m7": 0.45, "m8": 0.50, "q_statistic": 0.42},
            timestamp=datetime.now()
        )
        
        # Check for degradation
        result = monitor.check_for_degradation("CES0000000001", generate_alert=True)
        if result["degraded"]:
            logger.warning(f"Quality degradation detected: {result['message']}")
    """
    
    # Default thresholds based on Census Bureau guidelines
    DEFAULT_THRESHOLDS = {
        "m1": 1.0,
        "m2": 1.0,
        "m3": 1.0,
        "m4": 1.0,
        "m5": 1.0,
        "m6": 1.0,
        "m7": 1.0,   # Combined seasonality test
        "m8": 1.0,   # Closeness of annual totals
        "m9": 1.0,   # Stability of seasonal factors
        "m10": 1.0,  # Recent movements
        "m11": 1.0,  # Linear trend
        "q_statistic": 1.0,  # Overall quality < 1.0 = acceptable
    }
    
    # Quality grade thresholds
    GRADE_THRESHOLDS = {
        "good": 0.50,       # All stats < 0.50
        "acceptable": 1.0,  # All stats < 1.0
        # Above 1.0 = poor
    }
    
    def __init__(
        self,
        window_size: int = 10,
        alert_threshold: int = 3,
        thresholds: Optional[Dict[str, float]] = None
    ):
        """
        Initialize quality monitor.
        
        Args:
            window_size: Number of historical runs to keep (default: 10)
            alert_threshold: Number of consecutive increases to trigger alert (default: 3)
            thresholds: Custom thresholds for each statistic (default: Census Bureau guidelines)
        """
        self.window_size = window_size
        self.alert_threshold = alert_threshold
        self.thresholds = thresholds or self.DEFAULT_THRESHOLDS.copy()
        
        # Store history per series: {series_name: deque of entries}
        self._history: Dict[str, deque] = defaultdict(lambda: deque(maxlen=self.window_size))
        
        logger.info(
            f"QualityMonitor initialized",
            window_size=window_size,
            alert_threshold=alert_threshold
        )
    
    def record_diagnostics(
        self,
        series_name: str,
        diagnostics: Dict[str, float],
        timestamp: Optional[datetime] = None
    ) -> None:
        """
        Record diagnostics for a series.
        
        Args:
            series_name: Name of the time series (e.g., "CES0000000001")
            diagnostics: Dictionary of M/Q statistics
            timestamp: When diagnostics were computed (default: now)
        """
        if timestamp is None:
            timestamp = datetime.now()
        
        entry = {
            "series_name": series_name,
            "timestamp": timestamp,
            "diagnostics": diagnostics.copy()
        }
        
        self._history[series_name].append(entry)
        
        logger.debug(
            f"Recorded diagnostics for {series_name}",
            series_name=series_name,
            timestamp=timestamp.isoformat(),
            num_stats=len(diagnostics)
        )
    
    def get_history(self, series_name: str) -> List[Dict[str, Any]]:
        """
        Get historical diagnostics for a series.
        
        Args:
            series_name: Name of the time series
            
        Returns:
            List of historical entries (most recent last)
        """
        return list(self._history[series_name])
    
    def check_for_degradation(
        self,
        series_name: str,
        generate_alert: bool = False
    ) -> Dict[str, Any]:
        """
        Check for quality degradation in a series.
        
        Degradation is detected when:
        1. Any statistic exceeds its threshold (absolute)
        2. Consecutive increases in statistics (trend)
        
        Args:
            series_name: Name of the time series
            generate_alert: Whether to generate structured log alert
            
        Returns:
            Dictionary with degradation status and details:
            {
                "degraded": bool,
                "message": str,
                "threshold_breached": bool,
                "breached_stats": List[str],
                "consecutive_increases": int,
                "degraded_stats": List[str],
                "alert_generated": bool,
                "alert": Optional[Dict]
            }
        """
        history = self.get_history(series_name)
        
        if len(history) == 0:
            return {
                "degraded": False,
                "message": "No history available",
                "alert_generated": False
            }
        
        result = {
            "degraded": False,
            "message": "No degradation detected",
            "threshold_breached": False,
            "breached_stats": [],
            "consecutive_increases": 0,
            "degraded_stats": [],
            "alert_generated": False,
            "alert": None
        }
        
        latest_diagnostics = history[-1]["diagnostics"]
        
        # Check 1: Absolute threshold breaches
        breached_stats = []
        for stat_name, stat_value in latest_diagnostics.items():
            if stat_name in self.thresholds:
                threshold = self.thresholds[stat_name]
                if stat_value > threshold:
                    breached_stats.append(stat_name)
        
        if breached_stats:
            result["degraded"] = True
            result["threshold_breached"] = True
            result["breached_stats"] = breached_stats
            result["message"] = f"Threshold breach detected: {', '.join(breached_stats)}"
        
        # Check 2: Consecutive increases (trend detection)
        if len(history) >= 2:
            degraded_stats = []
            max_consecutive = 0
            
            for stat_name in latest_diagnostics.keys():
                if stat_name.startswith('m') or stat_name == 'q_statistic':
                    consecutive = self._count_consecutive_increases(history, stat_name)
                    
                    if consecutive >= self.alert_threshold:
                        degraded_stats.append(stat_name)
                        max_consecutive = max(max_consecutive, consecutive)
            
            if degraded_stats:
                result["degraded"] = True
                result["consecutive_increases"] = max_consecutive
                result["degraded_stats"] = degraded_stats
                
                if result["threshold_breached"]:
                    result["message"] += f" AND increasing trend detected: {', '.join(degraded_stats)}"
                else:
                    result["message"] = f"Increasing trend detected: {', '.join(degraded_stats)} ({max_consecutive} consecutive increases)"
        
        # Generate alert if requested and degradation detected
        if generate_alert and result["degraded"]:
            alert = self._generate_alert(series_name, result, history)
            result["alert"] = alert
            result["alert_generated"] = True
            
            # Log structured warning
            logger.warning(
                f"QUALITY DEGRADATION: {series_name}",
                series_name=series_name,
                degraded=True,
                threshold_breached=result["threshold_breached"],
                breached_stats=result["breached_stats"],
                consecutive_increases=result["consecutive_increases"],
                degraded_stats=result["degraded_stats"],
                message=result["message"],
                timestamp=datetime.now().isoformat()
            )
        
        return result
    
    def _count_consecutive_increases(
        self,
        history: List[Dict[str, Any]],
        stat_name: str
    ) -> int:
        """
        Count consecutive increases in a statistic.
        
        Args:
            history: Historical entries
            stat_name: Name of statistic to check
            
        Returns:
            Number of consecutive increases
        """
        if len(history) < 2:
            return 0
        
        consecutive = 0
        
        for i in range(1, len(history)):
            prev_val = history[i-1]["diagnostics"].get(stat_name)
            curr_val = history[i]["diagnostics"].get(stat_name)
            
            if prev_val is not None and curr_val is not None:
                if curr_val > prev_val:
                    consecutive += 1
                else:
                    consecutive = 0  # Reset if not increasing
        
        return consecutive
    
    def _generate_alert(
        self,
        series_name: str,
        result: Dict[str, Any],
        history: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Generate structured alert for ops monitoring.
        
        Args:
            series_name: Name of the series
            result: Degradation check result
            history: Historical entries
            
        Returns:
            Structured alert dictionary
        """
        latest = history[-1]
        
        alert = {
            "alert_type": "quality_degradation",
            "series_name": series_name,
            "timestamp": datetime.now().isoformat(),
            "severity": "warning",
            "degraded_stats": result.get("degraded_stats", []),
            "breached_stats": result.get("breached_stats", []),
            "consecutive_increases": result.get("consecutive_increases", 0),
            "latest_diagnostics": latest["diagnostics"],
            "message": result["message"],
            "action": "Review seasonal adjustment spec and data quality"
        }
        
        # Add trend information if available
        if len(history) >= 2:
            alert["trend"] = {}
            for stat_name in result.get("degraded_stats", []):
                values = [
                    entry["diagnostics"].get(stat_name)
                    for entry in history
                    if stat_name in entry["diagnostics"]
                ]
                if values:
                    alert["trend"][stat_name] = {
                        "first": values[0],
                        "latest": values[-1],
                        "change": values[-1] - values[0],
                        "change_pct": ((values[-1] - values[0]) / values[0] * 100) if values[0] != 0 else 0
                    }
        
        return alert
    
    def calculate_quality_score(self, diagnostics: Dict[str, float]) -> float:
        """
        Calculate overall quality score (0-100, higher = better).
        
        Quality score is calculated as:
        - 100 points starting
        - Deduct points based on how close stats are to thresholds
        - M7, M8, Q-statistic weighted more heavily
        
        Args:
            diagnostics: Dictionary of M/Q statistics
            
        Returns:
            Quality score (0-100)
        """
        if not diagnostics:
            return 0.0
        
        # Weight critical statistics more heavily
        weights = {
            "m7": 2.0,   # Combined seasonality test
            "m8": 2.0,   # Closeness of annual totals
            "m9": 1.5,   # Stability
            "q_statistic": 2.0,  # Overall quality
        }
        
        total_penalty = 0.0
        total_weight = 0.0
        
        for stat_name, stat_value in diagnostics.items():
            if stat_name in self.thresholds:
                threshold = self.thresholds[stat_name]
                weight = weights.get(stat_name, 1.0)
                
                # Penalty increases as stat approaches/exceeds threshold
                # 0.0 → no penalty, 1.0 → full penalty, >1.0 → over penalty
                penalty_factor = stat_value / threshold if threshold > 0 else 0
                penalty = min(penalty_factor, 1.5) * weight  # Cap at 1.5x
                
                total_penalty += penalty
                total_weight += weight
        
        if total_weight == 0:
            return 100.0
        
        # Calculate score: 100 - (average penalty * 100)
        avg_penalty = total_penalty / total_weight
        score = max(0.0, 100.0 - (avg_penalty * 100))
        
        return score
    
    def assess_quality_grade(self, diagnostics: Dict[str, float]) -> str:
        """
        Assess overall quality grade.
        
        Args:
            diagnostics: Dictionary of M/Q statistics
            
        Returns:
            Quality grade: "good", "acceptable", or "poor"
        """
        if not diagnostics:
            return "unknown"
        
        # Check maximum statistic value
        max_stat = 0.0
        for stat_name, stat_value in diagnostics.items():
            if stat_name.startswith('m') or stat_name == 'q_statistic':
                max_stat = max(max_stat, stat_value)
        
        if max_stat < self.GRADE_THRESHOLDS["good"]:
            return "good"
        elif max_stat < self.GRADE_THRESHOLDS["acceptable"]:
            return "acceptable"
        else:
            return "poor"
    
    def export_history(self, series_name: str) -> List[Dict[str, Any]]:
        """
        Export history in database-compatible format.
        
        Args:
            series_name: Name of the series
            
        Returns:
            List of entries ready for database storage
        """
        history = self.get_history(series_name)
        
        # Convert datetime objects to ISO format strings for database compatibility
        export = []
        for entry in history:
            export_entry = {
                "series_name": entry["series_name"],
                "timestamp": entry["timestamp"].isoformat() if isinstance(entry["timestamp"], datetime) else entry["timestamp"],
                "diagnostics": entry["diagnostics"]
            }
            export.append(export_entry)
        
        return export
    
    def get_summary(self, series_name: str) -> Dict[str, Any]:
        """
        Get summary statistics for a series.
        
        Args:
            series_name: Name of the series
            
        Returns:
            Summary with recent trends and quality assessment
        """
        history = self.get_history(series_name)
        
        if not history:
            return {
                "series_name": series_name,
                "num_entries": 0,
                "status": "no_data"
            }
        
        latest = history[-1]
        latest_diagnostics = latest["diagnostics"]
        
        summary = {
            "series_name": series_name,
            "num_entries": len(history),
            "latest_timestamp": latest["timestamp"].isoformat() if isinstance(latest["timestamp"], datetime) else latest["timestamp"],
            "latest_diagnostics": latest_diagnostics,
            "quality_score": self.calculate_quality_score(latest_diagnostics),
            "quality_grade": self.assess_quality_grade(latest_diagnostics),
        }
        
        # Add degradation check
        degradation = self.check_for_degradation(series_name, generate_alert=False)
        summary["degradation_detected"] = degradation["degraded"]
        summary["degradation_details"] = {
            "threshold_breached": degradation.get("threshold_breached", False),
            "breached_stats": degradation.get("breached_stats", []),
            "consecutive_increases": degradation.get("consecutive_increases", 0),
            "degraded_stats": degradation.get("degraded_stats", [])
        }
        
        return summary
    
    def get_all_series(self) -> List[str]:
        """
        Get list of all monitored series.
        
        Returns:
            List of series names
        """
        return list(self._history.keys())
    
    def clear_history(self, series_name: Optional[str] = None) -> None:
        """
        Clear history for a series or all series.
        
        Args:
            series_name: Series to clear (None = clear all)
        """
        if series_name:
            if series_name in self._history:
                self._history[series_name].clear()
                logger.info(f"Cleared history for {series_name}")
        else:
            self._history.clear()
            logger.info("Cleared all history")


def create_monitor(
    window_size: int = 10,
    alert_threshold: int = 3
) -> QualityMonitor:
    """
    Convenience function to create a quality monitor.
    
    Args:
        window_size: Number of historical runs to keep
        alert_threshold: Number of consecutive increases to trigger alert
        
    Returns:
        Configured QualityMonitor instance
    """
    return QualityMonitor(
        window_size=window_size,
        alert_threshold=alert_threshold
    )

