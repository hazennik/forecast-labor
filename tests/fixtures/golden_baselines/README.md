# Golden Baselines for Regression Testing

This directory contains golden baseline files for determinism and quality regression testing.

## Files

### `vintage_hashes.json`
- **Purpose:** SHA256 hashes of pinned vintage data for reproducibility testing
- **Populated by:** `scripts/verify_vintage_determinism.py --vintage-date 2024-01-15 --record`
- **Used by:** CI pipeline to verify data hasn't changed unexpectedly
- **Pinned vintage date:** 2024-01-15

### `golden_seasonal_diagnostics.json`
- **Purpose:** X-13ARIMA-SEATS diagnostic statistics (M-stats, Q-stats) baseline
- **Populated by:** `scripts/record_golden_diagnostics.py --vintage-date 2024-01-15 --record`
- **Used by:** CI pipeline to detect seasonal adjustment quality regressions
- **Monitored series:** Total NFP, Private Employment, Retail, Leisure/Hospitality

## Usage

### First-Time Setup

1. **Generate vintage data** (if not already present):
   ```bash
   make seed  # Runs seed_public_data.py for all 7 data sources
   ```

2. **Record vintage hashes**:
   ```bash
   python scripts/verify_vintage_determinism.py --vintage-date 2024-01-15 --record
   ```

3. **Record golden diagnostics**:
   ```bash
   python scripts/record_golden_diagnostics.py --vintage-date 2024-01-15 --record
   ```

### CI Validation

CI runs these checks on every commit:

```yaml
- name: Verify vintage determinism
  run: python scripts/verify_vintage_determinism.py --vintage-date 2024-01-15 --verify

- name: Check golden diagnostics  
  run: python scripts/record_golden_diagnostics.py --vintage-date 2024-01-15 --verify
```

**These checks will FAIL the build** if:
- Vintage data hashes don't match (data changed unexpectedly)
- Seasonal diagnostics degrade beyond acceptable thresholds
- Required vintage data is missing

## Quality Thresholds

### M-Statistics (Seasonal Adjustment Quality)
- M7, M8, M9, M10, M11 should be ≤ 1.0 (acceptable quality)
- Any value > 1.0 indicates potential problems

### Q-Statistics (Ljung-Box Test)
- Q-stat p-value > 0.05 indicates no remaining autocorrelation (good)
- p-value ≤ 0.05 may indicate model inadequacy

## Updating Baselines

Baselines should only be updated when:
1. Intentional changes to ETL or seasonal adjustment logic
2. Upgrading X-13 service version
3. Fixing known data quality issues

**Process:**
1. Review changes carefully
2. Re-record baselines with `--record` flag
3. Document reason for update in commit message
4. Get code review approval

## Important Notes

- ⚠️ **Never commit empty/null baseline files to main branch**
- ⚠️ **CI should fail if baselines aren't populated**
- ⚠️ **Synthetic data should never be used for golden baselines**
- ✅ **Always use real vintage data from pinned date (2024-01-15)**

