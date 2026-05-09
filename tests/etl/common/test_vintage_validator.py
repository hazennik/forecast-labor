"""
Tests for vintage data validation

Ensures that production scripts properly detect and reject synthetic test data.
"""

import pytest
import pandas as pd
from pathlib import Path
from datetime import datetime

from etl.common.vintage_validator import (
    validate_vintage_is_production,
    require_production_data,
    is_synthetic_data,
    get_vintage_provenance,
    VintageValidationError,
    save_vintage_with_metadata,
    load_vintage_with_metadata,
)


class TestVintageValidation:
    """Test vintage validation logic"""

    @pytest.fixture
    def synthetic_data(self):
        """Create synthetic test data with metadata"""
        df = pd.DataFrame(
            {"date": pd.date_range("2024-01-01", periods=120, freq="D"), "value": range(120)}
        )
        # Tag as synthetic
        df.attrs["is_synthetic"] = True
        df.attrs["generated_by"] = "scripts/create_test_vintages.py"
        df.attrs["purpose"] = "Testing"
        df.attrs["warning"] = "SYNTHETIC TEST DATA"
        return df

    @pytest.fixture
    def production_data(self):
        """Create production data with metadata"""
        df = pd.DataFrame(
            {"date": pd.date_range("2024-01-01", periods=500, freq="D"), "value": range(500)}
        )
        # Tag as production
        df.attrs["is_synthetic"] = False
        df.attrs["generated_by"] = "etl.bls_ces"
        df.attrs["purpose"] = "Production ETL output"
        df.attrs["source_name"] = "bls_ces"
        return df

    @pytest.fixture
    def data_without_metadata(self):
        """Create data without provenance metadata (legacy)"""
        df = pd.DataFrame(
            {"date": pd.date_range("2024-01-01", periods=500, freq="D"), "value": range(500)}
        )
        # No attrs set
        return df

    def test_synthetic_data_detected_and_rejected(self, synthetic_data):
        """Test that synthetic data is detected and rejected"""
        with pytest.raises(VintageValidationError) as exc_info:
            validate_vintage_is_production(
                synthetic_data,
                Path("data/vintages/test/2024-01-15/test_vintage.parquet"),
                allow_test_data=False,
            )

        assert "SYNTHETIC TEST DATA DETECTED" in str(exc_info.value)
        assert "CRITICAL" in str(exc_info.value)

    def test_production_data_accepted(self, production_data):
        """Test that production data passes validation"""
        # Should not raise
        validate_vintage_is_production(
            production_data,
            Path("data/vintages/bls_ces/2024-11-16/bls_ces_vintage.parquet"),
            allow_test_data=False,
        )

    def test_synthetic_data_allowed_with_flag(self, synthetic_data):
        """Test that synthetic data is allowed when flag is set"""
        # Should not raise when allow_test_data=True
        validate_vintage_is_production(
            synthetic_data,
            Path("data/vintages/test/2024-01-15/test_vintage.parquet"),
            allow_test_data=True,
        )

    def test_data_without_metadata_passes_heuristics(self, data_without_metadata):
        """Test that data without metadata passes if heuristics pass"""
        # Should pass because:
        # - No is_synthetic flag (ambiguous)
        # - 500 rows (not suspicious)
        # - Not the test pinned date
        validate_vintage_is_production(
            data_without_metadata,
            Path("data/vintages/bls_ces/2024-11-16/bls_ces_vintage.parquet"),
            allow_test_data=False,
            strict=False,
        )

    def test_test_row_count_detected(self):
        """Test that the exact test data row count (120) is flagged"""
        df = pd.DataFrame(
            {"date": pd.date_range("2024-01-01", periods=120, freq="D"), "value": range(120)}
        )
        # No metadata, but suspicious row count

        with pytest.raises(VintageValidationError) as exc_info:
            validate_vintage_is_production(
                df,
                Path("data/vintages/test/2024-11-16/test_vintage.parquet"),
                allow_test_data=False,
                strict=True,
            )

        assert "120 rows" in str(exc_info.value)

    def test_test_pinned_date_flagged(self):
        """Test that test data pinned date (2024-01-15) is flagged"""
        df = pd.DataFrame(
            {"date": pd.date_range("2024-01-01", periods=120, freq="D"), "value": range(120)}
        )
        # No metadata, but test pinned date + test row count

        with pytest.raises(VintageValidationError) as exc_info:
            validate_vintage_is_production(
                df,
                Path("data/vintages/bls_ces/2024-01-15/bls_ces_vintage.parquet"),
                allow_test_data=False,
                strict=True,
            )

        assert "MULTIPLE TEST DATA INDICATORS" in str(exc_info.value)
        assert "2024-01-15" in str(exc_info.value)

    def test_require_production_data_strict(self, synthetic_data):
        """Test require_production_data always rejects synthetic"""
        with pytest.raises(VintageValidationError):
            require_production_data(
                synthetic_data, Path("data/vintages/test/2024-01-15/test_vintage.parquet")
            )

    def test_is_synthetic_data_function(
        self, synthetic_data, production_data, data_without_metadata
    ):
        """Test is_synthetic_data helper function"""
        assert is_synthetic_data(synthetic_data) is True
        assert is_synthetic_data(production_data) is False
        assert is_synthetic_data(data_without_metadata) is None

    def test_get_vintage_provenance(self, production_data):
        """Test get_vintage_provenance extracts metadata"""
        provenance = get_vintage_provenance(production_data)

        assert provenance["is_synthetic"] is False
        assert provenance["generated_by"] == "etl.bls_ces"
        assert provenance["purpose"] == "Production ETL output"
        assert provenance["source_name"] == "bls_ces"

    def test_get_vintage_provenance_no_metadata(self, data_without_metadata):
        """Test get_vintage_provenance returns empty dict for no metadata"""
        provenance = get_vintage_provenance(data_without_metadata)

        assert provenance == {
            "is_synthetic": None,
            "generated_by": None,
            "generation_date": None,
            "purpose": None,
            "source_name": None,
            "vintage_date": None,
            "warning": None,
            "random_seed": None,
        }

    def test_small_dataset_warning(self):
        """Test that small datasets (< 50 rows) trigger warnings"""
        df = pd.DataFrame(
            {"date": pd.date_range("2024-01-01", periods=30, freq="D"), "value": range(30)}
        )

        # Should pass but log warning
        validate_vintage_is_production(
            df,
            Path("data/vintages/test/2024-11-16/test_vintage.parquet"),
            allow_test_data=False,
            strict=False,
        )

    def test_validation_with_production_mode_environment(self, synthetic_data):
        """Test that validation works in production mode"""
        # In production mode, synthetic data must always fail
        with pytest.raises(VintageValidationError):
            require_production_data(
                synthetic_data, Path("data/vintages/test/2024-01-15/test_vintage.parquet")
            )


