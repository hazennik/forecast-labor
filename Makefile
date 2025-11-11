# ===========================
# FORECAST-LABOR MAKEFILE
# ===========================
# One-command orchestration for the entire forecasting system

.PHONY: help up down restart logs seed seasonal features train backtest submit miner clean test lint format

# Default target
.DEFAULT_GOAL := help

# ----------------------------
# HELP
# ----------------------------
help: ## Show this help message
	@echo "Forecast-Labor Make Commands:"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}'
	@echo ""

# ----------------------------
# DOCKER SERVICES
# ----------------------------
up: ## Start all services (Docker Compose)
	@echo "🚀 Starting forecast-labor stack..."
	docker compose up -d
	@echo "✅ Stack started. Access:"
	@echo "   - MLflow UI: http://localhost:5000"
	@echo "   - MinIO Console: http://localhost:9001"
	@echo "   - Streamlit Dashboard: http://localhost:8501"
	@echo "   - Prefect UI: http://localhost:4200"

down: ## Stop all services
	@echo "🛑 Stopping forecast-labor stack..."
	docker compose down
	@echo "✅ Stack stopped."

restart: ## Restart all services
	@echo "♻️  Restarting stack..."
	docker compose restart
	@echo "✅ Stack restarted."

logs: ## Tail logs from all services
	docker compose logs -f

logs-etl: ## Tail ETL service logs
	docker compose logs -f etl

logs-models: ## Tail model training logs
	docker compose logs -f models

logs-miner: ## Tail SN41 miner logs
	docker compose logs -f miner

# ----------------------------
# SETUP & INITIALIZATION
# ----------------------------
init: ## Initial setup (create directories, copy .env)
	@echo "🔧 Initializing forecast-labor..."
	@if [ ! -f .env ]; then cp .env.example .env; echo "✅ Created .env from .env.example"; fi
	@mkdir -p data/raw data/vintages data/features data/artifacts data/reports data/secrets
	@mkdir -p sn41/keys
	@echo "✅ Directories created."
	@echo "⚠️  Edit .env with your API keys before proceeding."

venv: ## Create Python virtual environment
	@echo "🐍 Creating virtual environment..."
	python3 -m venv .venv
	@echo "✅ Virtual environment created."
	@echo "   Activate with: source .venv/bin/activate"

install: ## Install Python dependencies
	@echo "📦 Installing dependencies..."
	pip install --upgrade pip
	pip install -r requirements.txt
	@echo "✅ Dependencies installed."

# ----------------------------
# DATA PIPELINE
# ----------------------------
seed: ## Seed initial public data (first-time setup)
	@echo "🌱 Seeding public data..."
	docker compose exec etl python /app/scripts/seed_public_data.py
	@echo "✅ Public data seeded."

ingest: ## Run daily/weekly data ingestion
	@echo "📥 Ingesting latest data..."
	docker compose exec etl python /app/scripts/run_etl.py
	@echo "✅ Data ingestion complete."

validate: ## Run data validation checks
	@echo "✅ Running data quality checks..."
	docker compose exec etl python /app/etl/validators/run_validation.py
	@echo "✅ Validation complete."

# ----------------------------
# SEASONAL ADJUSTMENT
# ----------------------------
seasonal: ## Run X-13 seasonal adjustment
	@echo "📊 Running seasonal adjustment..."
	docker compose exec x13 python /app/scripts/run_x13_bundle.py
	@echo "✅ Seasonal adjustment complete."

seasonal-diagnostics: ## Generate X-13 diagnostics report
	@echo "📋 Generating seasonal diagnostics..."
	docker compose exec x13 python /app/seasonal/diagnostics/generate_report.py
	@echo "✅ Diagnostics generated."

# ----------------------------
# FEATURE ENGINEERING
# ----------------------------
features: ## Build feature tables
	@echo "🔨 Building features..."
	docker compose exec models python /app/scripts/build_features.py
	@echo "✅ Features built."

# ----------------------------
# MODEL TRAINING
# ----------------------------
train: ## Train all models (DFM, MIDAS, GBM, revision, calibration)
	@echo "🧠 Training models..."
	docker compose exec models python /app/scripts/train_all.py
	@echo "✅ Model training complete. Check MLflow UI."

train-dfm: ## Train Dynamic Factor Model only
	docker compose exec models python /app/models_src/dfm/train.py

train-midas: ## Train MIDAS model only
	docker compose exec models python /app/models_src/midas/train.py

train-gbm: ## Train GBM quantile model only
	docker compose exec models python /app/models_src/gbm_quantile/train.py

