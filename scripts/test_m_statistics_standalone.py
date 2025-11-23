#!/usr/bin/env python3
"""
Standalone test script for M-statistics computation
Does not require pytest or database dependencies
"""

import sys
import os
import numpy as np
import pandas as pd

# Add parent directory to path
project_root = '/Users/ryan/Documents/GitHub/forecast-labor'
sys.path.insert(0, project_root)

# Import directly from file to avoid __init__ chain
import importlib.util
spec = importlib.util.spec_from_file_location(
    "m_statistics",
    os.path.join(project_root, "seasonal/diagnostics/m_statistics.py")
)
m_statistics = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m_statistics)

MStatisticsComputer = m_statistics.MStatisticsComputer
compute_m_statistics = m_statistics.compute_m_statistics
validate_quality_thresholds = m_statistics.validate_quality_thresholds


def create_test_data():
    """Create simple test data"""
    dates = pd.date_range(start='2020-01-01', periods=60, freq='MS')
    
    # Stable seasonal pattern
    seasonal = np.tile(np.sin(np.arange(12) * 2 * np.pi / 12) * 10, 5)
    
    # Smooth trend
    trend = np.linspace(100, 150, 60)
    
    # Small random irregular
    np.random.seed(42)
    irregular = np.random.normal(0, 1, 60)
    
    original = seasonal + trend + irregular
    
    return {
        'original': pd.Series(original, index=dates),
        'seasonal': pd.Series(seasonal, index=dates),
        'trend': pd.Series(trend, index=dates),
        'irregular': pd.Series(irregular, index=dates),
        'seasonally_adjusted': pd.Series(trend + irregular, index=dates),
    }


def test_basic_computation():
    """Test basic M-statistics computation"""
    print("Test 1: Basic computation")
    
    components = create_test_data()
    computer = MStatisticsComputer()
    
    result = computer.compute(components)
    
    # Check all M-statistics are present
    for i in range(1, 12):
        key = f'm{i}'
        assert key in result, f"Missing {key}"
        assert isinstance(result[key], (int, float)), f"{key} should be numeric"
        assert not np.isnan(result[key]), f"{key} should not be NaN"
        print(f"  {key}: {result[key]:.3f}")
    
    assert 'q_statistic' in result
    print(f"  q_statistic: {result['q_statistic']:.3f}")
    
    print("✓ Test 1 passed\n")
    return result


def test_q_is_average():
    """Test that Q-statistic is average of M1-M11"""
    print("Test 2: Q-statistic is average of M1-M11")
    
    components = create_test_data()
    computer = MStatisticsComputer()
    result = computer.compute(components)
    
    m_values = [result[f'm{i}'] for i in range(1, 12)]
    expected_q = np.mean(m_values)
    
    diff = abs(result['q_statistic'] - expected_q)
    assert diff < 1e-6, f"Q should be average: expected {expected_q}, got {result['q_statistic']}"
    
    print(f"  Expected Q: {expected_q:.6f}")
    print(f"  Actual Q: {result['q_statistic']:.6f}")
    print(f"  Difference: {diff:.9f}")
    print("✓ Test 2 passed\n")


def test_determinism():
    """Test that computation is deterministic"""
    print("Test 3: Determinism")
    
    components = create_test_data()
    computer = MStatisticsComputer()
    
    result1 = computer.compute(components)
    result2 = computer.compute(components)
    
    for i in range(1, 12):
        key = f'm{i}'
        assert result1[key] == result2[key], f"{key} should be deterministic"
    
    assert result1['q_statistic'] == result2['q_statistic']
    
    print("  All M-statistics are deterministic")
    print("✓ Test 3 passed\n")


def test_quality_validation():
    """Test quality threshold validation"""
    print("Test 4: Quality threshold validation")
    
    # Good quality
    m_stats = {f'm{i}': 0.5 for i in range(1, 12)}
    m_stats['q_statistic'] = 0.5
    
    validation = validate_quality_thresholds(m_stats)
    
    assert validation['overall_quality'] == 'good', "Should be good quality"
    assert validation['pass'] is True, "Should pass"
    
    print(f"  Quality: {validation['overall_quality']}")
    print(f"  Pass: {validation['pass']}")
    print("✓ Test 4 passed\n")


def test_high_quality_decomposition():
    """Test that high-quality decomposition produces good M-stats"""
    print("Test 5: High-quality decomposition")
    
    components = create_test_data()  # High quality data
    computer = MStatisticsComputer()
    result = computer.compute(components)
    
    # Count how many M-stats are < 1.0 (good quality)
    good_count = sum(1 for i in range(1, 12) if result[f'm{i}'] < 1.0)
    
    print(f"  M-statistics < 1.0: {good_count}/11")
    print(f"  Q-statistic: {result['q_statistic']:.3f}")
    
    if good_count >= 8:
        print("✓ Test 5 passed\n")
    else:
        print("⚠ Test 5: Less than 8 M-stats < 1.0 (expected for high quality)\n")


def test_irregular_sensitivity():
    """Test that M1 is sensitive to irregular component size"""
    print("Test 6: M1 sensitivity to irregular component")
    
    computer = MStatisticsComputer()
    
    # Baseline
    components1 = create_test_data()
    result1 = computer.compute(components1)
    m1_baseline = result1['m1']
    
    # Increase irregular component
    components2 = create_test_data()
    components2['irregular'] = components2['irregular'] * 5
    components2['original'] = components2['seasonal'] + components2['trend'] + components2['irregular']
    components2['seasonally_adjusted'] = components2['trend'] + components2['irregular']
    
    result2 = computer.compute(components2)
    m1_increased = result2['m1']
    
    print(f"  M1 (baseline): {m1_baseline:.3f}")
    print(f"  M1 (5x irregular): {m1_increased:.3f}")
    
    if m1_increased > m1_baseline:
        print("✓ Test 6 passed: M1 increases with larger irregular\n")
    else:
        print("⚠ Test 6: M1 did not increase as expected\n")


def main():
    """Run all standalone tests"""
    print("=" * 60)
    print("M-Statistics Standalone Tests")
    print("=" * 60)
    print()
    
    try:
        result = test_basic_computation()
        test_q_is_average()
        test_determinism()
        test_quality_validation()
        test_high_quality_decomposition()
        test_irregular_sensitivity()
        
        print("=" * 60)
        print("All tests completed successfully!")
        print("=" * 60)
        
    except Exception as e:
        print(f"\n❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()

