"""
Tests for Quality Degradation Monitor

Tests monitoring of M/Q statistics over time, trend detection, and alert generation.
Validates Phase 5.11.4: Quality Degradation Alerts
"""

import pytest
from datetime import datetime, timedelta
from typing import Dict, List, Any
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent.parent))


class TestQualityMonitorBasics:
    """Test basic quality monitor functionality"""
    
    def test_quality_monitor_initialization(self):
        """Test that quality monitor can be initialized"""
        from seasonal.diagnostics.quality_monitor import QualityMonitor
        
        monitor = QualityMonitor()
        
        assert monitor is not None
        assert hasattr(monitor, 'record_diagnostics')
        assert hasattr(monitor, 'check_for_degradation')
    
    def test_quality_monitor_with_window_size(self):
        """Test that monitor accepts window size parameter"""
        from seasonal.diagnostics.quality_monitor import QualityMonitor
        
        monitor = QualityMonitor(window_size=10)
        
        assert monitor.window_size == 10
    
    def test_quality_monitor_with_alert_threshold(self):
        """Test that monitor accepts alert threshold parameter"""
        from seasonal.diagnostics.quality_monitor import QualityMonitor
        
        monitor = QualityMonitor(alert_threshold=3)
        
        assert monitor.alert_threshold == 3
    
    def test_record_single_diagnostic(self):
        """Test recording a single diagnostic entry"""
        from seasonal.diagnostics.quality_monitor import QualityMonitor
        
        monitor = QualityMonitor()
        
        diagnostics = {
            "m1": 0.25,
            "m2": 0.28,
            "m7": 0.45,
            "m8": 0.50,
            "q_statistic": 0.42
        }
        
        monitor.record_diagnostics(
            series_name="TEST_SERIES",
            diagnostics=diagnostics,
            timestamp=datetime(2024, 1, 1)
        )
        
        history = monitor.get_history("TEST_SERIES")
        assert len(history) == 1
        assert history[0]["diagnostics"]["m7"] == 0.45
    
    def test_record_multiple_diagnostics(self):
        """Test recording multiple diagnostic entries over time"""
        from seasonal.diagnostics.quality_monitor import QualityMonitor
        
        monitor = QualityMonitor()
        
        # Record 5 runs
        for i in range(5):
            diagnostics = {
                "m7": 0.45 + (i * 0.01),  # Slight increase each time
                "m8": 0.50 + (i * 0.01),
                "q_statistic": 0.42 + (i * 0.01)
            }
            
            monitor.record_diagnostics(
                series_name="TEST_SERIES",
                diagnostics=diagnostics,
                timestamp=datetime(2024, 1, 1) + timedelta(days=i)
            )
        
        history = monitor.get_history("TEST_SERIES")
        assert len(history) == 5
        assert history[0]["diagnostics"]["m7"] == 0.45  # First
        assert history[4]["diagnostics"]["m7"] == 0.49  # Fifth
    
    def test_window_size_limits_history(self):
        """Test that window size limits stored history"""
        from seasonal.diagnostics.quality_monitor import QualityMonitor
        
        monitor = QualityMonitor(window_size=3)
        
        # Record 5 entries (more than window size)
        for i in range(5):
            monitor.record_diagnostics(
                series_name="TEST_SERIES",
                diagnostics={"m7": 0.40 + i * 0.05},
                timestamp=datetime(2024, 1, 1) + timedelta(days=i)
            )
        
        history = monitor.get_history("TEST_SERIES")
        
        # Should only keep last 3
        assert len(history) == 3
        assert history[0]["diagnostics"]["m7"] == 0.50  # Entry 2 (oldest kept)
        assert history[2]["diagnostics"]["m7"] == 0.60  # Entry 4 (newest)


