# Phase 6.2.0 CRITICAL FINDING: Series-Type Regressor Mismatch

**Date:** 2025-11-30  
**Discovery:** Post-investigation codebase search  
**Severity:** HIGH - Methodological Error in Testing  

---

## Executive Summary

**CRITICAL DISCOVERY:** The golden diagnostics baseline and Phase 6.2.0 investigation were testing **unemployment rate series with employment-focused regressors**, which is methodologically incorrect per the system's own design.

**Impact:** This explains why:
1. ✅ Regressors are technically applied (pipeline works)
2. ❌ Regressors are not statistically significant (wrong regressors for series type)
3. ❌ Q-statistics are poor for LASST060000000000003 (unemployment rate)

**Resolution:** Fixed `record_golden_diagnostics.py` and `test_regressors_impact.py` to use series-type-appropriate regressor configurations.

---

## The Problem

### Series in Golden Diagnostics

**Three series being tested:**
1. `CES0000000001` - Total Nonfarm Payrolls (employment COUNT)
2. `CES0500000003` - Total Private Employment (employment COUNT)
3. `LASST060000000000003` - California Unemployment Rate (unemployment RATE)

### Configuration Used (INCORRECT)

**Before Fix:** All three series received the SAME regressor configuration:
- `use_holiday_regressors`: Default `True`
- `use_strike_regressors`: Default `True`
- `use_weather_regressors`: Default `True`
- `mode`: Default `"mult"`
- `easter`: Default `True`
- `trading_day`: Default `True`

**Problem:** Unemployment rates are NOT employment counts. They measure different things and have different seasonal properties.

---

## System Design Intent

### Evidence from `scripts/run_seasonal_adjustment.py`

The system has **explicit series-type differentiation**:

#### Employment Counts (CES Series)
```python
"ces_nfp": {
    "mode": "mult",                    # Multiplicative
    "easter": True,
    "trading_day": True,
    "use_holiday_regressors": True,    # ✅ ENABLED
    "use_strike_regressors": True,     # ✅ ENABLED
    "use_weather_regressors": False,   # National aggregate less affected
},
```

#### Unemployment Rates (LAUS Series)
```python
"laus_unemployment": {
    "mode": "add",                     # ❌ ADDITIVE (not multiplicative)
    "easter": False,                   # ❌ DISABLED
    "trading_day": False,              # ❌ DISABLED
    "use_holiday_regressors": False,  # ❌ DISABLED - "Rates typically don't need"
    "use_strike_regressors": False,   # ❌ DISABLED - "Rates are smoothed, less affected"
    "use_weather_regressors": False,  # ❌ DISABLED
},
```

**Comments in code (lines 55-57):**
- "Rates typically don't need holiday regressors"
- "Rates are smoothed, less affected"

---

## Why This Matters

### Different Data Sources, Different Properties

**CES (Current Employment Statistics) - Establishment Survey:**
- Surveys ~144,000 businesses and government agencies
- Measures payroll employment (jobs)
- Captures: Total nonfarm payrolls, private sector, sectors
- **Directly affected by:** Strikes (workers off payroll), holidays (hiring timing), weather (business closures)

**LAUS (Local Area Unemployment Statistics) - Household Survey:**
- Derived from CPS (Current Population Survey)
- Surveys ~60,000 households
- Measures: Unemployment rate, labor force participation
- **Smoothed, less affected by:** Short-term events like strikes, holidays, weather
- Uses different seasonal adjustment methodology

### Methodological Implications

1. **Strike Regressors on Unemployment Rates:**
   - Strike: Workers off payroll (CES drops)
   - Strike: Workers still "employed" in household survey (unemployment rate unchanged)
   - **Applying strike regressors to unemployment rates is methodologically wrong**

2. **Holiday Regressors on Unemployment Rates:**
   - Holiday timing affects establishment hiring patterns (CES)
   - Holiday timing doesn't affect household survey responses (unemployment rate)
   - **Applying holiday regressors to unemployment rates adds noise**

