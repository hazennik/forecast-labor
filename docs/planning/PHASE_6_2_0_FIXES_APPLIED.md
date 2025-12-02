# Phase 6.2.0 Fixes Applied - Series-Type Configuration Correction

**Date:** 2025-11-30  
**Type:** Configuration Fix (Methodological Error)  
**Severity:** HIGH  
**Status:** ✅ FIXED

---

## Summary

Fixed a critical methodological error: **Unemployment rate series (LASST060000000000003) was being tested with employment-focused regressors**, which is incorrect per the system's design.

---

## What Was Wrong

### The Problem

**Golden diagnostics testing used INCORRECT configurations:**

```python
# Before (WRONG): All series got same default config
MONITORED_SERIES = {
    "CES0000000001": {...},        # Employment count
    "CES0500000003": {...},        # Employment count  
    "LASST060000000000003": {...}, # Unemployment RATE
}

# All series received:
# - use_holiday_regressors: True  (default)
# - use_strike_regressors: True   (default)
# - use_weather_regressors: True  (default)
# - mode: "mult"                  (default)
```

**Why This is Wrong:**
- Employment COUNTS (CES) and unemployment RATES (LAUS) are different series types
- They come from different surveys (establishment vs household)
- They have different seasonal properties
- They require different seasonal adjustment approaches

### Evidence from System Design

**File:** `scripts/run_seasonal_adjustment.py`

The system already has **correct configurations** for different series types:

**Employment Counts (CES):**
```python
"ces_nfp": {
    "mode": "mult",
    "use_holiday_regressors": True,
    "use_strike_regressors": True,
    "use_weather_regressors": False,
}
```

**Unemployment Rates (LAUS):**
```python
"laus_unemployment": {
    "mode": "add",                    # Different mode!
    "use_holiday_regressors": False,  # No holiday regressors!
    "use_strike_regressors": False,   # No strike regressors!
    "use_weather_regressors": False,  # No weather regressors!
}
```

**Comment in code:** `"Rates typically don't need holiday regressors"` and `"Rates are smoothed, less affected"`

---

## What Was Fixed

### File 1: `scripts/record_golden_diagnostics.py`

**Added series-type-specific configurations:**

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
    "CES0500000003": {
        "name": "Total Private Employment",
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
    "LASST060000000000003": {  # ← UNEMPLOYMENT RATE
        "name": "California Unemployment Rate",
        "source": "bls_laus",
        "series_type": "unemployment_rate",
        "config": {
            "mode": "add",                     # ✅ Additive (not multiplicative)
            "easter": False,                   # ✅ No Easter regressor
            "trading_day": False,              # ✅ No trading day
            "use_holiday_regressors": False,  # ✅ No holiday regressors
            "use_strike_regressors": False,   # ✅ No strike regressors
            "use_weather_regressors": False,  # ✅ No weather regressors
        },
    },
}
```

**Updated pipeline call:**

```python
# Get series-specific config
series_config = series_info.get("config", {})
series_config["frequency"] = "monthly"

