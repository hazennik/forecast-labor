# Phase 6.1.1 User Guide: Running Staging Validation

**Purpose:** Step-by-step guide for running Phase 6.1.1 staging validation with real production data.

---

## Prerequisites

Before running Phase 6.1.1 validation, you need:

### 1. API Keys (Required)

Obtain API keys for the following services:

- **BLS API Key:** https://www.bls.gov/developers/home.htm
  - Free registration required
  - Used for: CES (Nonfarm Payrolls), LAUS (State Employment)
  
- **NOAA API Token:** https://www.ncdc.noaa.gov/cdo-web/token
  - Free registration required
  - Used for: Weather/Storm Events data

### 2. Docker and Docker Compose (Required)

- Docker Desktop installed and running
- Minimum 8GB RAM allocated to Docker
- Minimum 20GB free disk space

### 3. Repository Cloned (Required)

```bash
git clone <repository_url>
cd forecast-labor
```

---

## Step-by-Step Validation Process

### Step 1: Configure Environment Variables

```bash
# Copy the example .env file
cp .env.example .env

# Edit .env with your API keys
nano .env  # or use your preferred text editor
```

**Required settings in `.env`:**

```bash
# BLS API Key (required for CES and LAUS data)
BLS_API_KEY=your_bls_api_key_here

# NOAA API Token (required for weather data)
NOAA_API_TOKEN=your_noaa_api_token_here

# Production validation setting (important!)
ALLOW_FALLBACK_DATA=false  # Must be 'false' for production validation

# Database settings (usually default is fine)
POSTGRES_HOST=postgres
POSTGRES_PORT=5432
POSTGRES_DB=forecast
POSTGRES_USER=forecast
POSTGRES_PASSWORD=forecast

# Feature registry backend
FEATURE_REGISTRY_BACKEND=database  # Use 'memory' for development, 'database' for production
```

### Step 2: Start Docker Services

```bash
# Start all services (Postgres, MinIO, MLflow, Prefect, ETL, X-13)
docker compose up -d

# Wait ~30 seconds for services to fully start
sleep 30

# Verify services are healthy
python scripts/check_infrastructure_health.py
```

**Expected output:**
```
✅ All services healthy
- Postgres: UP
- MinIO: UP
- MLflow: UP
- Prefect: UP
- ETL: UP
- X-13: UP
```

### Step 3: Run Environment Check (Recommended First)

Before committing to a full validation (which can take 30+ minutes), verify your environment is set up correctly:

```bash
python scripts/phase_6_1_1_staging_validation.py --check-only
```

**What this does:**
- ✅ Checks if API keys are configured in `.env`
- ✅ Verifies Docker services are healthy
- ⊘ Skips all data pipeline steps (ETL, validation, seasonal, features)

**Expected output:**
```
================================================================================
PHASE 6.1.1: STAGING VALIDATION WITH REAL DATA
================================================================================
Validation ID: phase_6_1_1_20251128_120000
Check Only Mode: True
================================================================================

Step 1: API Keys Configuration Check
✅ BLS_API_KEY: Configured
✅ NOAA_API_TOKEN: Configured
✅ ALLOW_FALLBACK_DATA: false (production mode)

Step 2: Infrastructure Health Check
✅ All Docker services healthy

Steps 3-7: SKIPPED (check-only mode)

================================================================================
✅ PHASE 6.1.1 VALIDATION PASSED
📄 Full Report: data/reports/validation/phase_6_1_1/phase_6_1_1_20251128_120000.md
📊 JSON Report: data/reports/validation/phase_6_1_1/phase_6_1_1_20251128_120000.json
================================================================================
```

**If environment check fails:**
- Review the validation report in `data/reports/validation/phase_6_1_1/`
- Fix the issues identified (missing API keys, unhealthy services, etc.)
- Re-run the check until it passes

### Step 4: Run Full Validation (After Environment Check Passes)

Once the environment check passes, run the complete validation workflow:

```bash
python scripts/phase_6_1_1_staging_validation.py --run-full-validation
```

**⏱️ Estimated Time:** 30-60 minutes (depends on network speed and API rate limits)

**What this does:**
1. ✅ **API Keys Check** (~5 seconds)
2. ✅ **Infrastructure Health** (~10 seconds)
3. ✅ **Real ETL Execution** (~10-30 minutes)
   - Pulls data from BLS (CES, LAUS)
   - Pulls data from NOAA (Weather)
   - Pulls data from Treasury (Withholdings)
   - Pulls data from Census (Business Formations)
   - Saves data to vintages