3. **Additive vs Multiplicative:**
   - Employment counts grow exponentially (use multiplicative: `mode="mult"`)
   - Unemployment rates are percentages (use additive: `mode="add"`)
   - **Wrong mode compounds seasonal adjustment errors**

---

## Evidence from Phase 6.2.0 Investigation

### Statistical Results

**LASST060000000000003 (CA Unemployment Rate) with WRONG regressors:**
```
Variable                     Estimate        Std Error      t-value
easter_timing                -0.0411         0.02446        -1.68    (marginal)
thanksgiving_timing           0.0033         0.01789         0.18    (not significant)
labor_day_timing             -0.0093         0.02310        -0.40    (not significant)

Group test: p-value = not reported (but likely not significant)
```

**Compare to CES series (employment counts) with CORRECT regressors:**
```
CES0000000001:
easter_timing                 0.0067         0.00387         1.74    (marginal)
thanksgiving_timing           0.0002         0.00288         0.07    (not significant)
labor_day_timing             -0.0003         0.00358        -0.09    (not significant)

Group test: p-value = 0.39 (not significant)
```

**Both show weak signal because:**
1. CES series: Holiday timing regressors too coarse (design issue)
2. LAUS series: Holiday timing regressors inappropriate (methodological error)

---

## Root Cause Analysis

### Pipeline Defaults

**File:** `seasonal/pipeline.py` (lines 181-204)

```python
# Holiday regressors
if config.get("use_holiday_regressors", True):  # ← Defaults to TRUE
    ...
    
# Strike regressors  
if config.get("use_strike_regressors", True):  # ← Defaults to TRUE
    ...
```

**Problem:** Pipeline defaults ALL regressors to `True`, which is:
- ✅ Correct for employment counts (CES)
- ❌ WRONG for unemployment rates (LAUS)

### Missing Configuration in Golden Diagnostics

**File:** `scripts/record_golden_diagnostics.py` (lines 39-52, before fix)

```python
MONITORED_SERIES = {
    "CES0000000001": {
        "name": "Total Nonfarm Payrolls",
        "source": "bls_ces",
        # ❌ NO CONFIG SPECIFIED - uses pipeline defaults
    },
    ...
    "LASST060000000000003": {
        "name": "California Unemployment Rate",
        "source": "bls_laus",
        # ❌ NO CONFIG SPECIFIED - uses pipeline defaults (WRONG for rates)
    },
}
```

**Result:** All series get default configuration (all regressors enabled), which is wrong for unemployment rates.

---

## The Fix

### Updated Configuration

**File:** `scripts/record_golden_diagnostics.py` (after fix)

```python
MONITORED_SERIES = {
    "CES0000000001": {
        "name": "Total Nonfarm Payrolls",
        "source": "bls_ces",
        "series_type": "employment_count",
        "config": {
            "mode": "mult",
            "easter": True,
            "trading_day": True,
            "use_holiday_regressors": True,
            "use_strike_regressors": True,
            "use_weather_regressors": False,
        },
    },
    ...
    "LASST060000000000003": {
        "name": "California Unemployment Rate",
        "source": "bls_laus",
        "series_type": "unemployment_rate",
        "config": {
            "mode": "add",                     # ✅ ADDITIVE for rates
            "easter": False,                   # ✅ No built-in Easter
            "trading_day": False,              # ✅ No trading day
            "use_holiday_regressors": False,  # ✅ No holiday regressors
            "use_strike_regressors": False,   # ✅ No strike regressors
            "use_weather_regressors": False,  # ✅ No weather regressors
        },
    },
}
```

### Updated Pipeline Call

```python
# Get series-specific config (with defaults for backward compatibility)
series_config = series_info.get("config", {})
series_config["frequency"] = "monthly"

result = pipeline.run(
    series_name=series_id,
    series_data=series_data,
    start_date=series_data.index[0].date(),
    config=series_config  # ✅ Use series-type-appropriate config
)
```

---

## Expected Impact

### After Re-Running Golden Diagnostics

**CES Series (employment counts):**
- Same results as before (already using correct configuration)
- Q-statistics may still be poor (weak holiday regressor signal)
- Strike/weather regressors should now show in output (data fixed)

