# Weather Data Production Strategy

**Date:** 2025-11-28  
**Issue:** How does CSV bulk file approach ensure up-to-date data in production?

---

## Current Situation

**NOAA Storm Events Database:**
- Only available via CSV bulk files (no JSON API exists)
- Files published at: `https://www.ncei.noaa.gov/pub/data/swdi/stormevents/csvfiles/`
- Format: `StormEvents_details-ftp_v1.0_d{YEAR}_c{YYYYMMDD}.csv.gz`
- Updated regularly (most recent: `c20251118` - November 18, 2025)

**Example Files:**
- `StormEvents_details-ftp_v1.0_d2024_c20251118.csv.gz` (69,502 events)
- `StormEvents_details-ftp_v1.0_d2025_c20251118.csv.gz` (44,721 events)

---

## Data Freshness Analysis

### Update Frequency
Based on filenames, NOAA updates Storm Events CSV files:
- **At least monthly** (possibly more frequent)
- Files have creation dates (`c20251118` = created 2025-11-18)
- New events added as they're reviewed and quality-controlled

### Data Lag
Storm Events data has **inherent reporting lag**:
1. Event occurs (e.g., Hurricane hits Florida)
2. Local NWS offices collect reports (days-weeks)
3. NOAA reviews and validates data (weeks-months)
4. Data added to database (1-3 months after event)

**This lag exists regardless of CSV vs API approach.**

---

## Production Impact

### For Labor Market Forecasting:
**Historical severe weather events** are used to:
- Analyze past labor market impacts (e.g., "Hurricane impact on 2023 employment")
- Train models on weather disruption patterns
- Incorporate weather disruptions into nowcasts

**NOT used for:**
- Real-time weather tracking (use `api.weather.gov` alerts for that)
- Same-day weather forecasts

### Data Freshness Requirements:
**Monthly updates are SUFFICIENT because:**
1. **Labor data itself is monthly** (NFP released ~6 weeks after month-end)
2. **Weather impact takes time** (employment effects measured months later)
3. **Model retraining is periodic** (not real-time)

**Example Timeline:**
- Hurricane hits: October 15, 2025
- Labor market impact: Measured in October/November/December employment
- NFP October data: Released ~December 6, 2025
- By then, Storm Events CSV updated with October hurricane

---

## Recommended Production Strategy

### Option 1: CSV with Automated Updates (RECOMMENDED)

**Implementation:**
```python
# In weather_etl.py extract method:
# 1. Download latest CSV for current + past year
# 2. Check file modification date vs last run
# 3. Only reprocess if new data available
```

**Advantages:**
- ✅ No API rate limits
- ✅ Complete historical data (2004-present)
- ✅ Official NOAA source (most reliable)
- ✅ Monthly updates sufficient for monthly labor data
- ✅ No authentication required

**Implementation Plan:**
1. Check CSV file last-modified date before download
2. Compare with last successful run timestamp
3. Skip if no new data (optimization)
4. Download and process if updated

### Option 2: Hybrid Approach (OVERKILL)

**For real-time events + historical:**
1. Use `api.weather.gov/alerts` for current alerts (last 7 days)
2. Use CSV bulk files for historical events (> 1 week old)
3. Merge both sources in transform

**Advantages:**
- ✅ Most current data possible (same-day)
- ✅ Historical completeness

**Disadvantages:**
- ❌ Complex merge logic
- ❌ Real-time alerts don't have final damage/casualty counts
- ❌ Overkill for monthly labor forecasting

---

## Production Workflow

### Monthly ETL Run (Recommended):
```
Day 1: NFP forecast window opens
├─ Run weather ETL
│  ├─ Check NOAA CSV last-modified dates
│  ├─ Download if updated (or first run of month)
│  ├─ Extract storm events from past 24 months
│  └─ Create vintage snapshot
├─ Run seasonal adjustment
├─ Build features (includes weather disruption scores)
└─ Generate forecasts

Result: Weather data is at most 1-2 weeks old when forecasting
        (Acceptable given 1-3 month reporting lag inherent to storm data)
```

### Optimization - Incremental Updates:
```python
# Only fetch current + previous year files
# Compare modification dates to avoid re-downloading unchanged files
if csv_last_modified > last_etl_run:
    download_and_process()
else:
    logger.info("No new storm data available, skipping download")
    use_existing_vintage()
```

---

## Answer to Your Question

**Q: How will models get the most up-to-date data during production runs?**

**A: CSV approach IS production-ready because:**

1. **NOAA updates CSV files monthly** - matches labor data frequency
2. **Storm Events have inherent lag** (1-3 months) - no real-time source exists
3. **Labor forecasts are monthly** - don't need intra-month weather updates
4. **CSV is official NOAA source** - most complete and reliable

**Example Production Schedule:**
- **ETL runs:** Every Friday before NFP release (weekly)
- **Weather data:** NOAA updates CSVs mid-month
- **By forecast time:** Weather data is current through ~2 weeks ago
- **For modeling:** This is fresh enough (weather impacts measured over months, not days)

---

## Alternative: NOAA CDO API (NOT RECOMMENDED)

NOAA's Climate Data Online (CDO) API exists but:
- ❌ Doesn't include Storm Events Database
- ❌ Has temperature/precipitation (not storm details)
- ❌ Missing key fields: deaths, injuries, property damage by event
- ❌ Requires different data structure

**Verdict:** CSV is the correct approach for Storm Events.

---

## Implementation Status

**Current:** ✅ CSV download implemented and working (115K+ events ingested)

**Recommended Enhancements:**
1. ✅ Already implemented: Download multiple years (2023-2025)
2. ⏳ TODO: Add file modification date checking (optimization)
3. ⏳ TODO: Add logging of data freshness (e.g., "Latest event: 2025-11-15")

**No changes required for Phase 6.1.1** - current implementation is production-ready.

---

## Conclusion

**Keep the CSV approach.** It's the correct solution for NOAA Storm Events:
- Most reliable data source
- Sufficient freshness for monthly labor forecasting
- No API rate limits
- Complete historical coverage

The key insight: **Weather impact on labor markets is measured over months, not hours.** Having storm data updated monthly (via CSV) is perfectly aligned with monthly labor data releases.

