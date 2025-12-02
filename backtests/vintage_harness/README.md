# Vintage Harness

Reconstructs historical data states for vintage-honest backtesting.

## Purpose

The Vintage Harness ensures **no data leakage** during backtesting by reconstructing "what was known then" at specific points in time. This is critical for accurate evaluation of forecasting models.

## Key Concept: Vintage Honesty

**Vintage honesty** means that when evaluating a forecast made on date X, you only use data that would have been available on or before date X.

**Example:**
- Backtest date: 2024-02-15
- CES data: Latest vintage on 2024-02-01 (published Feb 1)
- LAUS data: Latest vintage on 2024-01-15 (published Jan 15)
- ❌ **WRONG**: Use 2024-03-01 vintage (not available yet on Feb 15!)
- ✅ **RIGHT**: Use 2024-02-01 vintage for CES, 2024-01-15 for LAUS

The Vintage Harness automatically selects the correct vintages.

## Quick Start

```python
from datetime import date
from backtests.vintage_harness import VintageHarness

# Initialize harness
harness = VintageHarness(Path("data/vintages"))

# Reconstruct state as of Feb 15, 2024
state = harness.reconstruct_state(
    as_of_date=date(2024, 2, 15),
    sources=["ces", "laus", "claims"]
)

# Access reconstructed data
ces_data = state.data["ces"]
laus_data = state.data["laus"]

# Check which vintage was used
ces_vintage_date = state.vintage_dates["ces"]  # date(2024, 2, 1)

# Validate no future data leakage
is_valid, errors = harness.validate_vintage_honesty(state)
if not is_valid:
    print(f"Validation errors: {errors}")
```

## Core Components

### VintageHarness

Main class for reconstructing historical states.

**Methods:**
- `reconstruct_state()` - Reconstruct data state for a date
- `validate_vintage_honesty()` - Validate no future data leakage
- `get_available_backtest_dates()` - Find dates with complete data

### ReconstructedState

Dataclass representing a reconstructed historical state.

**Attributes:**
- `as_of_date` - Date for which state was reconstructed
- `data` - Dict[str, DataFrame] mapping sources to data
- `vintage_dates` - Dict[str, date] mapping sources to vintage dates used
- `sources_requested` - List of requested sources
- `sources_available` - List of successfully loaded sources
- `metadata` - Additional reconstruction metadata

### VintageReconstructionError

Exception raised when reconstruction fails (e.g., no vintage available).

## Usage Examples

### Basic Reconstruction

```python
harness = VintageHarness(Path("data/vintages"))

state = harness.reconstruct_state(
    as_of_date=date(2024, 2, 15),
    sources=["ces", "laus"]
)

print(f"Reconstructed {len(state.sources_available)} sources")
print(f"Vintage dates: {state.vintage_dates}")
```

### Partial Reconstruction (Some Sources Missing)

```python
# Allow partial reconstruction if some sources unavailable
state = harness.reconstruct_state(
    as_of_date=date(2024, 2, 15),
    sources=["ces", "laus", "maybe_missing"],
    allow_partial=True  # Don't fail if maybe_missing is unavailable
)

print(f"Requested: {state.sources_requested}")
print(f"Available: {state.sources_available}")
```

### Validate Vintage Honesty

```python
state = harness.reconstruct_state(
    as_of_date=date(2024, 2, 15),
    sources=["ces"]
)

is_valid, errors = harness.validate_vintage_honesty(state)

if is_valid:
    print("✅ No data leakage detected")
else:
    print(f"❌ Data leakage found: {errors}")
```

### Find Available Backtest Dates

```python
# Find all dates with complete data for ces and laus
backtest_dates = harness.get_available_backtest_dates(
    sources=["ces", "laus"],
    start_date=date(2023, 1, 1),
    end_date=date(2024, 12, 31)
)

print(f"Found {len(backtest_dates)} backtest-ready dates")

# Run backtest on each date
for backtest_date in backtest_dates:
    state = harness.reconstruct_state(
        as_of_date=backtest_date,
        sources=["ces", "laus"]
    )
    # ... run model training/evaluation ...
```

### Full Backtest Workflow

