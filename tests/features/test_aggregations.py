"""
Tests for state and sector aggregations.

Tests hierarchical aggregation for:
- State-level LAUS → National totals
- Sector-level CES → Total nonfarm payrolls

All aggregations must preserve coherence (sum of parts = total).
"""

import numpy as np
import pandas as pd
import pytest


class TestStateAggregator:
    """Test state-to-national aggregation."""

    @pytest.fixture
    def state_employment_data(self) -> pd.DataFrame:
        """Create sample state employment data."""
        dates = pd.date_range("2024-01-01", periods=12, freq="MS")
        states = ["CA", "TX", "NY", "FL", "IL"]

        data = []
        for state in states:
            for date in dates:
                data.append(
                    {
                        "date": date,
                        "state": state,
                        "employment": np.random.RandomState(42).randint(1_000_000, 20_000_000),
                        "unemployment": np.random.RandomState(42).randint(50_000, 1_000_000),
                        "labor_force": np.random.RandomState(42).randint(1_100_000, 21_000_000),
                    }
                )

        return pd.DataFrame(data)

    @pytest.fixture
    def state_populations(self) -> pd.DataFrame:
        """Create sample state population data."""
        return pd.DataFrame(
            {
                "state": ["CA", "TX", "NY", "FL", "IL"],
                "population": [39_500_000, 29_000_000, 19_500_000, 21_500_000, 12_700_000],
            }
        )

    def test_state_aggregator_initialization(self):
        """Test StateAggregator initialization."""
        from features.aggregations.state_aggregator import StateAggregator

        aggregator = StateAggregator(agg_method="sum", weighted=False)
        assert aggregator.agg_method == "sum"
        assert aggregator.weighted is False

    def test_sum_aggregation(self, state_employment_data):
        """Test simple sum aggregation (no weights)."""
        from features.aggregations.state_aggregator import StateAggregator

        aggregator = StateAggregator(agg_method="sum", weighted=False)
        national = aggregator.aggregate(
            state_employment_data, value_col="employment", date_col="date", state_col="state"
        )

        # Check output
        assert isinstance(national, pd.Series)
        assert len(national) == 12  # 12 months

        # Verify sums are correct
        for date in national.index:
            state_total = state_employment_data[state_employment_data["date"] == date][
                "employment"
            ].sum()
            assert np.isclose(national.loc[date], state_total)

    def test_weighted_aggregation(self, state_employment_data, state_populations):
        """Test population-weighted aggregation."""
        from features.aggregations.state_aggregator import StateAggregator

        aggregator = StateAggregator(agg_method="weighted_mean", weighted=True)
        result = aggregator.aggregate(
            state_employment_data,
            value_col="employment",
            date_col="date",
            state_col="state",
            weights=state_populations,
            weight_col="population",
        )

        # Check output
        assert isinstance(result, pd.Series)
        assert len(result) == 12

    def test_coherence_check(self, state_employment_data):
        """Test that sum of states equals national total (coherence)."""
        from features.aggregations.state_aggregator import StateAggregator

        aggregator = StateAggregator(agg_method="sum")
        national = aggregator.aggregate(
            state_employment_data, value_col="employment", date_col="date", state_col="state"
        )

        # Manually sum states for each date
        for date in national.index:
            manual_sum = state_employment_data[state_employment_data["date"] == date][
                "employment"
            ].sum()
            # Should be coherent (sum of states = national)
            assert np.isclose(national.loc[date], manual_sum, rtol=1e-6)

    def test_all_states_aggregation(self):
        """Test aggregation of all 50 states + DC."""
        from features.aggregations.state_aggregator import StateAggregator

        # Create data for all states
        dates = pd.date_range("2024-01-01", periods=3, freq="MS")
        states = ["CA", "TX", "NY"]  # Simplified for test

        data = []
        for state in states:
            for date in dates:
                data.append(
                    {
                        "date": date,
                        "state": state,
                        "employment": 1_000_000,
                    }
                )

        df = pd.DataFrame(data)

        aggregator = StateAggregator(agg_method="sum")
        national = aggregator.aggregate(
            df, value_col="employment", date_col="date", state_col="state"
        )

        # Should sum all states
        assert np.isclose(national.iloc[0], 3_000_000)  # 3 states * 1M each

    def test_missing_state_handling(self, state_employment_data):
        """Test handling of missing state data."""
        from features.aggregations.state_aggregator import StateAggregator

        # Remove one state from one month
        df = state_employment_data.copy()
        df = df[~((df["date"] == df["date"].iloc[0]) & (df["state"] == "CA"))]

        aggregator = StateAggregator(agg_method="sum", handle_missing="fill_zero")
        national = aggregator.aggregate(
            df, value_col="employment", date_col="date", state_col="state"
        )

        # Should still produce result
        assert len(national) == 12
        assert not national.isna().any()