4. ✅ **Data Quality Validation** (~2-5 minutes)
   - Schema validation
   - Freshness checks
   - Quality validation (ranges, duplicates)
5. ✅ **Seasonal Adjustment** (~5-10 minutes)
   - X-13 ARIMA-SEATS on all series
   - M-statistics computation
   - Q-statistics computation
6. ✅ **Feature Building** (~5-10 minutes)
   - MIDAS lag construction
   - Frequency transformations
   - State/sector aggregations
   - Feature registry updates
7. ⊘ **Sample Model Training** (SKIPPED for now)
   - Deferred until Phase 6+ orchestration ready

**Expected output:**
```
================================================================================
PHASE 6.1.1: STAGING VALIDATION WITH REAL DATA
================================================================================
Validation ID: phase_6_1_1_20251128_130000
Check Only Mode: False
================================================================================

Step 1: API Keys Configuration Check
✅ PASSED

Step 2: Infrastructure Health Check
✅ PASSED

Step 3: Real ETL Execution (Production APIs)
🔄 IN PROGRESS (this will take 10-30 minutes)...
✅ PASSED

Step 4: Data Quality Validation
✅ PASSED

Step 5: Seasonal Adjustment on Real Data
✅ PASSED

Step 6: Feature Generation on Real Data
✅ PASSED

Step 7: Sample Model Training
⊘ SKIPPED (deferred to Phase 6+ orchestration)

================================================================================
✅ PHASE 6.1.1 VALIDATION PASSED
📄 Full Report: data/reports/validation/phase_6_1_1/phase_6_1_1_20251128_130000.md
📊 JSON Report: data/reports/validation/phase_6_1_1/phase_6_1_1_20251128_130000.json
================================================================================
```

### Step 5: Review Validation Report

Open the Markdown report to review detailed results:

```bash
# Find the latest report
ls -lt data/reports/validation/phase_6_1_1/

# View the report
cat data/reports/validation/phase_6_1_1/phase_6_1_1_*.md
# Or open in your text editor/browser
```

**Report includes:**
- Overall status (PASSED/FAILED)
- API keys configuration summary
- Step-by-step results with details
- Issues discovered (if any)
- Recommendations for fixes
- Next steps guidance

---

## Troubleshooting Common Issues

### Issue 1: Missing API Keys

**Error:**
```
❌ Step 1: API Keys Configuration Check
Error: Missing API keys: BLS_API_KEY (Bureau of Labor Statistics), NOAA_API_TOKEN (NOAA Weather Data)
```

**Solution:**
1. Verify `.env` file exists in project root
2. Check that API keys are set correctly (no quotes, no spaces)
3. Restart Docker services after updating `.env`:
   ```bash
   docker compose down
   docker compose up -d
   ```

### Issue 2: Docker Services Not Healthy

**Error:**
```
❌ Step 2: Infrastructure Health Check
Error: Infrastructure health check failed
```

**Solution:**
1. Check Docker is running: `docker ps`
2. Check service logs: `docker compose logs postgres minio mlflow`
3. Restart services:
   ```bash
   docker compose down
   docker compose up -d
   sleep 30
   python scripts/check_infrastructure_health.py
   ```

### Issue 3: ETL Execution Timeout

**Error:**
```
❌ Step 3: Real ETL Execution
Error: ETL execution timed out (>30 minutes)
```

**Possible Causes:**
- Slow network connection
- API rate limiting
- Large historical data range

**Solution:**
1. Check network connectivity: `ping bls.gov`
2. Check API rate limits (BLS: 500 requests/day)
3. Re-run validation (it will resume from cached data)

### Issue 4: Data Quality Validation Failed

**Error:**
```
❌ Step 4: Data Quality Validation
Error: Schema validation failed: Missing required columns
```

**Solution:**
1. Review validation report for specific failures
2. Check ETL logs: `docker compose logs etl`
3. Verify API responses are valid
4. Check for upstream API schema changes
5. Re-run validation after fixing issues

### Issue 5: Seasonal Adjustment Failed

**Error:**
```
❌ Step 5: Seasonal Adjustment on Real Data
Error: X-13 seasonal adjustment failed
```

**Solution:**
1. Check X-13 service: `docker compose logs x13`
2. Verify X-13 binary is installed in container
3. Check seasonal adjustment specs in `seasonal/specs/`
4. Review diagnostics in logs

### Issue 6: Feature Building Failed

**Error:**
```
❌ Step 6: Feature Generation on Real Data
Error: Feature building failed for vintage date YYYY-MM-DD
```

**Solution:**
1. Check feature building logs: `docker compose logs etl`
2. Verify seasonal adjustment completed successfully
3. Check feature registry configuration
4. Ensure database is healthy

