# Feature Registry Database Documentation

**Version:** 1.0  
**Last Updated:** 2025-11-21  
**Status:** Production-Ready

## Overview

The Feature Registry provides persistent storage for feature metadata, lineage tracking, and versioning using PostgreSQL. This document covers database schema, usage examples, and migration procedures.

---

## Table of Contents

1. [Database Schema](#database-schema)
2. [Quick Start](#quick-start)
3. [Usage Examples](#usage-examples)
4. [Migration Guide](#migration-guide)
5. [Lineage Tracking](#lineage-tracking)
6. [Versioning Workflow](#versioning-workflow)
7. [Rollback Procedures](#rollback-procedures)
8. [API Reference](#api-reference)
9. [Troubleshooting](#troubleshooting)

---

## Database Schema

### Tables

The feature registry uses three main tables in the `features` schema:

#### 1. `features.feature_metadata`

Primary table for feature information.

| Column | Type | Description |
|--------|------|-------------|
| `feature_id` | UUID | Primary key, auto-generated |
| `name` | VARCHAR(255) | Feature name (e.g., 'treasury_withholdings_lag_0') |
| `display_name` | VARCHAR(255) | Human-readable name |
| `description` | TEXT | Feature description |
| `source` | VARCHAR(100) | Data source (e.g., 'bls_ces', 'treasury') |
| `frequency` | VARCHAR(50) | Temporal frequency ('daily', 'weekly', 'monthly') |
| `vintage_date` | DATE | Vintage date for reproducibility |
| `data_type` | VARCHAR(50) | Data type (e.g., 'float64', 'int64') |
| `unit` | VARCHAR(100) | Unit of measurement |
| `seasonal_adjustment` | VARCHAR(50) | Seasonal adjustment method |
| `current_version` | INTEGER | Current version number |
| `status` | VARCHAR(50) | Status ('active', 'deprecated', 'experimental') |
| `is_synthetic` | BOOLEAN | Whether feature is derived from others |
| `created_at` | TIMESTAMP | Creation timestamp |
| `updated_at` | TIMESTAMP | Last update timestamp |
| `deprecation_date` | DATE | Date feature was deprecated (if applicable) |
| `tags` | JSONB | Additional metadata (key-value pairs) |

**Indexes:**
- Primary key on `feature_id`
- Index on `name` (unique)
- Index on `source`
- Index on `status`
- Index on `vintage_date`

#### 2. `features.feature_transforms`

Tracks transformations and lineage.

| Column | Type | Description |
|--------|------|-------------|
| `transform_id` | UUID | Primary key |
| `feature_id` | UUID | Foreign key to feature_metadata |
| `transform_type` | VARCHAR(100) | Type of transformation |
| `transform_params` | JSONB | Transformation parameters |
| `parent_feature_id` | UUID | Parent feature (if derived) |

**Indexes:**
- Primary key on `transform_id`
- Index on `feature_id`
- Index on `parent_feature_id`

#### 3. `features.feature_versions`

Version history for features.

| Column | Type | Description |
|--------|------|-------------|
| `version_id` | UUID | Primary key |
| `feature_id` | UUID | Foreign key to feature_metadata |
| `version` | INTEGER | Version number (1, 2, 3, ...) |
| `checksum` | VARCHAR(64) | SHA256 hash of feature data |
| `row_count` | INTEGER | Number of rows |
| `byte_size` | BIGINT | Size in bytes |
| `created_at` | TIMESTAMP | Version creation timestamp |
| `change_description` | TEXT | Description of changes |
| `deprecated_at` | TIMESTAMP | When version was deprecated |
| `min_value` | DOUBLE PRECISION | Minimum value (for numeric features) |
| `max_value` | DOUBLE PRECISION | Maximum value |
| `mean_value` | DOUBLE PRECISION | Mean value |
| `std_value` | DOUBLE PRECISION | Standard deviation |
| `null_count` | INTEGER | Number of null values |
| `outlier_count` | INTEGER | Number of outliers detected |

**Indexes:**
- Primary key on `version_id`
- Composite index on `(feature_id, version)`

### Database Functions

#### `get_feature_lineage(feature_uuid UUID)`

Recursively retrieves feature lineage (all ancestors).

**Returns:** Table with columns:
- `feature_id`: UUID
- `feature_name`: VARCHAR
- `transform_type`: VARCHAR
- `depth`: INTEGER (0 = target feature, 1 = parent, 2 = grandparent, etc.)

**Example:**
```sql
SELECT * FROM features.get_feature_lineage('550e8400-e29b-41d4-a716-446655440000');
```

#### `get_feature_descendants(feature_uuid UUID)`

Retrieves all features derived from a given feature.

**Returns:** Table with columns:
- `feature_id`: UUID
- `feature_name`: VARCHAR
- `transform_type`: VARCHAR

**Example:**
```sql
SELECT * FROM features.get_feature_descendants('550e8400-e29b-41d4-a716-446655440000');
```

### Views

#### `v_active_features`

Shows only active (non-deprecated) features.

```sql
SELECT * FROM features.v_active_features WHERE source = 'bls_ces';
```

#### `v_feature_lineage`

Pre-computed lineage for all features.

```sql
SELECT * FROM features.v_feature_lineage WHERE feature_name = 'treasury_withholdings_lag_0';
```

---

## Quick Start

### Prerequisites

1. PostgreSQL 12+ installed and running
2. Database created: `forecast_labor`
3. Schema initialized: Run `infra/postgres/feature_registry_schema.sql`
4. Python package `psycopg2-binary` installed

### Basic Usage

```python
from features.registry import FeatureRegistry

# Initialize with database backend
registry = FeatureRegistry(
    backend='database',
    db_config={
        'host': 'localhost',
        'port': 5432,
        'database': 'forecast_labor',
        'user': 'forecast_labor',
        'password': 'your_password'
    }
)

# Register a feature
feature_id = registry.register({
    'name': 'ces_total_nonfarm',
    'source': 'bls_ces',
    'frequency': 'monthly',
    'description': 'Total nonfarm payrolls',
    'status': 'active'
})

print(f"Registered feature: {feature_id}")
```

---

## Usage Examples

### 1. Register a Simple Feature

```python
from features.registry import FeatureRegistry

registry = FeatureRegistry(backend='database', db_config={...})

feature_id = registry.register({
    'name': 'treasury_withholdings_raw',
    'source': 'treasury',
    'frequency': 'daily',
    'description': 'Raw daily federal tax withholdings',
    'vintage_date': '2025-01-15',
    'data_type': 'float64',
    'unit': 'millions_usd',
    'status': 'active',
    'tags': {'category': 'raw', 'quality': 'high'}
})
```

### 2. Register a Derived Feature (with Lineage)

```python
# Parent feature
parent_id = registry.register({
    'name': 'treasury_withholdings_raw',
    'source': 'treasury',
    'frequency': 'daily'
})

# Derived feature with lineage
child_id = registry.register({
    'name': 'treasury_withholdings_smoothed',
    'source': 'treasury',
    'frequency': 'daily',
    'description': '7-day moving average of withholdings',
    'depends_on': [parent_id],  # Lineage tracking
    'transform': 'moving_average',
    'transform_params': {'window': 7},
    'is_synthetic': True,
    'status': 'active'
})
```

### 3. Query Features

```python
# Get by ID
feature = registry.get(feature_id)
print(f"Feature name: {feature['name']}")
print(f"Source: {feature['source']}")

# List all features
all_features = registry.list_all()
print(f"Total features: {len(all_features)}")

# Search by criteria
ces_features = registry.search(source='bls_ces', status='active')
daily_features = registry.search(frequency='daily')
```

### 4. Update Feature Metadata

```python
# Update status
registry.update(feature_id, {
    'status': 'deprecated',
    'deprecation_date': '2025-01-20',
    'description': 'Deprecated: Use treasury_withholdings_v2 instead'
})

# Update tags
registry.update(feature_id, {
    'tags': {'category': 'deprecated', 'replaced_by': 'treasury_withholdings_v2'}
})
```

### 5. Delete a Feature

```python
# Soft delete by marking as deprecated
registry.update(feature_id, {'status': 'deprecated'})

# Hard delete (removes from database)
registry.delete(feature_id)
```

---

## Migration Guide

### In-Memory to Database Migration

If you have features registered in-memory and want to migrate to database persistence:

#### Step 1: Export In-Memory Features

```python
from features.registry import FeatureRegistry

# Load in-memory registry (with existing features)
memory_registry = FeatureRegistry(backend='memory')

# ... register features to memory_registry ...

# Export to JSON
features = memory_registry.export_to_dict()

import json
with open('features_backup.json', 'w') as f:
    json.dump(features, f, indent=2)
```

#### Step 2: Import to Database

```python
# Create database registry
db_registry = FeatureRegistry(
    backend='database',
    db_config={
        'host': 'localhost',
        'database': 'forecast_labor',
        'user': 'forecast_labor',
        'password': 'your_password'
    }
)

# Import from JSON
with open('features_backup.json', 'r') as f:
    features = json.load(f)

db_registry.import_from_dict(features)
print(f"Imported {len(features)} features to database")
```

#### Step 3: Validate Migration

```python
# Verify counts match
memory_count = len(memory_registry.list_all())
db_count = len(db_registry.list_all())

assert memory_count == db_count, f"Count mismatch: {memory_count} vs {db_count}"

# Verify feature names match
memory_names = {f['name'] for f in memory_registry.list_all()}
db_names = {f['name'] for f in db_registry.list_all()}

assert memory_names == db_names, "Feature names don't match"

print("✅ Migration validated successfully")
```

### Using the Migration Script

```bash
# Export from memory to JSON
python scripts/migrate_feature_registry.py \
    --source memory \
    --export features_backup.json

# Import from JSON to database
python scripts/migrate_feature_registry.py \
    --target database \
    --import features_backup.json \
    --db-host localhost \
    --db-name forecast_labor \
    --db-user forecast_labor \
    --db-password your_password \
    --validate

# Dry run (test without writing)
python scripts/migrate_feature_registry.py \
    --target database \
    --import features_backup.json \
    --dry-run
```

---

## Lineage Tracking

### Understanding Feature Lineage

Lineage tracks the transformation history of features:

```
Raw Feature → Transform 1 → Transform 2 → Final Feature
```

### Example: Multi-Level Lineage

```python
# Level 0: Raw data
raw_id = registry.register({
    'name': 'ces_total_nonfarm_raw',
    'source': 'bls_ces',
    'frequency': 'monthly'
})

# Level 1: Seasonally adjusted
sa_id = registry.register({
    'name': 'ces_total_nonfarm_sa',
    'source': 'bls_ces',
    'frequency': 'monthly',
    'depends_on': [raw_id],
    'transform': 'seasonal_adjustment',
    'is_synthetic': True
})

# Level 2: Differenced
diff_id = registry.register({
    'name': 'ces_total_nonfarm_mom_change',
    'source': 'bls_ces',
    'frequency': 'monthly',
    'depends_on': [sa_id],
    'transform': 'difference',
    'is_synthetic': True
})
```

### Query Lineage

```python
# Get full lineage (all ancestors)
lineage = registry._db_backend.get_lineage(diff_id)

for item in lineage:
    print(f"Level {item['depth']}: {item['feature_name']} ({item['transform_type']})")

# Output:
# Level 0: ces_total_nonfarm_mom_change (difference)
# Level 1: ces_total_nonfarm_sa (seasonal_adjustment)
# Level 2: ces_total_nonfarm_raw (None)

# Get descendants (all derived features)
descendants = registry._db_backend.get_descendants(raw_id)

for desc in descendants:
    print(f"Derived: {desc['feature_name']} via {desc['transform_type']}")
```

### Lineage Use Cases

1. **Impact Analysis**: Find all features affected by a change
2. **Debugging**: Trace where a feature came from
3. **Documentation**: Understand feature provenance
4. **Reproducibility**: Recreate features from raw data

---

## Versioning Workflow

### Creating Feature Versions

Versions track changes to feature data over time:

```python
# Register initial feature
feature_id = registry.register({
    'name': 'ces_total_nonfarm',
    'source': 'bls_ces',
    'frequency': 'monthly',
    'checksum': 'abc123',  # SHA256 of data
})

# Version 1 created automatically

# Create version 2 (after data update)
version_id = registry._db_backend.create_version(
    feature_id=feature_id,
    checksum='def456',
    row_count=240,
    change_description='Added 12 months of data (Jan-Dec 2024)'
)
```

### Query Version History

```python
# Get all versions
versions = registry._db_backend.get_versions(feature_id)

for v in versions:
    print(f"Version {v['version']}: {v['checksum']}")
    print(f"  Created: {v['created_at']}")
    print(f"  Rows: {v['row_count']}")
    print(f"  Changes: {v['change_description']}")
```

### Version Metadata

Track statistics for each version:

```python
version_id = registry._db_backend.create_version(
    feature_id=feature_id,
    checksum='abc123',
    row_count=1000,
    change_description='Monthly update'
)

# Update version with statistics (done separately after data processing)
# Note: This would require extending the API to update version metadata
```

### Best Practices

1. **Checksum Everything**: Always compute SHA256 hash of feature data
2. **Document Changes**: Provide clear change descriptions
3. **Track Row Counts**: Helps detect data issues
4. **Version on Updates**: Create new version when data changes

---

## Rollback Procedures

### Scenario 1: Revert to Previous Version

```python
# Get version history
versions = registry._db_backend.get_versions(feature_id)

# Find version to revert to
target_version = [v for v in versions if v['version'] == 2][0]

# Load data for that version (application logic)
# Note: Version metadata points to the checksum, but data retrieval
# is handled by your data storage layer (e.g., S3/MinIO)

print(f"Reverting to version {target_version['version']}")
print(f"Checksum: {target_version['checksum']}")

# Update current_version pointer
registry.update(feature_id, {
    'current_version': target_version['version']
})
```

### Scenario 2: Rollback Migration

If database migration fails or has issues:

```bash
# 1. Restore from backup JSON
python scripts/migrate_feature_registry.py \
    --import features_backup.json \
    --target database \
    --validate

# 2. Or switch back to in-memory mode
# In your code:
registry = FeatureRegistry(backend='memory')  # Switch back
```

### Scenario 3: Emergency Recovery

```sql
-- Check database state
SELECT COUNT(*) FROM features.feature_metadata;
SELECT COUNT(*) FROM features.feature_versions;

-- Restore from PostgreSQL backup (if available)
-- psql forecast_labor < backup.sql

-- Or restore from application backup
```

### Backup Strategy

1. **Regular Exports**: Export registry to JSON daily
2. **Database Snapshots**: Use PostgreSQL backup tools
3. **Version Control**: Track schema changes in git
4. **Checksums**: Verify data integrity regularly

```bash
# Daily backup cron job
0 2 * * * python scripts/migrate_feature_registry.py --export /backups/features_$(date +\%Y\%m\%d).json
```

---

## API Reference

### FeatureRegistry Class

#### `__init__(backend, db_config)`

Initialize registry with specified backend.

**Parameters:**
- `backend` (str): 'memory' or 'database'
- `db_config` (dict): Database connection parameters (required if backend='database')
  - `host` (str): Database host
  - `port` (int): Database port (default: 5432)
  - `database` (str): Database name
  - `user` (str): Database user
  - `password` (str): Database password

**Example:**
```python
registry = FeatureRegistry(
    backend='database',
    db_config={'host': 'localhost', 'database': 'forecast_labor'}
)
```

#### `register(feature_data)`

Register a new feature.

**Parameters:**
- `feature_data` (dict): Feature metadata

**Returns:**
- `str`: Feature ID (UUID)

**Required Fields:**
- `name`: Feature name (unique)

**Optional Fields:**
- `source`, `frequency`, `description`, `vintage_date`, `status`, `depends_on`, etc.

#### `get(feature_id)`

Retrieve feature metadata by ID.

**Parameters:**
- `feature_id` (str): Feature UUID

**Returns:**
- `dict`: Feature metadata

**Raises:**
- `KeyError`: If feature not found

#### `list_all()`

List all registered features.

**Returns:**
- `list[dict]`: List of feature metadata dictionaries

#### `search(**filters)`

Search features by criteria.

**Parameters:**
- `**filters`: Field filters (e.g., `source='bls_ces'`, `status='active'`)

**Returns:**
- `list[dict]`: Matching features

#### `update(feature_id, updates)`

Update feature metadata.

**Parameters:**
- `feature_id` (str): Feature UUID
- `updates` (dict): Fields to update

#### `delete(feature_id)`

Delete a feature.

**Parameters:**
- `feature_id` (str): Feature UUID

#### `export_to_dict()`

Export entire registry to dictionary.

**Returns:**
- `list[dict]`: All features with IDs

#### `import_from_dict(features)`

Import features from dictionary.

**Parameters:**
- `features` (list[dict]): Feature metadata dictionaries

### DatabaseBackend Class

Direct database access (for advanced use).

#### `get_lineage(feature_id)`

Get feature lineage (all ancestors).

**Returns:**
- `list[dict]`: Lineage with depth

#### `get_descendants(feature_id)`

Get derived features.

**Returns:**
- `list[dict]`: Descendant features

#### `create_version(feature_id, checksum, ...)`

Create new feature version.

**Returns:**
- `str`: Version ID

#### `get_versions(feature_id)`

Get version history.

**Returns:**
- `list[dict]`: All versions

---

## Troubleshooting

### Connection Issues

**Problem:** `psycopg2.OperationalError: could not connect to server`

**Solution:**
1. Verify PostgreSQL is running: `pg_isready`
2. Check connection parameters (host, port, database)
3. Verify user permissions: `GRANT ALL ON SCHEMA features TO forecast_labor;`

### Missing Schema

**Problem:** `psycopg2.errors.UndefinedTable: relation "features.feature_metadata" does not exist`

**Solution:**
```bash
# Initialize schema
psql -d forecast_labor -f infra/postgres/feature_registry_schema.sql
```

### Duplicate Feature Names

**Problem:** `psycopg2.IntegrityError: duplicate key value violates unique constraint`

**Solution:**
- Feature names must be unique
- Check existing features: `registry.search(name='your_feature_name')`
- Use different name or update existing feature

### Migration Validation Fails

**Problem:** Feature count or checksum mismatch after migration

**Solution:**
1. Check source data: `memory_registry.export_to_dict()`
2. Verify database connection
3. Re-run migration with `--validate` flag
4. Check PostgreSQL logs for errors

### Performance Issues

**Problem:** Slow queries with many features

**Solution:**
1. Ensure indexes are created (check schema)
2. Use filters in `list_features()` instead of `list_all()`
3. Add pagination: `registry._db_backend.list_features(limit=100, offset=0)`
4. Vacuum database: `VACUUM ANALYZE features.feature_metadata;`

### Lineage Query Slow

**Problem:** `get_feature_lineage()` takes too long

**Solution:**
- Lineage depth is typically <5 levels
- If deeper, consider caching or materialized views
- Check `v_feature_lineage` view for pre-computed results

---

## Best Practices

### 1. Feature Naming Convention

Use descriptive, hierarchical names:

```
{source}_{series}_{transform}_{params}

Examples:
- ces_total_nonfarm_raw
- ces_total_nonfarm_sa (seasonally adjusted)
- ces_total_nonfarm_mom_change (month-over-month)
- treasury_withholdings_lag_0
- treasury_withholdings_smoothed_7d
```

### 2. Always Track Vintage Dates

```python
registry.register({
    'name': 'ces_total_nonfarm',
    'vintage_date': '2025-01-15',  # When data was retrieved
    # ...
})
```

### 3. Document Transformations

```python
registry.register({
    'name': 'ces_total_nonfarm_sa',
    'depends_on': [parent_id],
    'transform': 'x13_seasonal_adjustment',
    'transform_params': {'model': 'auto', 'trading_day': True},
    'description': 'Seasonally adjusted using X-13ARIMA-SEATS'
})
```

### 4. Use Status Wisely

- `active`: Production-ready, in use
- `experimental`: Testing, not production
- `deprecated`: No longer recommended
- `draft`: Under development

### 5. Regular Backups

```bash
# Daily export
python scripts/migrate_feature_registry.py --export features_backup.json

# PostgreSQL dump
pg_dump forecast_labor > forecast_labor_$(date +%Y%m%d).sql
```

### 6. Checksum Validation

```python
import hashlib
import pandas as pd

def compute_checksum(df):
    """Compute SHA256 checksum of DataFrame."""
    return hashlib.sha256(df.to_csv(index=False).encode()).hexdigest()

df = pd.read_parquet('features/ces_total_nonfarm.parquet')
checksum = compute_checksum(df)

registry.register({
    'name': 'ces_total_nonfarm',
    'checksum': checksum,
    # ...
})
```

---

## Additional Resources

- **Schema SQL**: `infra/postgres/feature_registry_schema.sql`
- **Schema Docs**: `docs/DATABASE_SCHEMA.md`
- **Migration Script**: `scripts/migrate_feature_registry.py`
- **Source Code**: `features/registry.py`
- **Tests**: `tests/features/test_registry_database.py`

---

**Questions?** Check `docs/DATABASE_SCHEMA.md` for detailed schema documentation.

**Issues?** See troubleshooting section above or check PostgreSQL logs.

