"""
Build features script - CLI runner for feature generation.

Orchestrates:
- Loading vintage data
- Applying MIDAS lag construction
- Frequency transformations
- Calendar adjustments
- Scaling/winsorization
- State/sector aggregations
- Feature registry updates

Usage:
    python scripts/build_features.py --vintage-date 2024-01-15 --all
    python scripts/build_features.py --vintage-date 2024-01-15 --midas-only
    python scripts/build_features.py --vintage-date 2024-01-15 --aggregations-only
"""

import argparse
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Optional
import pandas as pd
import sys
from loguru import logger

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from features.midas.lag_constructor import MIDASLagConstructor
from features.transforms.frequency import FrequencyConverter
from features.transforms.calendar import apply_calendar_adjustment
from features.transforms.scaling import StandardScaler, Winsorizer
from features.transforms.pipeline import TransformPipeline
from features.aggregations.state_aggregator import StateAggregator
from features.aggregations.sector_aggregator import SectorAggregator
from features.registry import FeatureRegistry, get_registry_config_from_env
from etl.common.storage import StorageClient
from etl.common.vintage import VintageManager
from etl.common.vintage_validator import validate_vintage_is_production, log_vintage_provenance


class FeatureBuilder:
    """
    Orchestrates feature generation from vintage data.

    Applies all feature engineering transformations and logs to registry.
    """

    def __init__(self, vintage_date: str, output_dir: Path):
        """
        Initialize feature builder.
        
        The feature registry backend is configured via environment variables:
        - FEATURE_REGISTRY_BACKEND: 'memory' (default) or 'database'
        - POSTGRES_*: Database connection parameters (if backend='database')

        Args:
            vintage_date: Vintage date (YYYY-MM-DD)
            output_dir: Directory for output features
        """
        self.vintage_date = vintage_date
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Initialize registry with environment-based configuration
        registry_config = get_registry_config_from_env()
        self.registry = FeatureRegistry(**registry_config)
        
        self.storage = StorageClient()
        self.vintage_mgr = VintageManager(storage_client=self.storage)

        logger.info(
            "feature_builder_initialized",
            vintage_date=vintage_date,
            output_dir=str(output_dir),
            registry_backend=registry_config['backend'],
        )

    def build_all(self) -> Dict[str, pd.DataFrame]:
        """
        Build all features.

        Returns:
            Dictionary of feature DataFrames
        """
        logger.info("building_all_features", vintage_date=self.vintage_date)

        features = {}

        # 1. MIDAS lag features
        logger.info("building_midas_features")
        midas_features = self.build_midas_features()
        features.update(midas_features)

        # 2. Frequency conversions
        logger.info("building_frequency_features")
        freq_features = self.build_frequency_features()
        features.update(freq_features)

        # 3. Calendar adjustments
        logger.info("building_calendar_features")
        calendar_features = self.build_calendar_features()
        features.update(calendar_features)

        # 4. Scaled features
        logger.info("building_scaled_features")
        scaled_features = self.build_scaled_features()
        features.update(scaled_features)

        # 5. Aggregations
        logger.info("building_aggregations")
        aggregations = self.build_aggregations()
        features.update(aggregations)

        logger.info("all_features_built", feature_count=len(features))

        # Save features
        self._save_features(features)

        return features

    def build_midas_features(self) -> Dict[str, pd.DataFrame]:
        """Build MIDAS lag features."""
        features = {}

        # Load Treasury withholdings (daily)
        try:
            treasury_df = self._load_vintage_data("treasury_withholdings")
            if treasury_df is not None and not treasury_df.empty:
                # Extract value column as Series
                # Treasury ETL typically has 'withholding_amount' or similar
                value_cols = [c for c in treasury_df.columns if 'withhold' in c.lower() or 'amount' in c.lower()]
                if not value_cols:
                    value_cols = treasury_df.select_dtypes(include=['number']).columns.tolist()
                
                if value_cols:
                    treasury_series = treasury_df[value_cols[0]]
                    if 'date' in treasury_df.columns:
                        treasury_series.index = pd.to_datetime(treasury_df['date'])
                    
                    # Create MIDAS lags for monthly NFP forecasting
                    constructor = MIDASLagConstructor(
                        source_freq="D",
                        target_freq="M",
                        n_lags=20,
                        almon_poly_degree=2,
                        column_prefix="treasury",
                    )

                    # Target dates: monthly (first of month)
                    target_dates = pd.date_range(
                        treasury_series.index[0], treasury_series.index[-1], freq="MS"
                    )

                    midas_lags = constructor.construct_lags(treasury_series, target_dates)
                    features["treasury_midas_lags"] = midas_lags

                    # Register in registry
                    self._register_feature(
                        "treasury_midas_lags",
                        source="treasury",
                        transform="midas_lag",
                        frequency="monthly",
                    )

                    logger.info("midas_features_created", series="treasury", n_lags=20)

        except Exception as e:
            logger.error("midas_feature_creation_failed", series="treasury", error=str(e))

        # Load UI Claims (weekly)
        try:
            claims_df = self._load_vintage_data("ui_claims")
            if claims_df is not None and not claims_df.empty:
                # Extract claims value column
                value_cols = [c for c in claims_df.columns if 'claim' in c.lower() or 'initial' in c.lower()]
                if not value_cols:
                    value_cols = claims_df.select_dtypes(include=['number']).columns.tolist()
                
                if value_cols:
                    claims_series = claims_df[value_cols[0]]
                    if 'date' in claims_df.columns:
                        claims_series.index = pd.to_datetime(claims_df['date'])
                    
                    constructor = MIDASLagConstructor(
                        source_freq="W",
                        target_freq="M",
                        n_lags=8,
                        column_prefix="claims",
                    )

                    target_dates = pd.date_range(
                        claims_series.index[0], claims_series.index[-1], freq="MS"
                    )

                    midas_lags = constructor.construct_lags(claims_series, target_dates)
                    features["claims_midas_lags"] = midas_lags

                    self._register_feature(
                        "claims_midas_lags",
                        source="ui_claims",
                        transform="midas_lag",
                        frequency="monthly",
                    )

                    logger.info("midas_features_created", series="claims", n_lags=8)

        except Exception as e:
            logger.error("midas_feature_creation_failed", series="claims", error=str(e))

        return features

    def build_frequency_features(self) -> Dict[str, pd.DataFrame]:
        """Build frequency-converted features."""
        features = {}

        # Convert daily Treasury to weekly
        try:
            treasury_df = self._load_vintage_data("treasury_withholdings")
            if treasury_df is not None and not treasury_df.empty:
                # Extract value column
                value_cols = [c for c in treasury_df.columns if 'withhold' in c.lower() or 'amount' in c.lower()]
                if not value_cols:
                    value_cols = treasury_df.select_dtypes(include=['number']).columns.tolist()
                
                if value_cols:
                    treasury_series = treasury_df[value_cols[0]]
                    if 'date' in treasury_df.columns:
                        treasury_series.index = pd.to_datetime(treasury_df['date'])
                    
                    converter = FrequencyConverter(source_freq="D", target_freq="W", agg_method="mean")
                    weekly_treasury = converter.convert(treasury_series)

                    features["treasury_weekly"] = weekly_treasury.to_frame()

                    self._register_feature(
                        "treasury_weekly",
                        source="treasury",
                        transform="frequency_conversion",
                        frequency="weekly",
                    )

                    logger.info("frequency_conversion_created", series="treasury", target="weekly")

        except Exception as e:
            logger.error("frequency_conversion_failed", series="treasury", error=str(e))

        return features

    def build_calendar_features(self) -> Dict[str, pd.DataFrame]:
        """Build calendar-adjusted features."""
        features = {}

        # Calendar-adjust monthly employment
        try:
            ces_df = self._load_vintage_data("bls_ces")  # Correct DataSource enum value
            if ces_df is not None and not ces_df.empty:
                # Extract employment column
                value_cols = [c for c in ces_df.columns if 'employ' in c.lower() or 'payroll' in c.lower()]
                if not value_cols:
                    value_cols = ces_df.select_dtypes(include=['number']).columns.tolist()
                
                if value_cols:
                    ces_series = ces_df[value_cols[0]]
                    if 'date' in ces_df.columns:
                        ces_series.index = pd.to_datetime(ces_df['date'])
                    
                    adjusted = apply_calendar_adjustment(ces_series, method="business_days")

                    features["ces_calendar_adjusted"] = adjusted.to_frame()

                    self._register_feature(
                        "ces_calendar_adjusted",
                        source="bls_ces",
                        transform="calendar_adjustment",
                        frequency="monthly",
                    )

                    logger.info("calendar_adjustment_created", series="ces")

        except Exception as e:
            logger.error("calendar_adjustment_failed", series="ces", error=str(e))

        return features

    def build_scaled_features(self) -> Dict[str, pd.DataFrame]:
        """Build scaled/winsorized features."""
        features = {}

        # Standardize Treasury withholdings
        try:
            treasury_df = self._load_vintage_data("treasury_withholdings")
            if treasury_df is not None and not treasury_df.empty:
                # Extract value column
                value_cols = [c for c in treasury_df.columns if 'withhold' in c.lower() or 'amount' in c.lower()]
                if not value_cols:
                    value_cols = treasury_df.select_dtypes(include=['number']).columns.tolist()
                
                if value_cols:
                    treasury_series = treasury_df[value_cols[0]]
                    if 'date' in treasury_df.columns:
                        treasury_series.index = pd.to_datetime(treasury_df['date'])
                    
                    # Pipeline: winsorize then standardize
                    pipeline = TransformPipeline(
                        [
                            ("winsorize", Winsorizer(lower=0.01, upper=0.99)),
                            ("standardize", StandardScaler()),
                        ]
                    )

                    scaled = pipeline.fit_transform(treasury_series)

                    features["treasury_scaled"] = scaled.to_frame()

                    self._register_feature(
                        "treasury_scaled",
                        source="treasury",
                        transform="winsorize_standardize",
                        frequency="daily",
                    )

                    logger.info("scaling_created", series="treasury")

        except Exception as e:
            logger.error("scaling_failed", series="treasury", error=str(e))

        return features

    def build_aggregations(self) -> Dict[str, pd.DataFrame]:
        """Build state/sector aggregations."""
        features = {}

        # State to national aggregation
        try:
            laus_df = self._load_vintage_data("bls_laus")  # Correct DataSource enum value
            if laus_df is not None and not laus_df.empty:
                # LAUS data has: date, state_name, state_fips, measure, value
                # Find state column (state_fips, state_name, or state)
                state_col = None
                for col in ["state_fips", "state_name", "state"]:
                    if col in laus_df.columns:
                        state_col = col
                        break
                
                # Find employment column
                employment_col = None
                for col in laus_df.columns:
                    if 'employ' in col.lower() and 'unemploy' not in col.lower():
                        employment_col = col
                        break
                
                # Check we have the required columns
                if state_col and employment_col and "date" in laus_df.columns:
                    # Filter to employment_level measure if measure column exists
                    if "measure" in laus_df.columns:
                        laus_df = laus_df[laus_df["measure"] == "employment_level"].copy()
                    
                    aggregator = StateAggregator(agg_method="sum")
                    national = aggregator.aggregate(
                        laus_df,
                        value_col=employment_col,
                        date_col="date",
                        state_col=state_col,
                    )

                    features["laus_national_employment"] = national.to_frame()

                    self._register_feature(
                        "laus_national_employment",
                        source="bls_laus",
                        transform="state_aggregation",
                        frequency="monthly",
                    )

                    logger.info("state_aggregation_created", rows=len(national))
                else:
                    logger.warning("laus_aggregation_skipped_missing_columns", 
                                 columns=list(laus_df.columns),
                                 employment_col=employment_col)

        except Exception as e:
            logger.error("state_aggregation_failed", error=str(e), exc_info=True)

        # Sector to total aggregation
        try:
            ces_df = self._load_vintage_data("bls_ces")  # Correct DataSource enum value
            if ces_df is not None and not ces_df.empty:
                # CES data should have date, series_id or sector, and employment columns
                required_cols = ["date"]
                sector_col = None
                employment_col = None
                
                # Find sector column
                for col in ces_df.columns:
                    if any(x in col.lower() for x in ['sector', 'series', 'industry']):
                        sector_col = col
                        break
                
                # Find employment column
                for col in ces_df.columns:
                    if any(x in col.lower() for x in ['employ', 'payroll', 'value']):
                        employment_col = col
                        break
                
                if sector_col and employment_col and all(col in ces_df.columns for col in required_cols):
                    aggregator = SectorAggregator(agg_method="sum")
                    total_nonfarm = aggregator.aggregate(
                        ces_df,
                        value_col=employment_col,
                        date_col="date",
                        sector_col=sector_col,
                    )

                    features["ces_total_nonfarm"] = total_nonfarm.to_frame()

                    self._register_feature(
                        "ces_total_nonfarm",
                        source="bls_ces",
                        transform="sector_aggregation",
                        frequency="monthly",
                    )

                    logger.info("sector_aggregation_created", rows=len(total_nonfarm))
                else:
                    logger.warning("ces_aggregation_skipped_missing_columns",
                                 columns=list(ces_df.columns),
                                 sector_col=sector_col,
                                 employment_col=employment_col)

        except Exception as e:
            logger.error("sector_aggregation_failed", error=str(e), exc_info=True)

        return features

    def _load_vintage_data(self, data_source: str) -> Optional[pd.DataFrame]:
        """
        Load data from vintage.

        Args:
            data_source: Data source name (DataSource enum value, e.g., 'bls_ces', 'bls_laus')

        Returns:
            DataFrame with vintage data, or None if not found
        """
        try:
            # ETL creates: data/vintages/{source}/{YYYY-MM-DD}/{source}_vintage.parquet
            vintage_path = f"data/vintages/{data_source}/{self.vintage_date}/{data_source}_vintage.parquet"

            if Path(vintage_path).exists():
                df = pd.read_parquet(vintage_path)
                
                # CRITICAL: Validate this is production data, not synthetic test data
                try:
                    validate_vintage_is_production(df, Path(vintage_path), strict=True)
                except Exception as e:
                    logger.error(
                        f"❌ Vintage validation failed for {data_source}",
                        error=str(e)
                    )
                    # Re-raise to prevent using synthetic data in production
                    raise
                
                logger.info(
                    "vintage_data_loaded",
                    source=data_source,
                    vintage=self.vintage_date,
                    rows=len(df),
                    columns=list(df.columns),
                )
                return df

            logger.warning("vintage_data_not_found", source=data_source, vintage=self.vintage_date, expected_path=vintage_path)
            return None

        except Exception as e:
            logger.error("vintage_data_load_failed", source=data_source, error=str(e))
            return None

    def _register_feature(
        self, name: str, source: str, transform: str, frequency: str
    ) -> None:
        """Register feature in registry."""
        try:
            self.registry.register(
                {
                    "name": name,
                    "source": source,
                    "transform": transform,
                    "frequency": frequency,
                    "vintage_date": self.vintage_date,
                    "status": "production",
                }
            )
        except Exception as e:
            logger.error("feature_registration_failed", feature=name, error=str(e))

    def _save_features(self, features: Dict[str, pd.DataFrame]) -> None:
        """Save features to disk."""
        for feature_name, feature_df in features.items():
            output_path = self.output_dir / f"{feature_name}.parquet"
            feature_df.to_parquet(output_path)
            logger.info("feature_saved", name=feature_name, path=str(output_path))


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Build features from vintage data")
    parser.add_argument(
        "--vintage-date",
        type=str,
        required=True,
        help="Vintage date (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="data/features",
        help="Output directory for features",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Build all features",
    )
    parser.add_argument(
        "--midas-only",
        action="store_true",
        help="Build only MIDAS features",
    )
    parser.add_argument(
        "--aggregations-only",
        action="store_true",
        help="Build only aggregations",
    )

    args = parser.parse_args()

    logger.info(
        "starting_feature_builder",
        vintage_date=args.vintage_date,
        output_dir=args.output_dir,
    )

    # Initialize builder
    builder = FeatureBuilder(
        vintage_date=args.vintage_date,
        output_dir=Path(args.output_dir),
    )

    # Build features based on flags
    if args.all or (not args.midas_only and not args.aggregations_only):
        features = builder.build_all()
    elif args.midas_only:
        features = builder.build_midas_features()
    elif args.aggregations_only:
        features = builder.build_aggregations()
    else:
        logger.error("no_feature_type_specified")
        sys.exit(1)

    logger.info("feature_builder_complete", feature_count=len(features))
    print(f"✅ Built {len(features)} feature sets")
    print(f"✅ Saved to {args.output_dir}")


if __name__ == "__main__":
    main()