---

## Understanding Validation Reports

### JSON Report Structure

```json
{
  "validation_id": "phase_6_1_1_20251128_130000",
  "started_at": "2025-11-28T13:00:00",
  "completed_at": "2025-11-28T13:45:30",
  "total_duration_seconds": 2730.0,
  "overall_status": "passed",
  "steps": [
    {
      "step_id": "1_api_keys",
      "step_name": "API Keys Configuration Check",
      "status": "passed",
      "started_at": "2025-11-28T13:00:00",
      "completed_at": "2025-11-28T13:00:05",
      "error_message": null,
      "details": {"all_keys_configured": true}
    },
    // ... more steps
  ],
  "api_keys_configured": {
    "BLS_API_KEY": true,
    "NOAA_API_TOKEN": true,
    "ALLOW_FALLBACK_DATA": true
  },
  "issues_discovered": [],
  "recommendations": []
}
```

### Markdown Report Structure

```markdown
# Phase 6.1.1: Staging Validation with Real Data

**Validation ID:** `phase_6_1_1_20251128_130000`
**Overall Status:** **PASSED**

## API Keys Configuration
- **BLS_API_KEY:** ✅ Configured
- **NOAA_API_TOKEN:** ✅ Configured

## Validation Steps
### ✅ API Keys Configuration Check
**Status:** passed
...

### ✅ Real ETL Execution (Production APIs)
**Status:** passed
...

## Next Steps
✅ **Staging validation PASSED.** Ready to proceed to Phase 6.1.2.
```

---

## What to Do After Validation Passes

Once Phase 6.1.1 validation passes:

### 1. Review the Report

- Verify all steps passed (except step 7, which is deferred)
- Check "Issues Discovered" section (should be empty)
- Review "Recommendations" (if any)

### 2. Commit Validation Report (Optional)

```bash
git add data/reports/validation/phase_6_1_1/
git commit -m "Phase 6.1.1: Staging validation passed"
```

### 3. Proceed to Phase 6.1.2

**Next Phase:** Record Real Seasonal Diagnostics Baseline

**Estimated Time:** 30-60 minutes

**Actions:**
1. Ensure X-13 service is running
2. Run: `python scripts/record_golden_diagnostics.py --vintage-date 2024-01-15 --record`
3. Verify M-statistics quality (< 1.0 for good quality)
4. Verify Q-statistic quality (p-value > 0.05)
5. Commit updated baseline to repository

---

## Frequently Asked Questions

### Q: How long does full validation take?
**A:** 30-60 minutes, depending on network speed and API rate limits. The ETL step (pulling production data) is the longest.

### Q: Can I stop and resume validation?
**A:** Yes. If validation fails at any step, fix the issue and re-run. ETL data is cached, so it won't re-download everything.

### Q: Do I need to run validation every time?
**A:** No. Run full validation:
- Before Phase 6.2+ backtesting (first time)
- After major infrastructure changes
- After API key rotation
- Periodically (monthly) to verify production readiness

Use `--check-only` for quick environment checks.

### Q: What if validation fails?
**A:** Review the validation report for specific errors. Common fixes:
- Add missing API keys
- Restart unhealthy Docker services
- Check network connectivity
- Verify API rate limits not exceeded

### Q: Why is Step 7 (Model Training) skipped?
**A:** Phase 5 model classes exist, but orchestrated training pipeline is pending Phase 6+ integration. This step will be implemented as backtesting infrastructure is developed.

### Q: Can I run validation without Docker?
**A:** Not recommended. Docker ensures consistent environment. Native Python execution may have dependency conflicts.

### Q: How do I re-run validation?
**A:** Just run the command again:
```bash
python scripts/phase_6_1_1_staging_validation.py --run-full-validation
```

### Q: Where are validation artifacts stored?
**A:**
- Reports: `data/reports/validation/phase_6_1_1/`
- ETL data: `data/vintages/`
- Seasonal output: `data/seasonal_output/`
- Features: `data/features/`

---

## Support

If you encounter issues not covered in this guide:

1. Check validation report for detailed error messages
2. Review Docker logs: `docker compose logs <service>`
3. Verify infrastructure: `python scripts/check_infrastructure_health.py`
4. Review completion summary: `docs/planning/PHASE_6_1_1_COMPLETION_SUMMARY.md`
5. Open a GitHub issue with validation report attached

---

**Last Updated:** 2025-11-28  
**Phase:** 6.1.1 - Staging Validation with Real Data  
**Next Phase:** 6.1.2 - Record Real Seasonal Diagnostics Baseline