**LASST060000000000003 (unemployment rate):**
- **Expect BETTER Q-statistics** (no inappropriate regressors)
- No user-defined regressors in regression table
- Only built-in seasonal pattern detection
- Residuals should be MORE random (not less)

### Why Q-Statistics Should Improve

**Before (WRONG config):**
- X-13 trying to fit employment-focused regressors to unemployment rate
- Regressors add noise, not signal
- Residuals contain both:
  - True seasonal pattern (unmodeled)
  - Noise from inappropriate regressors
- Result: Poor Q-statistics (residuals not random)

**After (CORRECT config):**
- X-13 using only appropriate seasonal adjustment (no external regressors)
- Unemployment rate has smoother seasonal pattern
- Residuals contain only true randomness
- Result: Better Q-statistics (residuals more random)

---

## Lessons Learned

### 1. **Test Configuration Matters as Much as Code**

The pipeline code is CORRECT. The test configuration was WRONG.
- ✅ Technical implementation: Working
- ❌ Test methodology: Flawed

### 2. **Series-Type Differentiation is Critical**

Employment counts ≠ Unemployment rates
- Different data sources
- Different seasonal properties
- Different appropriate adjustments

### 3. **Defaults Can Hide Errors**

Pipeline defaulting to `True` for all regressors is convenient for employment counts but dangerous for other series types.

### 4. **Domain Knowledge Required**

Understanding BLS methodology is ESSENTIAL:
- CES vs LAUS
- Establishment survey vs household survey
- Multiplicative vs additive seasonal adjustment

### 5. **"Working Correctly" ≠ "Working Appropriately"**

Phase 6.2.0 investigation correctly concluded:
- ✅ Regressors ARE being applied
- ✅ Pipeline is working correctly

But missed:
- ❌ Wrong regressors for unemployment rate
- ❌ Configuration error, not code bug

---

## Recommendations

### Immediate (Phase 6.2.0 Completion)

1. **Re-Run Golden Diagnostics** with corrected configurations
   ```bash
   python scripts/record_golden_diagnostics.py --vintage-date 2025-11-29 --record
   ```

2. **Compare Before/After Q-Statistics:**
   - CES series: Expect similar results (configuration unchanged)
   - LAUS series: Expect IMPROVED results (configuration corrected)

3. **Document Findings:**
   - Update Phase 6.2.0 reports with this discovery
   - Note that original hypothesis was partially correct

### Short-Term (Phase 6.2+)

4. **Add Series-Type Validation:**
   - Pipeline should warn if unemployment rate gets employment regressors
   - Configuration validation layer

5. **Improve Pipeline Defaults:**
   - Consider making defaults `None` (explicit required)
   - Or add series-type parameter to auto-configure

6. **Add Documentation:**
   - Document series-type-appropriate configurations
   - BLS methodology guide (CES vs LAUS)

### Long-Term (Post Phase 6)

7. **Configuration Management:**
   - Move to YAML config files per series
   - Validate configurations against series type

8. **Automated Testing:**
   - Test that employment counts get employment config
   - Test that unemployment rates get rate config
   - Catch configuration mismatches

---

## Files Modified

1. `scripts/record_golden_diagnostics.py` - Added series-type-appropriate configs
2. `scripts/test_regressors_impact.py` - Updated to use correct configs
3. `docs/planning/PHASE_6_2_0_CRITICAL_FINDING_SERIES_TYPE_MISMATCH.md` - This document

---

## References

- `scripts/run_seasonal_adjustment.py` (lines 25-70) - Correct series-type configurations
- `docs/ACCURACY_MAP.md` (lines 142-147) - Regressor accuracy improvements
- `docs/PROJECT_INSTRUCTIONS.md` (lines 58-66) - Original regressor requirements
- Phase 6.2.0 investigation reports

---

**Conclusion:** This finding changes the interpretation of Phase 6.2.0 results. The pipeline works correctly, but we were testing unemployment rates with employment configurations. Correcting this should improve Q-statistics for the unemployment rate series.

**Status:** ✅ **FIXED** - Configuration corrected, ready for re-baseline

