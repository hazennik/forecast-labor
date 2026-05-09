"""
Standalone verification script for VintageHarness implementation.

This script can be run outside of pytest to verify basic functionality.
"""

import sys
from pathlib import Path
from datetime import date
import pandas as pd
import numpy as np

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from backtests.vintage_harness import VintageHarness, VintageReconstructionError, ReconstructedState
from etl.common.vintage import VintageManager


def verify_harness():
    """Verify VintageHarness basic functionality."""
    print("=" * 80)
    print("VintageHarness Verification")
    print("=" * 80)

    # Create temporary test directory
    test_dir = Path(__file__).parent.parent / "data" / "test_vintages_verify"
    test_dir.mkdir(parents=True, exist_ok=True)

    try:
        # Initialize harness
        print("\n1. Testing harness initialization...")
        harness = VintageHarness(test_dir)
        assert harness.vintage_base_path == test_dir
        assert isinstance(harness.vintage_manager, VintageManager)
        print("   ✅ Initialization successful")

        # Create sample vintages
        print("\n2. Creating sample vintages...")
        vm = VintageManager(test_dir)

        for source in ["ces", "laus"]:
            for month in [1, 2, 3]:
                vintage_date = date(2024, month, 1)
                dates = pd.date_range(start="2020-01-01", end=vintage_date, freq="MS")

                data = pd.DataFrame(
                    {
                        "date": dates,
                        "value": np.random.randn(len(dates)) * 100 + 1000,
                        "series_id": f"{source}_test",
                    }
                )

                vm.create_vintage(source, data, vintage_date)

        print("   ✅ Created vintages for ces and laus")

        # Test reconstruction
        print("\n3. Testing state reconstruction...")
        as_of_date = date(2024, 2, 15)
        state = harness.reconstruct_state(as_of_date=as_of_date, sources=["ces", "laus"])

        assert isinstance(state, ReconstructedState)
        assert state.as_of_date == as_of_date
        assert "ces" in state.data
        assert "laus" in state.data
        assert len(state.sources_available) == 2
        print(f"   ✅ Reconstructed state for {as_of_date}")
        print(f"      - Sources: {state.sources_available}")
        print(f"      - Vintage dates: {state.vintage_dates}")

        # Test vintage honesty validation
        print("\n4. Testing vintage honesty validation...")
        is_valid, errors = harness.validate_vintage_honesty(state)

        assert is_valid is True
        assert len(errors) == 0
        print("   ✅ Vintage honesty validation passed")

        # Test edge case: missing source
        print("\n5. Testing edge case: missing source...")
        try:
            harness.reconstruct_state(as_of_date=as_of_date, sources=["nonexistent"])
            print("   ❌ Should have raised VintageReconstructionError")
            return False
        except VintageReconstructionError as e:
            print(f"   ✅ Correctly raised error: {type(e).__name__}")

        # Test edge case: allow_partial
        print("\n6. Testing edge case: allow_partial=True...")
        state_partial = harness.reconstruct_state(
            as_of_date=as_of_date, sources=["ces", "laus", "missing_source"], allow_partial=True
        )

        assert len(state_partial.sources_available) == 2
        assert "missing_source" not in state_partial.data
        print("   ✅ Partial reconstruction works correctly")

        # Test get_available_backtest_dates
        print("\n7. Testing get_available_backtest_dates...")
        backtest_dates = harness.get_available_backtest_dates(sources=["ces", "laus"])

        assert len(backtest_dates) == 3  # Jan, Feb, Mar
        assert backtest_dates[0] == date(2024, 1, 1)
        print(f"   ✅ Found {len(backtest_dates)} backtest dates: {backtest_dates}")

        print("\n" + "=" * 80)
        print("✅ ALL VERIFICATION CHECKS PASSED")
        print("=" * 80)

        return True

    except Exception as e:
        print(f"\n❌ Verification failed: {e}")
        import traceback

        traceback.print_exc()
        return False

    finally:
        # Cleanup
        import shutil

        if test_dir.exists():
            shutil.rmtree(test_dir)
        print("\n🧹 Cleanup complete")


if __name__ == "__main__":
    success = verify_harness()
    sys.exit(0 if success else 1)