class TestDegradationTrendDetection:
    """Test degradation trend detection"""
    
    def test_detect_no_degradation_stable_stats(self):
        """Test that stable statistics show no degradation"""
        from seasonal.diagnostics.quality_monitor import QualityMonitor
        
        monitor = QualityMonitor()
        
        # Record stable statistics (no change)
        for i in range(5):
            monitor.record_diagnostics(
                series_name="TEST_SERIES",
                diagnostics={
                    "m7": 0.45,  # Stable
                    "m8": 0.50,  # Stable
                    "q_statistic": 0.42
                },
                timestamp=datetime(2024, 1, 1) + timedelta(days=i)
            )
        
        result = monitor.check_for_degradation("TEST_SERIES")
        
        assert result["degraded"] is False
        assert result["message"] == "No degradation detected"
    
    def test_detect_degradation_increasing_trend(self):
        """Test detection of increasing trend (degradation)"""
        from seasonal.diagnostics.quality_monitor import QualityMonitor
        
        monitor = QualityMonitor(alert_threshold=3)
        
        # Record increasing M7 (degradation)
        for i in range(5):
            monitor.record_diagnostics(
                series_name="TEST_SERIES",
                diagnostics={
                    "m7": 0.40 + (i * 0.10),  # 0.40 → 0.80 (degrading)
                    "m8": 0.50,
                    "q_statistic": 0.45
                },
                timestamp=datetime(2024, 1, 1) + timedelta(days=i)
            )
        
        result = monitor.check_for_degradation("TEST_SERIES")
        
        assert result["degraded"] is True
        assert "M7" in result["message"] or "degradation" in result["message"].lower()
    
    def test_detect_consecutive_increases(self):
        """Test detection of consecutive increases"""
        from seasonal.diagnostics.quality_monitor import QualityMonitor
        
        monitor = QualityMonitor(alert_threshold=3)  # Alert after 3 consecutive increases
        
        # Record 3 consecutive increases
        values = [0.40, 0.45, 0.50, 0.55]
        for i, val in enumerate(values):
            monitor.record_diagnostics(
                series_name="TEST_SERIES",
                diagnostics={"m7": val},
                timestamp=datetime(2024, 1, 1) + timedelta(days=i)
            )
        
        result = monitor.check_for_degradation("TEST_SERIES")
        
        # Should detect 3 consecutive increases (0.40→0.45→0.50→0.55)
        assert result["degraded"] is True
        assert result["consecutive_increases"] >= 3
    
    def test_no_alert_for_improvement_trend(self):
        """Test that improving statistics don't trigger alerts"""
        from seasonal.diagnostics.quality_monitor import QualityMonitor
        
        monitor = QualityMonitor()
        
        # Record decreasing M7 (improvement)
        for i in range(5):
            monitor.record_diagnostics(
                series_name="TEST_SERIES",
                diagnostics={
                    "m7": 0.80 - (i * 0.10),  # 0.80 → 0.40 (improving)
                },
                timestamp=datetime(2024, 1, 1) + timedelta(days=i)
            )
        
        result = monitor.check_for_degradation("TEST_SERIES")
        
        assert result["degraded"] is False
    
    def test_detect_threshold_breach(self):
        """Test detection of absolute threshold breach"""
        from seasonal.diagnostics.quality_monitor import QualityMonitor
        
        monitor = QualityMonitor(
            thresholds={
                "m7": 1.0,
                "m8": 1.0,
                "q_statistic": 1.0
            }
        )
        
        # Record stat exceeding threshold
        monitor.record_diagnostics(
            series_name="TEST_SERIES",
            diagnostics={
                "m7": 1.2,  # Exceeds threshold of 1.0
                "m8": 0.5,
                "q_statistic": 0.4
            },
            timestamp=datetime(2024, 1, 1)
        )
        
        result = monitor.check_for_degradation("TEST_SERIES")
        
        assert result["degraded"] is True
        assert result["threshold_breached"] is True
        assert "M7" in str(result.get("breached_stats", []))
    
    def test_detect_multiple_stat_degradation(self):
        """Test detection when multiple statistics degrade"""
        from seasonal.diagnostics.quality_monitor import QualityMonitor
        
        monitor = QualityMonitor(alert_threshold=2)
        
        # Record degradation in both M7 and M8
        for i in range(3):
            monitor.record_diagnostics(
                series_name="TEST_SERIES",
                diagnostics={
                    "m7": 0.40 + (i * 0.15),  # Degrading
                    "m8": 0.45 + (i * 0.15),  # Degrading
                    "q_statistic": 0.40 + (i * 0.10)
                },
                timestamp=datetime(2024, 1, 1) + timedelta(days=i)
            )
        
        result = monitor.check_for_degradation("TEST_SERIES")
        
        assert result["degraded"] is True
        degraded_stats = result.get("degraded_stats", [])
        assert len(degraded_stats) >= 2  # Both M7 and M8