class TestSectorAggregator:
    """Test sector-to-total aggregation for CES data."""

    @pytest.fixture
    def sector_employment_data(self) -> pd.DataFrame:
        """Create sample sector employment data."""
        dates = pd.date_range("2024-01-01", periods=12, freq="MS")
        sectors = [
            "retail_trade",
            "leisure_hospitality",
            "manufacturing",
            "construction",
            "professional_business",
        ]

        data = []
        for sector in sectors:
            for date in dates:
                data.append(
                    {
                        "date": date,
                        "sector": sector,
                        "employment": np.random.RandomState(42).randint(500_000, 5_000_000),
                    }
                )

        return pd.DataFrame(data)

    def test_sector_aggregator_initialization(self):
        """Test SectorAggregator initialization."""
        from features.aggregations.sector_aggregator import SectorAggregator

        aggregator = SectorAggregator(agg_method="sum")
        assert aggregator.agg_method == "sum"

    def test_sum_aggregation(self, sector_employment_data):
        """Test simple sum aggregation of sectors."""
        from features.aggregations.sector_aggregator import SectorAggregator

        aggregator = SectorAggregator(agg_method="sum")
        total_nonfarm = aggregator.aggregate(
            sector_employment_data,
            value_col="employment",
            date_col="date",
            sector_col="sector",
        )

        # Check output
        assert isinstance(total_nonfarm, pd.Series)
        assert len(total_nonfarm) == 12

        # Verify sums
        for date in total_nonfarm.index:
            sector_total = sector_employment_data[sector_employment_data["date"] == date][
                "employment"
            ].sum()
            assert np.isclose(total_nonfarm.loc[date], sector_total)

    def test_weighted_aggregation(self, sector_employment_data):
        """Test employment-weighted aggregation of sectors."""
        from features.aggregations.sector_aggregator import SectorAggregator

        # Create sector weights (based on employment share)
        sector_weights = pd.DataFrame(
            {
                "sector": [
                    "retail_trade",
                    "leisure_hospitality",
                    "manufacturing",
                    "construction",
                    "professional_business",
                ],
                "weight": [0.25, 0.20, 0.15, 0.10, 0.30],
            }
        )

        aggregator = SectorAggregator(agg_method="weighted_sum")
        result = aggregator.aggregate(
            sector_employment_data,
            value_col="employment",
            date_col="date",
            sector_col="sector",
            weights=sector_weights,
            weight_col="weight",
        )

        assert len(result) == 12

    def test_coherence_check(self, sector_employment_data):
        """Test that sum of sectors equals total (coherence)."""
        from features.aggregations.sector_aggregator import SectorAggregator

        aggregator = SectorAggregator(agg_method="sum")
        total = aggregator.aggregate(
            sector_employment_data,
            value_col="employment",
            date_col="date",
            sector_col="sector",
        )

        # Manually compute totals
        for date in total.index:
            manual_sum = sector_employment_data[sector_employment_data["date"] == date][
                "employment"
            ].sum()
            assert np.isclose(total.loc[date], manual_sum, rtol=1e-6)

    def test_subset_sectors(self, sector_employment_data):
        """Test aggregation of subset of sectors."""
        from features.aggregations.sector_aggregator import SectorAggregator

        # Only aggregate retail and leisure
        subset = sector_employment_data[
            sector_employment_data["sector"].isin(["retail_trade", "leisure_hospitality"])
        ]

        aggregator = SectorAggregator(agg_method="sum")
        result = aggregator.aggregate(
            subset, value_col="employment", date_col="date", sector_col="sector"
        )

        # Should sum only those two sectors
        assert len(result) == 12
        for date in result.index:
            manual_sum = subset[subset["date"] == date]["employment"].sum()
            assert np.isclose(result.loc[date], manual_sum)


