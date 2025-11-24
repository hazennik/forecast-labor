"""
Standalone Test for Quality Monitor

Demonstrates quality monitoring functionality without requiring full pipeline.
Validates Phase 5.11.4: Quality Degradation Alerts
"""

import sys
from pathlib import Path
from datetime import datetime, timedelta

sys.path.insert(0, str(Path(__file__).parent.parent))

from seasonal.diagnostics.quality_monitor import QualityMonitor


def test_basic_monitoring():
    """Test basic quality monitoring"""
    print("\n" + "="*70)
    print("TEST 1: Basic Quality Monitoring")
    print("="*70)
    
    monitor = QualityMonitor(window_size=5, alert_threshold=3)
    
    # Record stable diagnostics
    print("\nRecording 3 stable runs...")
    for i in range(3):
        monitor.record_diagnostics(
            series_name="TEST_SERIES",
            diagnostics={
                "m7": 0.45,
                "m8": 0.50,
                "q_statistic": 0.42
            },
            timestamp=datetime(2024, 1, 1) + timedelta(days=i)
        )
    
    print(f"History entries: {len(monitor.get_history('TEST_SERIES'))}")
    
    result = monitor.check_for_degradation("TEST_SERIES")
    print(f"Degradation detected: {result['degraded']}")
    print(f"Message: {result['message']}")
    
    assert result["degraded"] is False, "Stable stats should not show degradation"
    print("✅ PASSED: No degradation for stable statistics")


def test_degradation_detection():
    """Test degradation detection with increasing trend"""
    print("\n" + "="*70)
    print("TEST 2: Degradation Detection (Increasing Trend)")
    print("="*70)
    
    monitor = QualityMonitor(window_size=10, alert_threshold=3)
    
    # Record increasing M7 (degradation)
    print("\nRecording 5 runs with increasing M7...")
    for i in range(5):
        m7_value = 0.40 + (i * 0.10)
        print(f"  Run {i+1}: M7 = {m7_value:.2f}")
        
        monitor.record_diagnostics(
            series_name="DEGRADING_SERIES",
            diagnostics={
                "m7": m7_value,
                "m8": 0.50,
                "q_statistic": 0.45
            },
            timestamp=datetime(2024, 1, 1) + timedelta(days=i)
        )
    
    result = monitor.check_for_degradation("DEGRADING_SERIES", generate_alert=False)
    print(f"\nDegradation detected: {result['degraded']}")
    print(f"Consecutive increases: {result['consecutive_increases']}")
    print(f"Degraded stats: {result['degraded_stats']}")
    print(f"Message: {result['message']}")
    
    assert result["degraded"] is True, "Should detect degradation"
    assert result["consecutive_increases"] >= 3, "Should detect 3+ consecutive increases"
    print("✅ PASSED: Degradation detected successfully")


def test_threshold_breach():
    """Test absolute threshold breach detection"""
    print("\n" + "="*70)
    print("TEST 3: Threshold Breach Detection")
    print("="*70)
    
    monitor = QualityMonitor()
    
    # Record stats exceeding threshold
    print("\nRecording run with M7 = 1.2 (threshold = 1.0)...")
    monitor.record_diagnostics(
        series_name="BREACH_SERIES",
        diagnostics={
            "m7": 1.2,  # Exceeds threshold of 1.0
            "m8": 0.5,
            "q_statistic": 0.4
        },
        timestamp=datetime(2024, 1, 1)
    )
    
    result = monitor.check_for_degradation("BREACH_SERIES")
    print(f"\nThreshold breached: {result['threshold_breached']}")
    print(f"Breached stats: {result['breached_stats']}")
    print(f"Message: {result['message']}")
    
    assert result["threshold_breached"] is True, "Should detect threshold breach"
    assert "m7" in result["breached_stats"], "M7 should be in breached stats"
    print("✅ PASSED: Threshold breach detected successfully")


def test_alert_generation():
    """Test alert generation with structured logging"""
    print("\n" + "="*70)
    print("TEST 4: Alert Generation")
    print("="*70)
    
    monitor = QualityMonitor(alert_threshold=2)
    
    # Create degradation scenario
    print("\nRecording 3 runs with degradation...")
    for i in range(3):
        monitor.record_diagnostics(
            series_name="ALERT_SERIES",
            diagnostics={"m7": 0.40 + (i * 0.20)},
            timestamp=datetime(2024, 1, 1) + timedelta(days=i)
        )
    
    result = monitor.check_for_degradation("ALERT_SERIES", generate_alert=True)
    
    print(f"\nAlert generated: {result['alert_generated']}")
    if result['alert']:
        print(f"Alert type: {result['alert']['alert_type']}")
        print(f"Severity: {result['alert']['severity']}")
        print(f"Message: {result['alert']['message']}")
        print(f"Action: {result['alert']['action']}")
        
        if 'trend' in result['alert']:
            print(f"\nTrend analysis:")
            for stat, trend in result['alert']['trend'].items():
                print(f"  {stat}: {trend['first']:.3f} → {trend['latest']:.3f} (change: {trend['change_pct']:.1f}%)")
    
    assert result["alert_generated"] is True, "Alert should be generated"
    assert result["alert"] is not None, "Alert object should exist"
    print("✅ PASSED: Alert generated successfully")


