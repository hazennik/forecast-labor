#!/usr/bin/env python3
"""
Test Data Pipelines
Quick validation that all ETL pipelines work correctly
"""

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from loguru import logger


def test_ui_claims():
    """Test UI Claims pipeline"""
    try:
        from etl.public.claims import UIClaimsETL
        
        logger.info("Testing UI Claims ETL...")
        etl = UIClaimsETL()
        
        # Test extract
        df = etl.extract()
        assert not df.empty, "No data extracted"
        logger.info(f"✓ Extracted {len(df)} rows")
        
        # Test validate
        assert etl.validate(df), "Validation failed"
        logger.info("✓ Validation passed")
        
        # Test transform
        df_clean = etl.transform(df)
        assert not df_clean.empty, "Transform produced empty data"
        logger.info(f"✓ Transformed to {len(df_clean)} rows")
        
        logger.info("✅ UI Claims ETL test PASSED\n")
        return True
        
    except Exception as e:
        logger.error(f"❌ UI Claims ETL test FAILED: {e}\n")
        return False


def test_treasury_withholdings():
    """Test Treasury Withholdings pipeline"""
    try:
        from etl.public.treasury_withholdings import TreasuryWithholdingsETL
        
        logger.info("Testing Treasury Withholdings ETL...")
        etl = TreasuryWithholdingsETL(lookback_days=30)  # Smaller for testing
        
        # Test extract
        df = etl.extract()
        assert not df.empty, "No data extracted"
        logger.info(f"✓ Extracted {len(df)} rows")
        
        # Test validate
        assert etl.validate(df), "Validation failed"
        logger.info("✓ Validation passed")
        
        # Test transform
        df_clean = etl.transform(df)
        assert not df_clean.empty, "Transform produced empty data"
        logger.info(f"✓ Transformed to {len(df_clean)} rows")
        
        logger.info("✅ Treasury Withholdings ETL test PASSED\n")
        return True
        
    except Exception as e:
        logger.error(f"❌ Treasury Withholdings ETL test FAILED: {e}\n")
        return False


def test_ces():
    """Test BLS CES pipeline"""
    try:
        from etl.public.bls_ces import CESETL
        
        logger.info("Testing BLS CES ETL...")
        etl = CESETL(lookback_years=2)  # Smaller for testing
        
        # Test extract
        df = etl.extract()
        assert not df.empty, "No data extracted"
        logger.info(f"✓ Extracted {len(df)} rows")
        
        # Test validate
        assert etl.validate(df), "Validation failed"
        logger.info("✓ Validation passed")
        
        # Test transform
        df_clean = etl.transform(df)
        assert not df_clean.empty, "Transform produced empty data"
        logger.info(f"✓ Transformed to {len(df_clean)} rows")
        
        # Test NFP extraction
        nfp = etl.get_nfp_latest(df_clean)
        assert nfp is not None, "NFP extraction failed"
        logger.info(f"✓ Latest NFP: {nfp['level']}k ({nfp['date']})")
        
        logger.info("✅ BLS CES ETL test PASSED\n")
        return True
        
    except Exception as e:
        logger.error(f"❌ BLS CES ETL test FAILED: {e}\n")
        return False


def test_laus():
    """Test BLS LAUS pipeline"""
    try:
        from etl.public.bls_laus import LAUSETL
        
        logger.info("Testing BLS LAUS ETL...")
        etl = LAUSETL(lookback_years=2)
        
        df = etl.extract()
        assert not df.empty, "No data extracted"
        logger.info(f"✓ Extracted {len(df)} rows")
        
        assert etl.validate(df), "Validation failed"
        logger.info("✓ Validation passed")
        
        df_clean = etl.transform(df)
        assert not df_clean.empty, "Transform produced empty data"
        logger.info(f"✓ Transformed to {len(df_clean)} rows")
        
        logger.info("✅ LAUS ETL test PASSED\n")
        return True
        
    except Exception as e:
        logger.error(f"❌ LAUS ETL test FAILED: {e}\n")
        return False


def test_strikes():
    """Test Strikes pipeline"""
    try:
        from etl.public.strikes import StrikesETL
        
        logger.info("Testing Strikes ETL...")
        etl = StrikesETL()
        
        df = etl.extract()
        # Empty is okay for strikes
        logger.info(f"✓ Extracted {len(df)} rows")
        
        assert etl.validate(df), "Validation failed"
        logger.info("✓ Validation passed")
        
        df_clean = etl.transform(df)
        logger.info(f"✓ Transformed to {len(df_clean)} rows")
        
        logger.info("✅ Strikes ETL test PASSED\n")
        return True
        
    except Exception as e:
        logger.error(f"❌ Strikes ETL test FAILED: {e}\n")
        return False


def test_weather():
    """Test Weather pipeline"""
    try:
        from etl.public.weather import WeatherETL
        
        logger.info("Testing Weather ETL...")
        etl = WeatherETL()
        
        df = etl.extract()
        # Empty is okay for weather
        logger.info(f"✓ Extracted {len(df)} rows")
        
        assert etl.validate(df), "Validation failed"
        logger.info("✓ Validation passed")
        
        df_clean = etl.transform(df)
        logger.info(f"✓ Transformed to {len(df_clean)} rows")
        
        logger.info("✅ Weather ETL test PASSED\n")
        return True
        
    except Exception as e:
        logger.error(f"❌ Weather ETL test FAILED: {e}\n")
        return False


def test_cnbfs():
    """Test CNBFS pipeline"""
    try:
        from etl.public.cnbfs import CNBFSETL
        
        logger.info("Testing CNBFS ETL...")
        etl = CNBFSETL()
        
        df = etl.extract()
        assert not df.empty, "No data extracted"
        logger.info(f"✓ Extracted {len(df)} rows")
        
        assert etl.validate(df), "Validation failed"
        logger.info("✓ Validation passed")
        
        df_clean = etl.transform(df)
        assert not df_clean.empty, "Transform produced empty data"
        logger.info(f"✓ Transformed to {len(df_clean)} rows")
        
        logger.info("✅ CNBFS ETL test PASSED\n")
        return True
        
    except Exception as e:
        logger.error(f"❌ CNBFS ETL test FAILED: {e}\n")
        return False


def main():
    """Run all pipeline tests"""
    logger.info("=" * 60)
    logger.info("DATA PIPELINE TESTS")
    logger.info("=" * 60)
    logger.info("")
    
    results = {
        "ui_claims": test_ui_claims(),
        "treasury_withholdings": test_treasury_withholdings(),
        "ces": test_ces(),
        "laus": test_laus(),
        "strikes": test_strikes(),
        "weather": test_weather(),
        "cnbfs": test_cnbfs(),
    }
    
    # Summary
    logger.info("=" * 60)
    logger.info("TEST SUMMARY")
    logger.info("=" * 60)
    
    for pipeline, passed in results.items():
        status = "✅ PASSED" if passed else "❌ FAILED"
        logger.info(f"{status} - {pipeline}")
    
    total = len(results)
    passed = sum(results.values())
    
    logger.info("")
    logger.info(f"Results: {passed}/{total} tests passed")
    logger.info("=" * 60)
    
    return all(results.values())


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)