class TestHierarchicalCoherence:
    """Test hierarchical coherence constraints."""

    def test_mint_structure_preparation(self):
        """Test preparation of data for MinT reconciliation."""
        from features.aggregations.hierarchical import prepare_mint_structure

        # Create hierarchical data (national → states → sectors)
        data = {
            "date": pd.date_range("2024-01-01", periods=3, freq="MS"),
            "national": [150_000, 155_000, 160_000],
            "CA": [40_000, 41_000, 42_000],
            "TX": [30_000, 31_000, 32_000],
            "NY": [25_000, 26_000, 27_000],
        }
        df = pd.DataFrame(data).set_index("date")

        structure = prepare_mint_structure(df)

        # Should have coherence matrix
        assert "summing_matrix" in structure
        assert "forecasts" in structure

    def test_coherence_validation(self):
        """Test validation that sum of components equals total."""
        from features.aggregations.hierarchical import validate_coherence

        # Create coherent data
        dates = pd.date_range("2024-01-01", periods=3, freq="MS")
        data = pd.DataFrame(
            {
                "date": dates,
                "total": [100, 110, 120],
                "part1": [60, 66, 72],
                "part2": [40, 44, 48],
            }
        )

        # Should pass coherence check
        is_coherent = validate_coherence(data, total_col="total", component_cols=["part1", "part2"])
        assert is_coherent is True

    def test_incoherence_detection(self):
        """Test detection of incoherent data."""
        from features.aggregations.hierarchical import validate_coherence

        # Create incoherent data (parts don't sum to total)
        dates = pd.date_range("2024-01-01", periods=3, freq="MS")
        data = pd.DataFrame(
            {
                "date": dates,
                "total": [100, 110, 120],
                "part1": [50, 55, 60],  # Don't sum to total
                "part2": [40, 44, 48],
            }
        )

        # Should fail coherence check
        is_coherent = validate_coherence(data, total_col="total", component_cols=["part1", "part2"])
        assert is_coherent is False


class TestAggregationUtilities:
    """Test aggregation utility functions."""

    def test_compute_employment_weights(self):
        """Test computation of employment-based weights."""
        from features.aggregations.utils import compute_employment_weights

        employment = pd.Series(
            [10_000, 20_000, 30_000, 40_000], index=["sector1", "sector2", "sector3", "sector4"]
        )

        weights = compute_employment_weights(employment)

        # Weights should sum to 1
        assert np.isclose(weights.sum(), 1.0)
        # Sector4 (40K) should have largest weight
        assert weights["sector4"] == weights.max()

    def test_compute_population_weights(self):
        """Test computation of population-based weights."""
        from features.aggregations.utils import compute_population_weights

        population = pd.Series(
            [1_000_000, 2_000_000, 3_000_000], index=["state1", "state2", "state3"]
        )

        weights = compute_population_weights(population)

        # Weights should sum to 1
        assert np.isclose(weights.sum(), 1.0)
        # State3 should have largest weight
        assert weights["state3"] == weights.max()