def test_quality_scoring():
    """Test quality score calculation"""
    print("\n" + "="*70)
    print("TEST 5: Quality Scoring")
    print("="*70)
    
    monitor = QualityMonitor()
    
    good_diagnostics = {
        "m7": 0.30,
        "m8": 0.35,
        "q_statistic": 0.25
    }
    
    acceptable_diagnostics = {
        "m7": 0.60,
        "m8": 0.65,
        "q_statistic": 0.55
    }
    
    poor_diagnostics = {
        "m7": 0.95,
        "m8": 0.98,
        "q_statistic": 0.92
    }
    
    good_score = monitor.calculate_quality_score(good_diagnostics)
    good_grade = monitor.assess_quality_grade(good_diagnostics)
    
    acceptable_score = monitor.calculate_quality_score(acceptable_diagnostics)
    acceptable_grade = monitor.assess_quality_grade(acceptable_diagnostics)
    
    poor_score = monitor.calculate_quality_score(poor_diagnostics)
    poor_grade = monitor.assess_quality_grade(poor_diagnostics)
    
    print(f"\nGood diagnostics:")
    print(f"  Score: {good_score:.1f}/100")
    print(f"  Grade: {good_grade}")
    
    print(f"\nAcceptable diagnostics:")
    print(f"  Score: {acceptable_score:.1f}/100")
    print(f"  Grade: {acceptable_grade}")
    
    print(f"\nPoor diagnostics:")
    print(f"  Score: {poor_score:.1f}/100")
    print(f"  Grade: {poor_grade}")
    
    assert good_score > acceptable_score > poor_score, "Scores should decrease with quality"
    assert good_grade == "good", "Should be graded as good"
    assert acceptable_grade == "acceptable", "Should be graded as acceptable"
    assert poor_grade == "poor", "Should be graded as poor"
    print("✅ PASSED: Quality scoring working correctly")


def test_multiple_series():
    """Test monitoring multiple series independently"""
    print("\n" + "="*70)
    print("TEST 6: Multiple Series Monitoring")
    print("="*70)
    
    monitor = QualityMonitor(alert_threshold=2)
    
    # Series 1: Degrading
    print("\nSeries 1 (degrading):")
    for i in range(3):
        monitor.record_diagnostics(
            series_name="SERIES_1",
            diagnostics={"m7": 0.40 + (i * 0.20)},
            timestamp=datetime(2024, 1, 1) + timedelta(days=i)
        )
    
    # Series 2: Stable
    print("Series 2 (stable):")
    for i in range(3):
        monitor.record_diagnostics(
            series_name="SERIES_2",
            diagnostics={"m7": 0.45},
            timestamp=datetime(2024, 1, 1) + timedelta(days=i)
        )
    
    result1 = monitor.check_for_degradation("SERIES_1")
    result2 = monitor.check_for_degradation("SERIES_2")
    
    print(f"\nSeries 1 degraded: {result1['degraded']}")
    print(f"Series 2 degraded: {result2['degraded']}")
    
    assert result1["degraded"] is True, "Series 1 should show degradation"
    assert result2["degraded"] is False, "Series 2 should be stable"
    print("✅ PASSED: Multiple series monitored independently")


def test_summary_report():
    """Test summary reporting"""
    print("\n" + "="*70)
    print("TEST 7: Summary Report")
    print("="*70)
    
    monitor = QualityMonitor()
    
    # Record some diagnostics
    for i in range(3):
        monitor.record_diagnostics(
            series_name="SUMMARY_SERIES",
            diagnostics={
                "m7": 0.45 + (i * 0.05),
                "m8": 0.50,
                "q_statistic": 0.42
            },
            timestamp=datetime(2024, 1, 1) + timedelta(days=i)
        )
    
    summary = monitor.get_summary("SUMMARY_SERIES")
    
    print(f"\nSummary for SUMMARY_SERIES:")
    print(f"  Entries: {summary['num_entries']}")
    print(f"  Quality Score: {summary['quality_score']:.1f}/100")
    print(f"  Quality Grade: {summary['quality_grade']}")
    print(f"  Degradation Detected: {summary['degradation_detected']}")
    print(f"  Latest M7: {summary['latest_diagnostics']['m7']:.2f}")
    
    assert summary['num_entries'] == 3, "Should have 3 entries"
    assert 'quality_score' in summary, "Should include quality score"
    assert 'degradation_details' in summary, "Should include degradation details"
    print("✅ PASSED: Summary report generated successfully")


def main():
    """Run all tests"""
    print("\n" + "="*70)
    print("QUALITY MONITOR STANDALONE TESTS")
    print("Phase 5.11.4: Quality Degradation Alerts")
    print("="*70)
    
    tests = [
        test_basic_monitoring,
        test_degradation_detection,
        test_threshold_breach,
        test_alert_generation,
        test_quality_scoring,
        test_multiple_series,
        test_summary_report
    ]
    
    passed = 0
    failed = 0
    
    for test_func in tests:
        try:
            test_func()
            passed += 1
        except AssertionError as e:
            print(f"❌ FAILED: {e}")
            failed += 1
        except Exception as e:
            print(f"❌ ERROR: {e}")
            failed += 1
    
    print("\n" + "="*70)
    print("SUMMARY")
    print("="*70)
    print(f"Tests passed: {passed}/{len(tests)}")
    print(f"Tests failed: {failed}/{len(tests)}")
    
    if failed == 0:
        print("\n✅ ALL TESTS PASSED!")
        return 0
    else:
        print(f"\n❌ {failed} TEST(S) FAILED")
        return 1


if __name__ == "__main__":
    exit(main())

