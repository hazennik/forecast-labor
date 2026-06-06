-- ===========================
-- FORECAST-LABOR DATABASE INIT
-- ===========================
-- Initializes databases and schemas for the forecasting system
-- Creates: forecast_labor, mlflow, prefect databases

-- Ensure databases exist
SELECT 'CREATE DATABASE mlflow'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'mlflow')\gexec

SELECT 'CREATE DATABASE prefect'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'prefect')\gexec

-- Connect to main database
\c forecast_labor;

-- Create schemas
CREATE SCHEMA IF NOT EXISTS raw;
CREATE SCHEMA IF NOT EXISTS staging;
CREATE SCHEMA IF NOT EXISTS features;
CREATE SCHEMA IF NOT EXISTS models;
CREATE SCHEMA IF NOT EXISTS backtests;
CREATE SCHEMA IF NOT EXISTS subnets;
CREATE SCHEMA IF NOT EXISTS logs;

-- Create extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";

-- ----------------------------
-- RAW DATA TABLES
-- ----------------------------

-- Data ingestion log
CREATE TABLE IF NOT EXISTS logs.ingestion_log (
    id SERIAL PRIMARY KEY,
    source_name VARCHAR(255) NOT NULL,
    ingestion_timestamp TIMESTAMP NOT NULL DEFAULT NOW(),
    vintage_date DATE,
    row_count INTEGER,
    status VARCHAR(50),
    error_message TEXT,
    metadata JSONB
);

-- Data validation log
CREATE TABLE IF NOT EXISTS logs.validation_log (
    id SERIAL PRIMARY KEY,
    table_name VARCHAR(255) NOT NULL,
    validation_timestamp TIMESTAMP NOT NULL DEFAULT NOW(),
    validation_type VARCHAR(100),
    passed BOOLEAN,
    details JSONB
);

-- ----------------------------
-- FEATURE TABLES (METADATA)
-- ----------------------------

CREATE TABLE IF NOT EXISTS features.feature_registry (
    feature_id SERIAL PRIMARY KEY,
    feature_name VARCHAR(255) UNIQUE NOT NULL,
    feature_type VARCHAR(100),
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    description TEXT,
    source_tables TEXT[],
    transform_logic TEXT,
    is_active BOOLEAN DEFAULT TRUE
);

-- ----------------------------
-- MODEL METADATA
-- ----------------------------

CREATE TABLE IF NOT EXISTS models.model_registry (
    model_id SERIAL PRIMARY KEY,
    model_name VARCHAR(255) NOT NULL,
    model_version VARCHAR(50),
    model_type VARCHAR(100),
    trained_at TIMESTAMP DEFAULT NOW(),
    mlflow_run_id VARCHAR(255),
    accuracy_metrics JSONB,
    is_active BOOLEAN DEFAULT FALSE,
    deployed_at TIMESTAMP
);

-- Model performance tracking
CREATE TABLE IF NOT EXISTS models.performance_log (
    id SERIAL PRIMARY KEY,
    model_id INTEGER REFERENCES models.model_registry(model_id),
    evaluation_date DATE NOT NULL,
    target_variable VARCHAR(100),
    actual_value NUMERIC,
    predicted_value NUMERIC,
    prediction_interval_lower NUMERIC,
    prediction_interval_upper NUMERIC,
    metrics JSONB,
    vintage_date DATE
);

-- ----------------------------
-- BACKTEST RESULTS
-- ----------------------------

CREATE TABLE IF NOT EXISTS backtests.backtest_runs (
    run_id SERIAL PRIMARY KEY,
    model_id INTEGER REFERENCES models.model_registry(model_id),
    run_timestamp TIMESTAMP DEFAULT NOW(),
    start_date DATE,
    end_date DATE,
    smape NUMERIC,
    mae NUMERIC,
    rmse NUMERIC,
    crps NUMERIC,
    coverage_80 NUMERIC,
    coherence_error NUMERIC,
    passed_gates BOOLEAN,
    metadata JSONB
);