class TestAlertGeneration:
    """Test alert generation and logging"""
    
    def test_generate_alert_on_degradation(self, caplog):
        """Test that alerts are generated when degradation detected"""
        from seasonal.diagnostics.quality_monitor import QualityMonitor
        import logging
        
        caplog.set_level(logging.WARNING)
        
        monitor = QualityMonitor(alert_threshold=2)
        
        # Create degradation scenario
        for i in range(3):
            monitor.record_diagnostics(
                series_name="TEST_SERIES",
                diagnostics={"m7": 0.40 + (i * 0.20)},
                timestamp=datetime(2024, 1, 1) + timedelta(days=i)
            )
        
        # Check for degradation (should generate alert)
        result = monitor.check_for_degradation("TEST_SERIES", generate_alert=True)
        
        assert result["degraded"] is True
        assert result["alert_generated"] is True
        
        # Check that warning was logged
        assert any("degradation" in record.message.lower() for record in caplog.records)
    
    def test_alert_contains_details(self, caplog):
        """Test that alerts contain detailed information"""
        from seasonal.diagnostics.quality_monitor import QualityMonitor
        import logging
        
        caplog.set_level(logging.WARNING)
        
        monitor = QualityMonitor(alert_threshold=2)
        
        # Create degradation
        for i in range(3):
            monitor.record_diagnostics(
                series_name="IMPORTANT_SERIES",
                diagnostics={"m7": 0.50 + (i * 0.15)},
                timestamp=datetime(2024, 1, 1) + timedelta(days=i)
            )
        
        result = monitor.check_for_degradation("IMPORTANT_SERIES", generate_alert=True)
        
        # Check alert details
        alert = result.get("alert", {})
        assert "series_name" in alert
        assert alert["series_name"] == "IMPORTANT_SERIES"
        assert "degraded_stats" in alert
        assert "timestamp" in alert
    
    def test_no_alert_when_disabled(self, caplog):
        """Test that no alert generated when generate_alert=False"""
        from seasonal.diagnostics.quality_monitor import QualityMonitor
        import logging
        
        caplog.set_level(logging.WARNING)
        
        monitor = QualityMonitor(alert_threshold=2)
        
        # Create degradation
        for i in range(3):
            monitor.record_diagnostics(
                series_name="TEST_SERIES",
                diagnostics={"m7": 0.40 + (i * 0.20)},
                timestamp=datetime(2024, 1, 1) + timedelta(days=i)
            )
        
        result = monitor.check_for_degradation("TEST_SERIES", generate_alert=False)
        
        assert result["degraded"] is True
        assert result.get("alert_generated", False) is False
    
    def test_structured_logging_format(self, caplog):
        """Test that alerts use structured logging format"""
        from seasonal.diagnostics.quality_monitor import QualityMonitor
        import logging
        
        caplog.set_level(logging.WARNING)
        
        monitor = QualityMonitor()
        
        # Create threshold breach
        monitor.record_diagnostics(
            series_name="TEST_SERIES",
            diagnostics={"m7": 1.5},  # High value
            timestamp=datetime(2024, 1, 1)
        )
        
        monitor.check_for_degradation("TEST_SERIES", generate_alert=True)
        
        # Check for structured log (should contain key=value pairs or JSON-like structure)
        assert len(caplog.records) > 0


class TestQualityScoring:
    """Test quality scoring and assessment"""
    
    def test_calculate_quality_score(self):
        """Test quality score calculation"""
        from seasonal.diagnostics.quality_monitor import QualityMonitor
        
        monitor = QualityMonitor()
        
        diagnostics = {
            "m7": 0.45,
            "m8": 0.50,
            "q_statistic": 0.42
        }
        
        score = monitor.calculate_quality_score(diagnostics)
        
        assert score is not None
        assert 0 <= score <= 100  # Score should be normalized 0-100
    
    def test_quality_score_decreases_with_degradation(self):
        """Test that quality score decreases as statistics degrade"""
        from seasonal.diagnostics.quality_monitor import QualityMonitor
        
        monitor = QualityMonitor()
        
        good_diagnostics = {
            "m7": 0.30,
            "m8": 0.35,
            "q_statistic": 0.25
        }
        
        poor_diagnostics = {
            "m7": 0.85,
            "m8": 0.90,
            "q_statistic": 0.95
        }
        
        good_score = monitor.calculate_quality_score(good_diagnostics)
        poor_score = monitor.calculate_quality_score(poor_diagnostics)
        
        assert good_score > poor_score, "Good diagnostics should have higher score"
    
    def test_assess_quality_grade(self):
        """Test quality grade assessment"""
        from seasonal.diagnostics.quality_monitor import QualityMonitor
        
        monitor = QualityMonitor()
        
        good_diagnostics = {"m7": 0.30, "m8": 0.35, "q_statistic": 0.25}
        acceptable_diagnostics = {"m7": 0.60, "m8": 0.65, "q_statistic": 0.55}
        poor_diagnostics = {"m7": 0.95, "m8": 0.98, "q_statistic": 0.92}
        
        assert monitor.assess_quality_grade(good_diagnostics) == "good"
        assert monitor.assess_quality_grade(acceptable_diagnostics) == "acceptable"
        assert monitor.assess_quality_grade(poor_diagnostics) == "poor"


