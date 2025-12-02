#!/usr/bin/env python3
"""
Debug Regressor Variance Script
Phase 6.2.0: Verify regressors have non-zero variance and correct values

This script manually tests regressor variance without requiring pytest or Docker.
"""

import sys
from pathlib import Path
from datetime import date

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

def test_holiday_regressors():
    """Test holiday regressor variance"""
    print("=" * 70)
    print("TESTING HOLIDAY REGRESSORS")
    print("=" * 70)
    
    try:
        from seasonal.regressors.holiday_regressors import HolidayRegressors
        import pandas as pd
        
        builder = HolidayRegressors()
        start_date = date(2014, 1, 1)
        end_date = date(2023, 12, 31)
        
        print(f"\n1. Building holiday regressors from {start_date} to {end_date}...")
        regressors = builder.build(start_date, end_date)
        
        print(f"\n2. Regressor Summary:")
        print(f"   - Shape: {regressors.shape}")
        print(f"   - Columns: {list(regressors.columns)}")
        
        print(f"\n3. Variance Analysis:")
        all_have_variance = True
        for col in regressors.columns:
            var = regressors[col].var()
            non_zero_count = (regressors[col] != 0).sum()
            non_zero_pct = (non_zero_count / len(regressors)) * 100
            
            status = "✅ PASS" if var > 0 else "❌ FAIL"
            print(f"   {col}:")
            print(f"      Variance: {var:.6f} {status}")
            print(f"      Non-zero values: {non_zero_count} / {len(regressors)} ({non_zero_pct:.1f}%)")
            print(f"      Unique values: {set(regressors[col].unique())}")
            
            if var <= 0:
                all_have_variance = False
        
        print(f"\n4. First 12 rows (showing patterns):")
        print(regressors.head(12).to_string())
        
        print(f"\n5. Specific Years Analysis:")
        # Easter 2020 (April 12 - mid-month, expect 0)
        april_2020 = regressors.loc[regressors.index.to_period('M') == pd.Period("2020-04", freq='M'), "easter_timing"]
        if not april_2020.empty:
            val = april_2020.iloc[0]
            expected = 0  # April 12 is mid-month
            status = "✅" if val == expected else "❌"
            print(f"   Easter 2020 (April 12, mid): {val} (expected {expected}) {status}")
        
        # Easter 2024 (March 31 - late, expect 1)
        # Note: might not be in data range
        
        # Thanksgiving 2023 (November 23, early, expect -1)
        nov_2023 = regressors.loc[regressors.index.to_period('M') == pd.Period("2023-11", freq='M'), "thanksgiving_timing"]
        if not nov_2023.empty:
            val = nov_2023.iloc[0]
            expected = -1  # Nov 23 is ≤ 24 (early)
            status = "✅" if val == expected else "❌"
            print(f"   Thanksgiving 2023 (Nov 23, early): {val} (expected {expected}) {status}")
        
        # Labor Day 2023 (September 4, mid, expect 0)
        sept_2023 = regressors.loc[regressors.index.to_period('M') == pd.Period("2023-09", freq='M'), "labor_day_timing"]
        if not sept_2023.empty:
            val = sept_2023.iloc[0]
            expected = 0  # Sept 4 is mid-range
            status = "✅" if val == expected else "❌"
            print(f"   Labor Day 2023 (Sept 4, mid): {val} (expected {expected}) {status}")
        
        print(f"\n6. Overall Result:")
        if all_have_variance:
            print("   ✅ ALL REGRESSORS HAVE NON-ZERO VARIANCE")
            return True
        else:
            print("   ❌ SOME REGRESSORS HAVE ZERO VARIANCE")
            return False
    
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_spec_generation():
    """Test that spec includes user regressors"""
    print("\n" + "=" * 70)
    print("TESTING SPEC GENERATION")
    print("=" * 70)
    
    try:
        from seasonal.regressors.holiday_regressors import HolidayRegressors
        from seasonal.spec_builder import SpecBuilder, X13Spec
        
        # Build regressors
        builder = HolidayRegressors()
        regressors = builder.build(date(2014, 1, 1), date(2023, 12, 31))
        
        print(f"\n1. Building X-13 spec with user regressors...")
        spec_builder = SpecBuilder()
        config = X13Spec(
            series_name="test_series",
            title="Test Series",
            start_year=2014,
            start_month=1,
            mode="mult",
            easter=True,
            trading_day=True,
            user_regressors=list(regressors.columns),
            regressor_data=regressors
        )
        spec_content = spec_builder.build_spec(config)
        
        print(f"\n2. Generated Spec Content:")
        print("-" * 70)
        print(spec_content)
        print("-" * 70)
        
        print(f"\n3. Validation Checks:")
        
        # Check for user declaration
        has_user = "user =" in spec_content
        status = "✅ PASS" if has_user else "❌ FAIL"
        print(f"   Contains 'user =' declaration: {has_user} {status}")
        
        # Check for file directive
        has_file = 'file = "test_series_regressors.dat"' in spec_content
        status = "✅ PASS" if has_file else "❌ FAIL"
        print(f"   Contains file directive: {has_file} {status}")
        
        # Check for each regressor name
        all_regressors_present = True
        for regressor_name in regressors.columns:
            present = regressor_name in spec_content
            status = "✅" if present else "❌"
            print(f"   Regressor '{regressor_name}' in spec: {present} {status}")
            if not present:
                all_regressors_present = False
        
        # Check for duplicate declaration in variables
        print(f"\n4. Duplicate Declaration Check:")
        variables_line = None
        for line in spec_content.split('\n'):
            if 'variables =' in line:
                variables_line = line
                break
        
        if variables_line:
            has_duplicates = False
            for regressor_name in regressors.columns:
                if regressor_name in variables_line:
                    print(f"   ❌ FAIL: '{regressor_name}' found in variables=() (should only be in user=())")
                    has_duplicates = True
            
            if not has_duplicates:
                print(f"   ✅ PASS: No user regressors in variables=() declaration")
        
        print(f"\n5. Overall Result:")
        if has_user and has_file and all_regressors_present and not has_duplicates:
            print("   ✅ SPEC GENERATION CORRECT")
            return True
        else:
            print("   ❌ SPEC GENERATION HAS ISSUES")
            return False
    
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_pipeline_flow():
    """Test regressor flow through pipeline"""
    print("\n" + "=" * 70)
    print("TESTING PIPELINE REGRESSOR FLOW")
    print("=" * 70)
    
    try:
        from seasonal.pipeline import SeasonalAdjustmentPipeline
        import pandas as pd
        import numpy as np
        
        # Create sample series
        dates = pd.date_range("2014-01-01", "2023-12-31", freq="MS")
        np.random.seed(42)  # Reproducible
        series = pd.Series(
            140000 + 2000 * np.sin(2 * np.pi * np.arange(len(dates)) / 12) + np.random.normal(0, 500, len(dates)),
            index=dates,
            name="test_series"
        )
        
        print(f"\n1. Building regressors through pipeline...")
        pipeline = SeasonalAdjustmentPipeline()
        
        # Extended end date for X-13 forecast horizon
        extended_end = dates[-1].date()
        from dateutil.relativedelta import relativedelta
        extended_end = extended_end + relativedelta(months=24)
        
        regressors = pipeline._build_regressors(
            start_date=dates[0].date(),
            end_date=extended_end,
            config={
                "use_holiday_regressors": True,
                "use_strike_regressors": False,
                "use_weather_regressors": False
            }
        )
        
        print(f"\n2. Pipeline Output:")
        print(f"   - Shape: {regressors.shape}")
        print(f"   - Columns: {list(regressors.columns)}")
        
        print(f"\n3. Variance Preserved Check:")
        all_have_variance = True
        for col in regressors.columns:
            var = regressors[col].var()
            status = "✅ PASS" if var > 0 else "❌ FAIL"
            print(f"   {col}: variance = {var:.6f} {status}")
            if var <= 0:
                all_have_variance = False
        
        print(f"\n4. Overall Result:")
        if all_have_variance and len(regressors.columns) > 0:
            print("   ✅ PIPELINE PRESERVES REGRESSOR VARIANCE")
            return True
        else:
            print("   ❌ PIPELINE HAS ISSUES")
            return False
    
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Run all debug tests"""
    print("REGRESSOR VARIANCE DEBUG SCRIPT")
    print("Phase 6.2.0: Verify regressors have non-zero variance")
    print("")
    
    results = []
    
    # Test 1: Holiday regressors
    results.append(("Holiday Regressors", test_holiday_regressors()))
    
    # Test 2: Spec generation
    results.append(("Spec Generation", test_spec_generation()))
    
    # Test 3: Pipeline flow
    results.append(("Pipeline Flow", test_pipeline_flow()))
    
    # Summary
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status} {name}")
    
    print(f"\nTotal: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n✅ ALL TESTS PASSED - Regressors have non-zero variance and are correctly configured")
        return 0
    else:
        print(f"\n❌ {total - passed} TEST(S) FAILED - Investigation needed")
        return 1


if __name__ == "__main__":
    sys.exit(main())