class TestVintageValidationIntegration:
    """Integration tests for vintage validation in production scripts"""

    def test_build_features_rejects_synthetic_data(self, tmp_path):
        """Test that build_features.py would reject synthetic data"""
        # Create synthetic vintage file
        df = pd.DataFrame(
            {
                "date": pd.date_range("2024-01-01", periods=120, freq="MS"),
                "series_id": ["CES0000000001"] * 120,
                "value": range(120),
                "series_name": ["Total Nonfarm Payrolls"] * 120,
            }
        )
        df.attrs["is_synthetic"] = True
        df.attrs["generated_by"] = "test"

        vintage_file = tmp_path / "test_vintage.parquet"
        df.to_parquet(vintage_file)

        # Load and validate (should fail)
        df_loaded = pd.read_parquet(vintage_file)

        with pytest.raises(VintageValidationError):
            validate_vintage_is_production(df_loaded, vintage_file, strict=True)

    def test_seasonal_adjustment_rejects_synthetic_data(self, tmp_path):
        """Test that run_seasonal_adjustment.py would reject synthetic data"""
        # Create synthetic vintage file
        df = pd.DataFrame(
            {
                "date": pd.date_range("2024-01-01", periods=120, freq="MS"),
                "series_id": ["CES0000000001"] * 120,
                "value": range(120),
            }
        )
        df.attrs["is_synthetic"] = True
        df.attrs["generated_by"] = "test"

        vintage_file = tmp_path / "test_vintage.parquet"
        df.to_parquet(vintage_file)

        # Load and validate (should fail)
        df_loaded = pd.read_parquet(vintage_file)

        with pytest.raises(VintageValidationError):
            require_production_data(df_loaded, vintage_file)

    def test_metadata_preserved_in_parquet(self, tmp_path):
        """Test that metadata is preserved when writing/reading parquet"""
        # Create data with metadata
        df = pd.DataFrame(
            {"date": pd.date_range("2024-01-01", periods=100, freq="D"), "value": range(100)}
        )
        df.attrs["is_synthetic"] = False
        df.attrs["generated_by"] = "test_etl"
        df.attrs["generation_date"] = datetime.now().isoformat()

        # Write to parquet using metadata-preserving function
        parquet_file = tmp_path / "test.parquet"
        save_vintage_with_metadata(df, parquet_file)

        # Read back using metadata-restoring function
        df_loaded = load_vintage_with_metadata(parquet_file)

        # Verify metadata preserved
        assert df_loaded.attrs["is_synthetic"] is False
        assert df_loaded.attrs["generated_by"] == "test_etl"
        assert "generation_date" in df_loaded.attrs


class TestEdgeCases:
    """Test edge cases and error conditions"""

    def test_empty_dataframe(self):
        """Test validation with empty DataFrame"""
        df = pd.DataFrame()

        # Should pass (no data to validate)
        validate_vintage_is_production(
            df, Path("data/vintages/test/2024-11-16/empty.parquet"), strict=False
        )

    def test_dataframe_without_attrs(self):
        """Test DataFrame without attrs metadata (empty attrs dict)"""
        df = pd.DataFrame({"value": [1, 2, 3]})
        # Note: pandas DataFrames always have .attrs property (as empty dict by default)
        # We can't delete it (it's a property descriptor), but we test with empty attrs
        # which represents DataFrames from older ETL versions without metadata
        assert hasattr(df, "attrs")  # attrs property always exists
        assert len(df.attrs) == 0  # but can be empty

        # Should pass with warning (no metadata to validate)
        validate_vintage_is_production(
            df, Path("data/vintages/test/2024-11-16/no_attrs.parquet"), strict=False
        )

    def test_mixed_metadata(self):
        """Test DataFrame with partial metadata"""
        df = pd.DataFrame(
            {"date": pd.date_range("2024-01-01", periods=200, freq="D"), "value": range(200)}
        )
        # Only set some metadata fields
        df.attrs["generated_by"] = "unknown"
        # is_synthetic is NOT set

        # Should pass but log warning in strict mode
        validate_vintage_is_production(
            df, Path("data/vintages/test/2024-11-16/partial_meta.parquet"), strict=True
        )