result = pipeline.run(
    series_name=series_id,
    series_data=series_data,
    start_date=series_data.index[0].date(),
    config=series_config  # ✅ Use series-type-appropriate config
)
```

### File 2: `scripts/test_regressors_impact.py`

**Same fix applied:**
- Added series-type-specific configurations
- Updated function signature to accept series_info dict
- Respects series type when enabling/disabling regressors

---

## Why This Matters

### Different Data Sources

**CES (Employment Counts):**
- Establishment survey
- Measures jobs on payrolls
- **Directly affected by:** Strikes (workers off payroll), holidays (hiring timing)

**LAUS (Unemployment Rates):**
- Household survey (CPS-derived)
- Measures percentage unemployed
- **Smoothed, less affected by:** Short-term events

### Methodological Implications

**Strike Regressors on Unemployment Rates:**
- Strike → Workers off payroll (CES drops)
- Strike → Workers still "employed" in survey (unemployment rate stable)
- **Applying strike regressors to unemployment rates adds noise, not signal**

**Holiday Regressors on Unemployment Rates:**
- Holidays affect establishment hiring patterns (CES)
- Holidays don't affect household survey responses (unemployment rate)
- **Applying holiday regressors to unemployment rates is methodologically wrong**

---

## Expected Impact

### When Golden Diagnostics Re-Run

**CES Series (employment counts):**
- Results unchanged (already using correct configuration)
- Q-statistics may still show room for improvement
- Strike/weather regressors visible in output

**LASST060000000000003 (unemployment rate):**
- **Expected: BETTER Q-statistics** ✅
- No user-defined regressors in regression table
- Residuals should be MORE random (inappropriate regressors removed)
- Seasonal adjustment appropriate for rate series

### Why Q-Statistics Should Improve

**Before (WRONG):**
- X-13 fitting employment regressors to unemployment rate
- Regressors add noise
- Residuals = true pattern + regressor noise
- **Result:** Poor Q-statistics

**After (CORRECT):**
- X-13 using only appropriate seasonal patterns
- No inappropriate regressors
- Residuals = true randomness only
- **Result:** Better Q-statistics

---

## Files Modified

1. ✅ `scripts/record_golden_diagnostics.py`
   - Added `series_type` field
   - Added `config` dict per series
   - Updated pipeline call to use series-specific config

2. ✅ `scripts/test_regressors_impact.py`
   - Added `series_type` field
   - Added `config` dict per series
   - Updated function signature
   - Respects series type when testing

3. ✅ `docs/planning/PHASE_6_2_0_CRITICAL_FINDING_SERIES_TYPE_MISMATCH.md`
   - Comprehensive documentation of finding
   - Evidence from codebase
   - Methodological explanation

4. ✅ `docs/planning/IMPLEMENTATION_STATUS.md`
   - Updated Phase 6.2.0 section
   - Added critical finding to Key Findings
   - Updated status to 98% complete

5. ✅ `docs/planning/PHASE_6_2_0_FIXES_APPLIED.md` (this file)

---

## Next Steps

### Immediate

1. **Re-Run Golden Diagnostics:**
   ```bash
   python scripts/record_golden_diagnostics.py --vintage-date 2025-11-29 --record
   ```

2. **Compare Results:**
   - CES series: Same as before (expected)
   - LASST series: Improved Q-statistics (expected)

3. **Validate:**
   - Confirm no user regressors for unemployment rate
   - Confirm improved Q-statistics (p-value closer to > 0.05)

### Future

4. **Add Validation:**
   - Pipeline should warn if unemployment rate gets employment regressors
   - Configuration validation layer

5. **Documentation:**
   - Document series-type-appropriate configurations
   - BLS methodology guide (CES vs LAUS)

---

## Lessons Learned

1. **Test Configuration = Code Quality**
   - Correct code + wrong config = wrong results
   - Configuration is as critical as implementation

2. **Domain Knowledge Required**
   - Understanding BLS methodology is essential
   - CES ≠ LAUS (different surveys, different properties)

3. **Defaults Can Hide Errors**
   - Pipeline defaulting to `True` is convenient but dangerous
   - Explicit configuration prevents errors

4. **"Working Correctly" ≠ "Working Appropriately"**
   - Pipeline works correctly (applies regressors)
   - But was configured inappropriately (wrong regressors for series type)

---

## References

- `scripts/run_seasonal_adjustment.py` (lines 25-70) - Correct configurations
- `docs/ACCURACY_MAP.md` (lines 142-147) - Regressor effects
- `docs/PROJECT_INSTRUCTIONS.md` (lines 58-66) - Regressor requirements
- Phase 6.2.0 investigation reports

---

**Status:** ✅ FIXED - Ready for re-baseline with correct configurations

**Impact:** Expected improvement in Q-statistics for unemployment rate series

