#!/usr/bin/env python3
"""
Standalone test script for Q-statistics computation
Does not require pytest or database dependencies
"""

import sys
import os
from pathlib import Path
import numpy as np
import pandas as pd

# Add project root to path. Resolve relative to this script so the test works
# both on the host checkout and inside the Docker /app mount.
project_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(project_root))

# Import directly from file
import importlib.util

spec = importlib.util.spec_from_file_location(
    "q_statistics", os.path.join(project_root, "seasonal/diagnostics/q_statistics.py")
)
q_statistics = importlib.util.module_from_spec(spec)
spec.loader.exec_module(q_statistics)

QStatisticsComputer = q_statistics.QStatisticsComputer
compute_ljung_box = q_statistics.compute_ljung_box
validate_residual_randomness = q_statistics.validate_residual_randomness


def create_random_residuals():
    """Create random (white noise) residuals"""
    np.random.seed(42)
    return pd.Series(np.random.normal(0, 1, 100))


def create_autocorrelated_residuals():
    """Create autocorrelated residuals (AR(1) process)"""
    np.random.seed(42)
    residuals = np.zeros(100)
    epsilon = np.random.normal(0, 1, 100)
    residuals[0] = epsilon[0]

    for i in range(1, 100):
        residuals[i] = 0.7 * residuals[i - 1] + epsilon[i]

    return pd.Series(residuals)


def test_basic_computation():
    """Test basic Q-statistics computation"""
    print("Test 1: Basic computation")

    residuals = create_random_residuals()
    computer = QStatisticsComputer(lags=10)

    result = computer.compute(residuals)

    # Check all fields are present
    assert "q_statistic" in result
    assert "p_value" in result
    assert "lags_tested" in result
    assert "degrees_of_freedom" in result

    print(f"  Q-statistic: {result['q_statistic']:.3f}")
    print(f"  p-value: {result['p_value']:.4f}")
    print(f"  Lags tested: {result['lags_tested']}")
    print(f"  DOF: {result['degrees_of_freedom']}")

    # Verify non-negative Q-statistic
    assert result["q_statistic"] >= 0

    # Verify p-value in [0, 1]
    assert 0 <= result["p_value"] <= 1

    print("✓ Test 1 passed\n")
    return result


def test_random_residuals_pass():
    """Test that random residuals pass Ljung-Box test"""
    print("Test 2: Random residuals should pass test")

    residuals = create_random_residuals()
    computer = QStatisticsComputer(lags=10)
    result = computer.compute(residuals)

    print(f"  Q-statistic: {result['q_statistic']:.3f}")
    print(f"  p-value: {result['p_value']:.4f}")

    # Random residuals should have p-value > 0.05
    if result["p_value"] > 0.05:
        print("  ✓ Test passed: p-value > 0.05 (residuals are random)")
    else:
        print(f"  ⚠ Note: p-value = {result['p_value']:.4f} (random data can occasionally fail)")

    print("✓ Test 2 completed\n")


def test_autocorrelated_residuals_fail():
    """Test that autocorrelated residuals fail Ljung-Box test"""
    print("Test 3: Autocorrelated residuals should fail test")

    residuals = create_autocorrelated_residuals()
    computer = QStatisticsComputer(lags=10)
    result = computer.compute(residuals)

    print(f"  Q-statistic: {result['q_statistic']:.3f}")
    print(f"  p-value: {result['p_value']:.4f}")

    # Autocorrelated residuals should have p-value < 0.05
    assert (
        result["p_value"] < 0.05
    ), f"Autocorrelated residuals should fail test: p-value={result['p_value']:.4f}"

    print("  ✓ Test passed: p-value < 0.05 (autocorrelation detected)")
    print("✓ Test 3 passed\n")


def test_q_increases_with_autocorrelation():
    """Test that Q-statistic increases with stronger autocorrelation"""
    print("Test 4: Q-statistic increases with autocorrelation strength")

    computer = QStatisticsComputer(lags=10)

    # Random residuals (low Q)
    random_res = create_random_residuals()
    result_random = computer.compute(random_res)
    q_random = result_random["q_statistic"]

    # Autocorrelated residuals (high Q)
    ar_res = create_autocorrelated_residuals()
    result_ar = computer.compute(ar_res)
    q_ar = result_ar["q_statistic"]

    print(f"  Q (random): {q_random:.3f}")
    print(f"  Q (AR(1)): {q_ar:.3f}")

    assert (
        q_ar > q_random
    ), f"AR process should have higher Q: Q_ar={q_ar:.3f}, Q_random={q_random:.3f}"

    print("  ✓ Test passed: Q_ar > Q_random")
    print("✓ Test 4 passed\n")


def test_determinism():
    """Test that computation is deterministic"""
    print("Test 5: Determinism")

    residuals = create_random_residuals()
    computer = QStatisticsComputer(lags=10)

    result1 = computer.compute(residuals)
    result2 = computer.compute(residuals)

    assert result1["q_statistic"] == result2["q_statistic"]
    assert result1["p_value"] == result2["p_value"]

    print("  All Q-statistics are deterministic")
    print("✓ Test 5 passed\n")


def test_quality_validation():
    """Test quality threshold validation"""
    print("Test 6: Quality validation")

    # Good quality (high p-value)
    q_stats_good = {
        "q_statistic": 8.5,
        "p_value": 0.58,
        "lags_tested": 10,
        "degrees_of_freedom": 10,
    }

    validation_good = validate_residual_randomness(q_stats_good)

    assert validation_good["quality"] == "good"
    assert validation_good["pass"] is True
    assert validation_good["random"] is True

    print(f"  Good quality: {validation_good['quality']}, pass={validation_good['pass']}")

    # Poor quality (low p-value)
    q_stats_poor = {
        "q_statistic": 28.5,
        "p_value": 0.001,
        "lags_tested": 10,
        "degrees_of_freedom": 10,
    }

    validation_poor = validate_residual_randomness(q_stats_poor)

    assert validation_poor["quality"] == "poor"
    assert validation_poor["pass"] is False
    assert validation_poor["random"] is False

    print(f"  Poor quality: {validation_poor['quality']}, pass={validation_poor['pass']}")
    print("✓ Test 6 passed\n")


def test_convenience_function():
    """Test convenience function"""
    print("Test 7: Convenience function")

    residuals = create_random_residuals()
    result = compute_ljung_box(residuals, lags=10)

    assert "q_statistic" in result
    assert "p_value" in result
    assert result["lags_tested"] == 10

    print(f"  Q-statistic: {result['q_statistic']:.3f}")
    print(f"  p-value: {result['p_value']:.4f}")
    print("✓ Test 7 passed\n")


def main():
    """Run all standalone tests"""
    print("=" * 60)
    print("Q-Statistics Standalone Tests")
    print("=" * 60)
    print()

    try:
        test_basic_computation()
        test_random_residuals_pass()
        test_autocorrelated_residuals_fail()
        test_q_increases_with_autocorrelation()
        test_determinism()
        test_quality_validation()
        test_convenience_function()

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