train-revision: ## Train revision model only
	docker compose exec models python /app/models_src/revision/train.py

# ----------------------------
# BACKTESTING & EVALUATION
# ----------------------------
backtest: ## Run vintage-honest backtest
	@echo "🔍 Running backtest..."
	docker compose exec models python /app/scripts/run_backtest.py
	@echo "✅ Backtest complete. Report saved to data/reports/"

evaluate: ## Evaluate current model performance
	@echo "📈 Evaluating models..."
	docker compose exec models python /app/backtests/metrics/evaluate.py
	@echo "✅ Evaluation complete."

# ----------------------------
# SN41 MINER
# ----------------------------
submit: ## Build SN41 payload (dry run)
	@echo "📤 Building SN41 payload..."
	docker compose exec miner python /app/scripts/make_sn41_payload.py
	@echo "✅ Payload generated."

miner: ## Start SN41 miner service (production only)
	@echo "⛏️  Starting SN41 miner..."
	@if [ "$(shell grep SN41_MINER_ENABLED .env | cut -d '=' -f2)" = "true" ]; then \
		docker compose exec miner python /app/scripts/submit_sn41.py; \
	else \
		echo "❌ SN41_MINER_ENABLED is false. Set to true in .env to enable."; \
	fi

miner-health: ## Check miner health status
	curl http://localhost:8080/health || echo "❌ Miner service not responding"

# ----------------------------
# DASHBOARDS
# ----------------------------
dashboard: ## Open Streamlit dashboard
	@echo "📊 Opening dashboard..."
	@open http://localhost:8501 || echo "Dashboard available at http://localhost:8501"

mlflow: ## Open MLflow UI
	@open http://localhost:5000 || echo "MLflow available at http://localhost:5000"

# ----------------------------
# DEVELOPMENT & TESTING
# ----------------------------
test: ## Run all tests
	@echo "🧪 Running tests..."
	pytest tests/ -v --cov=. --cov-report=html
	@echo "✅ Tests complete. Coverage report in htmlcov/"

test-etl: ## Run ETL tests only
	pytest tests/etl/ -v

test-models: ## Run model tests only
	pytest tests/models/ -v

lint: ## Run linters (ruff, mypy)
	@echo "🔍 Linting code..."
	ruff check .
	mypy .
	@echo "✅ Linting complete."

format: ## Format code (black)
	@echo "✨ Formatting code..."
	black .
	@echo "✅ Code formatted."

# ----------------------------
# CLEANUP
# ----------------------------
clean: ## Clean temporary files and caches
	@echo "🧹 Cleaning temporary files..."
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	find . -type f -name "*.pyo" -delete
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".ipynb_checkpoints" -exec rm -rf {} + 2>/dev/null || true
	@echo "✅ Cleanup complete."

clean-data: ## Clean local data (USE WITH CAUTION)
	@echo "⚠️  This will delete all local data. Press Ctrl+C to cancel..."
	@sleep 3
	rm -rf data/raw/* data/features/* data/artifacts/*
	@echo "✅ Local data cleaned (vintages preserved)."

reset: down clean ## Stop services and clean caches
	@echo "♻️  Reset complete."

# ----------------------------
# FULL PIPELINE
# ----------------------------
pipeline: seed seasonal features train backtest ## Run full pipeline (first-time)
	@echo "✅ Full pipeline complete."

update: ingest seasonal features ## Run incremental update (daily/weekly)
	@echo "✅ Incremental update complete."

# ----------------------------
# PRODUCTION DEPLOYMENT
# ----------------------------
deploy-check: ## Pre-deployment checks
	@echo "🔒 Running deployment checks..."
	@if [ ! -f .env ]; then echo "❌ .env file missing"; exit 1; fi
	@if [ -z "$(shell grep POSTGRES_PASSWORD .env | cut -d '=' -f2)" ]; then echo "❌ POSTGRES_PASSWORD not set"; exit 1; fi
	@if [ "$(shell grep ENVIRONMENT .env | cut -d '=' -f2)" != "production" ]; then echo "⚠️  ENVIRONMENT is not 'production'"; fi
	@echo "✅ Deployment checks passed."

# ----------------------------
# MISC
# ----------------------------
status: ## Show service status
	docker compose ps

shell-etl: ## Open shell in ETL container
	docker compose exec etl /bin/bash

shell-models: ## Open shell in models container
	docker compose exec models /bin/bash

shell-miner: ## Open shell in miner container
	docker compose exec miner /bin/bash

db-shell: ## Open PostgreSQL shell
	docker compose exec postgres psql -U forecast_user -d forecast_labor