class TestMultipleSeriesMonitoring:
    """Test monitoring multiple series simultaneously"""
    
    def test_monitor_multiple_series(self):
        """Test monitoring multiple series independently"""
        from seasonal.diagnostics.quality_monitor import QualityMonitor
        
        monitor = QualityMonitor()
        
        # Record for series 1
        monitor.record_diagnostics(
            series_name="SERIES_1",
            diagnostics={"m7": 0.40},
            timestamp=datetime(2024, 1, 1)
        )
        
        # Record for series 2
        monitor.record_diagnostics(
            series_name="SERIES_2",
            diagnostics={"m7": 0.50},
            timestamp=datetime(2024, 1, 1)
        )
        
        history_1 = monitor.get_history("SERIES_1")
        history_2 = monitor.get_history("SERIES_2")
        
        assert len(history_1) == 1
        assert len(history_2) == 1
        assert history_1[0]["diagnostics"]["m7"] == 0.40
        assert history_2[0]["diagnostics"]["m7"] == 0.50
    
    def test_degradation_detection_per_series(self):
        """Test that degradation is detected independently per series"""
        from seasonal.diagnostics.quality_monitor import QualityMonitor
        
        monitor = QualityMonitor(alert_threshold=2)
        
        # Series 1: Degrading
        for i in range(3):
            monitor.record_diagnostics(
                series_name="DEGRADING_SERIES",
                diagnostics={"m7": 0.40 + (i * 0.20)},
                timestamp=datetime(2024, 1, 1) + timedelta(days=i)
            )
        
        # Series 2: Stable
        for i in range(3):
            monitor.record_diagnostics(
                series_name="STABLE_SERIES",
                diagnostics={"m7": 0.45},
                timestamp=datetime(2024, 1, 1) + timedelta(days=i)
            )
        
        degrading_result = monitor.check_for_degradation("DEGRADING_SERIES")
        stable_result = monitor.check_for_degradation("STABLE_SERIES")
        
        assert degrading_result["degraded"] is True
        assert stable_result["degraded"] is False


class TestDatabaseIntegration:
    """Test database storage integration (prepared for Phase 10)"""
    
    def test_diagnostics_storage_structure(self):
        """Test that diagnostics have database-compatible structure"""
        from seasonal.diagnostics.quality_monitor import QualityMonitor
        
        monitor = QualityMonitor()
        
        monitor.record_diagnostics(
            series_name="TEST_SERIES",
            diagnostics={"m7": 0.45, "m8": 0.50},
            timestamp=datetime(2024, 1, 1)
        )
        
        history = monitor.get_history("TEST_SERIES")
        entry = history[0]
        
        # Check structure is database-compatible
        assert "series_name" in entry
        assert "timestamp" in entry
        assert "diagnostics" in entry
        assert isinstance(entry["timestamp"], datetime)
        assert isinstance(entry["diagnostics"], dict)
    
    def test_export_to_database_format(self):
        """Test exporting history to database-compatible format"""
        from seasonal.diagnostics.quality_monitor import QualityMonitor
        
        monitor = QualityMonitor()
        
        for i in range(3):
            monitor.record_diagnostics(
                series_name="TEST_SERIES",
                diagnostics={"m7": 0.40 + i * 0.05},
                timestamp=datetime(2024, 1, 1) + timedelta(days=i)
            )
        
        # Should be able to export for database storage
        export = monitor.export_history("TEST_SERIES")
        
        assert isinstance(export, list)
        assert len(export) == 3
        assert all("series_name" in entry for entry in export)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])