```python
from datetime import date
from pathlib import Path
from backtests.vintage_harness import VintageHarness

def run_backtest(model, as_of_date: date):
    """Run vintage-honest backtest for a single date."""
    
    # Initialize harness
    harness = VintageHarness(Path("data/vintages"))
    
    # Reconstruct historical state
    state = harness.reconstruct_state(
        as_of_date=as_of_date,
        sources=["ces", "laus", "claims"]
    )
    
    # Validate vintage honesty
    is_valid, errors = harness.validate_vintage_honesty(state)
    if not is_valid:
        raise ValueError(f"Data leakage detected: {errors}")
    
    # Train model on historical data
    model.fit(
        ces_data=state.data["ces"],
        laus_data=state.data["laus"],
        claims_data=state.data["claims"],
        vintage_date=as_of_date
    )
    
    # Make prediction
    prediction = model.predict()
    
    return prediction

# Run backtest across multiple dates
backtest_dates = [date(2024, i, 1) for i in range(1, 13)]

for backtest_date in backtest_dates:
    prediction = run_backtest(my_model, backtest_date)
    print(f"Prediction for {backtest_date}: {prediction}")
```

## Edge Cases Handled

### Missing Sources

If a requested source has no vintage available:

```python
try:
    state = harness.reconstruct_state(
        as_of_date=date(2024, 2, 15),
        sources=["nonexistent"]
    )
except VintageReconstructionError as e:
    print(f"Error: {e}")  # No vintage available for 'nonexistent'
```

### Short Series

Sources with insufficient history are still returned:

```python
state = harness.reconstruct_state(
    as_of_date=date(2024, 1, 15),
    sources=["short_series"]  # Only 3 observations
)

print(f"Rows: {len(state.data['short_series'])}")  # 3 rows
```

### Before First Vintage

If as_of_date is before any vintages exist:

```python
try:
    state = harness.reconstruct_state(
        as_of_date=date(2019, 1, 1),  # Before any vintages
        sources=["ces"]
    )
except VintageReconstructionError as e:
    print(f"Error: {e}")  # No vintage available on or before 2019-01-01
```

## Performance

**Benchmarks** (4 sources, ~100 rows each):
- Reconstruction: **< 1 second**
- Validation: **< 0.1 second**

For large-scale backtests:
- Cache loaded vintages if reconstructing multiple times for same date
- Use `get_available_backtest_dates()` to avoid failed reconstructions
- Consider parallel processing for multiple backtest dates

## Testing

Run tests:
```bash
pytest tests/backtests/test_vintage_harness.py -v
```

Run standalone verification:
```bash
python scripts/verify_vintage_harness.py
```

## Architecture

```
VintageHarness
├── Uses: VintageManager (etl.common.vintage)
│   ├── list_vintages(source) → List[date]
│   ├── get_vintage_as_of(source, date) → DataFrame
│   └── load_vintage(source, date) → DataFrame
│
├── Returns: ReconstructedState
│   ├── as_of_date: date
│   ├── data: Dict[str, DataFrame]
│   ├── vintage_dates: Dict[str, date]
│   └── metadata: Dict
│
└── Validates: Vintage Honesty
    ├── Vintage dates ≤ as_of_date
    ├── Data timestamps ≤ vintage_date
    └── No future data after as_of_date
```

## Design Principles

1. **Immutability**: Vintages are never modified (append-only)
2. **Determinism**: Same as_of_date + sources = identical reconstruction
3. **Validation**: Three-level checks prevent data leakage
4. **Flexibility**: `allow_partial` supports incomplete source sets
5. **Performance**: Lazy loading, minimal overhead

## See Also

- **VintageManager**: `etl/common/vintage.py`
- **Test Suite**: `tests/backtests/test_vintage_harness.py`
- **Completion Summary**: `docs/planning/PHASE_6_2_1_COMPLETION_SUMMARY.md`
- **Implementation Status**: `docs/planning/IMPLEMENTATION_STATUS.md`

## Contributing

When modifying the harness:
1. Write tests first (TDD)
2. Ensure all tests pass
3. Update this README if interface changes
4. Validate vintage honesty checks remain comprehensive