-- ----------------------------
-- SUBNET SUBMISSION LOGGING
-- ----------------------------

CREATE TABLE IF NOT EXISTS subnets.submission_log (
    submission_id SERIAL PRIMARY KEY,
    subnet_id VARCHAR(100) NOT NULL,
    adapter_version VARCHAR(100),
    submission_timestamp TIMESTAMP DEFAULT NOW(),
    event_id VARCHAR(255),
    event_name VARCHAR(255),
    event_date DATE,
    forecast_date DATE,
    target VARCHAR(100),
    probability_vector JSONB,
    signed_payload TEXT,
    payload_hash VARCHAR(128),
    submission_status VARCHAR(50) NOT NULL,
    validator_response JSONB,
    transaction_hash VARCHAR(255),
    reward NUMERIC,
    latency_ms INTEGER,
    error_message TEXT,
    metadata JSONB
);

-- Subnet event catalog
CREATE TABLE IF NOT EXISTS subnets.event_catalog (
    catalog_id SERIAL PRIMARY KEY,
    subnet_id VARCHAR(100) NOT NULL,
    external_event_id VARCHAR(255) NOT NULL,
    event_name VARCHAR(255) NOT NULL,
    event_type VARCHAR(100),
    event_date DATE,
    target VARCHAR(100),
    bin_definitions JSONB,
    scoring_rule VARCHAR(50),
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    UNIQUE (subnet_id, external_event_id)
);

-- ----------------------------
-- SEASONAL ADJUSTMENT METADATA
-- ----------------------------

CREATE TABLE IF NOT EXISTS raw.seasonal_specs (
    spec_id SERIAL PRIMARY KEY,
    series_name VARCHAR(255) UNIQUE NOT NULL,
    spec_file_path TEXT,
    spec_content TEXT,
    last_updated TIMESTAMP DEFAULT NOW(),
    m_stats JSONB,
    is_active BOOLEAN DEFAULT TRUE
);

-- ----------------------------
-- INDEXES
-- ----------------------------

CREATE INDEX IF NOT EXISTS idx_ingestion_log_source ON logs.ingestion_log(source_name, ingestion_timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_ingestion_log_vintage ON logs.ingestion_log(vintage_date);
CREATE INDEX IF NOT EXISTS idx_performance_log_model ON models.performance_log(model_id, evaluation_date DESC);
CREATE INDEX IF NOT EXISTS idx_backtest_runs_model ON backtests.backtest_runs(model_id, run_timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_submission_log_subnet ON subnets.submission_log(subnet_id, submission_timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_submission_log_event ON subnets.submission_log(subnet_id, event_name, event_date);
CREATE INDEX IF NOT EXISTS idx_submission_log_status ON subnets.submission_log(subnet_id, submission_status);
CREATE INDEX IF NOT EXISTS idx_event_catalog_subnet ON subnets.event_catalog(subnet_id, event_date DESC);

-- ----------------------------
-- GRANTS
-- ----------------------------

-- Grant permissions to forecast_user (created in docker-compose environment)
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA raw TO forecast_user;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA staging TO forecast_user;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA features TO forecast_user;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA models TO forecast_user;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA backtests TO forecast_user;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA subnets TO forecast_user;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA logs TO forecast_user;

GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA raw TO forecast_user;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA staging TO forecast_user;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA features TO forecast_user;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA models TO forecast_user;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA backtests TO forecast_user;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA subnets TO forecast_user;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA logs TO forecast_user;

-- ----------------------------
-- COMPLETION MESSAGE
-- ----------------------------

DO $$
BEGIN
    RAISE NOTICE '========================================';
    RAISE NOTICE 'Forecast-Labor Database Initialized';
    RAISE NOTICE '========================================';
    RAISE NOTICE 'Schemas: raw, staging, features, models, backtests, subnets, logs';
    RAISE NOTICE 'Ready for data ingestion and model tracking';
END $$;

