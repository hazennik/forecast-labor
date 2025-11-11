# Quick Start Guide

Get the forecast-labor system running locally in minutes.

---

## Prerequisites

✅ **Installed:**
- Docker Desktop (running)
- Python 3.9+
- Make
- Git

---

## Step 1: Initial Setup

```bash
# Clone repository (if not already)
cd /Users/ryan/Documents/GitHub/forecast-labor

# Initialize environment
make init

# Edit .env with your settings (optional for now)
# nano .env
```

---

## Step 2: Start Services

```bash
# Start all Docker services
make up

# Wait ~30 seconds for services to initialize
# Then verify services are running
make status
```

**Expected services:**
- `forecast-minio` - Object storage
- `forecast-postgres` - Database
- `forecast-mlflow` - Model tracking
- `forecast-prefect` - Workflow orchestration
- `forecast-x13` - Seasonal adjustment
- `forecast-etl` - Data ingestion
- `forecast-models` - Model training
- `forecast-dashboard` - Visualization
- `forecast-miner` - SN41 (disabled by default)

---

## Step 3: Access UIs

Open in your browser:

- **MLflow:** http://localhost:5000
- **MinIO Console:** http://localhost:9001 (minioadmin / minioadmin123)
- **Streamlit Dashboard:** http://localhost:8501
- **Prefect UI:** http://localhost:4200

---

## Step 4: Seed Initial Data

```bash
# Create Python virtual environment (optional but recommended)
make venv
source .venv/bin/activate

# Install dependencies
make install

# Seed public data (UI Claims)
make seed
```

**This will:**
- Download latest UI Claims data
- Validate data quality
- Save raw data to `data/raw/claims/`
- Create vintage snapshot in `data/vintages/ui_claims/`

---

## Step 5: Verify Data

```bash
# Check logs
make logs-etl

# Or access ETL container
make shell-etl
ls -la /app/data/raw/claims/
ls -la /app/data/vintages/ui_claims/
exit
```

---

## What's Working Now

✅ **Infrastructure:**
- All 9 services running
- Database initialized with complete schema
- Object storage ready (MinIO)
- MLflow tracking configured
- Prefect orchestration ready

✅ **Data Pipelines (ALL 7):**
- UI Claims ETL (weekly unemployment - national + states)
- Treasury Withholdings ETL (daily payroll tax collections)
- BLS CES ETL (monthly NFP + 20 sector series)
- BLS LAUS ETL (state employment + unemployment rates)
- Strikes ETL (work stoppages and labor disruptions)
- Weather ETL (NOAA storm events and disasters)
- CNBFS ETL (business formations and applications)
- Complete vintage snapshot management
- Full validation and error handling

---

## What's Next

🚧 **Phase 3 (Weeks 3-4):**
1. Data validation framework (Great Expectations)
2. Seasonal adjustment service (X-13)
3. Regressor builders (holidays, strikes, weather)

**Phase 4 (Weeks 4-5):**
4. Feature engineering (MIDAS lags, aggregations)
5. Feature registry and storage

**Phase 5 (Weeks 5-8):**
6. Model training (DFM, MIDAS, GBM quantile)
7. Revision modeling
8. Calibration layer

**Phase 6-7 (Weeks 8-12):**
9. Backtesting framework
10. SN41 integration and mining

---

## Common Commands

```bash
# Start services
make up

# Stop services
make down

# View logs
make logs                 # All services
make logs-etl            # ETL only
make logs-models         # Models only

# Run pipelines
make seed                # Initial data seed
make ingest              # Daily/weekly updates
make seasonal            # X-13 seasonal adjustment
make features            # Build features
make train               # Train models
make backtest            # Run backtests

# Development
make test                # Run tests
make lint                # Check code quality
make format              # Format code

# Cleanup
make clean               # Clear caches
make down                # Stop services
```

---

## Troubleshooting

### Services won't start
```bash
# Check Docker is running
docker ps

# Restart services
make restart
```

### Database connection errors
```bash
# Check Postgres is healthy
docker compose ps postgres

# Restart Postgres
docker compose restart postgres
```

### MinIO connection errors
```bash
# Check MinIO is healthy
docker compose ps minio

# Verify buckets were created
docker compose logs minio-init
```

### "Module not found" errors
```bash
# Make sure you're in the virtual environment
source .venv/bin/activate

# Reinstall dependencies
make install
```

---

## File Structure

```
forecast-labor/
├── data/                    # Local data (gitignored)
│   ├── raw/                # Downloaded data
│   ├── vintages/           # Immutable snapshots
│   ├── features/           # Engineered features
│   └── artifacts/          # Model outputs
├── etl/                    # Data pipelines
│   ├── common/            # Base classes ✅
│   └── public/
│       └── claims/        # UI Claims ETL ✅
├── scripts/               # Utility scripts
│   └── seed_public_data.py  # Initial seeding ✅
├── docker-compose.yml     # Service definitions ✅
├── Makefile              # Commands ✅
└── .env                  # Configuration
```

---

## Next Steps

1. **Add more data sources** - Treasury withholdings, CES, LAUS
2. **Set up seasonal adjustment** - X-13 specs and regressors
3. **Build features** - MIDAS lags, aggregations
4. **Train models** - DFM, MIDAS, XGBoost
5. **Connect to SN41** - When ready to mine

---

## Need Help?

- Check `IMPLEMENTATION_STATUS.md` for progress
- Review architecture docs in `/docs`
- Check logs: `make logs`

