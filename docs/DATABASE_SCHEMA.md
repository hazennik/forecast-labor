# Database Schema Documentation

## Feature Registry Database Schema

**Version:** 1.0.0  
**Last Updated:** 2025-11-21  
**Schema Location:** `infra/postgres/feature_registry_schema.sql`

---

## Overview

The Feature Registry Database provides persistent storage for feature metadata, enabling:

- **Feature Discovery:** Search and filter features by name, source, vintage, frequency
- **Lineage Tracking:** Understand feature derivation and dependencies
- **Versioning:** Track feature versions with rollback capabilities
- **Audit Trail:** Complete history of feature creation and modifications
- **Reproducibility:** Tie features to specific data vintages for deterministic pipelines

---

## Schema Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                    features.feature_metadata                 │
├─────────────────────────────────────────────────────────────┤
│ PK  feature_id           UUID                                │
│     name                 VARCHAR(255)        NOT NULL        │
│     display_name         VARCHAR(255)                        │
│     description          TEXT                                │
│     source               VARCHAR(100)        NOT NULL        │
│     frequency            VARCHAR(20)         NOT NULL        │
│     vintage_date         DATE                NOT NULL        │
│     data_type            VARCHAR(50)         NOT NULL        │
│     unit                 VARCHAR(100)                        │
│     seasonal_adjustment  VARCHAR(50)                         │
│     current_version      INTEGER             NOT NULL        │
│     status               VARCHAR(20)         NOT NULL        │
│     is_synthetic         BOOLEAN             NOT NULL        │
│     created_at           TIMESTAMP WITH TZ   NOT NULL        │
│     updated_at           TIMESTAMP WITH TZ   NOT NULL        │
│     deprecated_at        TIMESTAMP WITH TZ                   │
│     tags                 JSONB                               │
│                                                               │
│ UNIQUE (name, vintage_date)                                  │
│ CHECK (status IN ('active', 'deprecated', 'archived'))       │
└─────────────────────────────────────────────────────────────┘
                              │
                              │ 1
                              │
                              ├─────────────────────┐
                              │                     │
                              │ *                   │ *
┌─────────────────────────────▼──────┐   ┌─────────▼────────────────────────┐
│  features.feature_transforms       │   │  features.feature_versions       │
├────────────────────────────────────┤   ├──────────────────────────────────┤
│ PK  transform_id      UUID         │   │ PK  version_id       UUID        │
│ FK  feature_id        UUID         │   │ FK  feature_id       UUID        │
│     transform_type    VARCHAR(100) │   │     version          INTEGER     │
│     transform_params  JSONB        │   │     checksum         VARCHAR(64) │
│ FK  parent_feature_id UUID         │   │     row_count        BIGINT      │
│     applied_at        TIMESTAMP    │   │     null_count       BIGINT      │
│     applied_by        VARCHAR(100) │   │     min_value        DOUBLE      │
│     transform_version INTEGER      │   │     max_value        DOUBLE      │
│     notes             TEXT         │   │     mean_value       DOUBLE      │
│                                    │   │     std_dev          DOUBLE      │
│ ON DELETE CASCADE                  │   │     created_at       TIMESTAMP   │
│ ON DELETE SET NULL (parent)        │   │     deprecated_at    TIMESTAMP   │
└────────────────────────────────────┘   │     change_description TEXT      │
              │                           │     created_by       VARCHAR(100)│
              │ self-referencing          │     storage_location TEXT        │
              └───────────────────┐       │                                  │
                                  │       │ UNIQUE (feature_id, version)     │
                                  └───────│ ON DELETE CASCADE                │
                                          └──────────────────────────────────┘
```

---

## Table Descriptions

### 1. `features.feature_metadata`

**Purpose:** Core metadata table storing feature information.

**Key Fields:**
- `feature_id` (PK): Unique identifier (UUID)
- `name`: Programmatic name (e.g., `ces_total_nonfarm_sa`)
- `source`: Data source (e.g., `bls_ces`, `ui_claims`)
- `frequency`: Data frequency (`daily`, `weekly`, `monthly`, `quarterly`, `annual`)
- `vintage_date`: Date of data vintage (critical for reproducibility)
- `current_version`: Current version number
- `status`: Feature status (`active`, `deprecated`, `archived`)
- `is_synthetic`: Flag for test data
- `tags`: JSONB field for flexible metadata

**Indexes:**
- `idx_feature_metadata_name` - Fast lookup by name
- `idx_feature_metadata_source` - Filter by data source
- `idx_feature_metadata_vintage_date` - Filter by vintage
- `idx_feature_metadata_status` - Filter by status
- `idx_feature_metadata_created_at` - Chronological ordering
- `idx_feature_metadata_tags` - GIN index for JSONB queries

**Constraints:**
- Unique constraint on `(name, vintage_date)` - Prevent duplicate features per vintage
- Check constraint on `status` - Valid values only
- Check constraint on `frequency` - Valid frequencies only

---

### 2. `features.feature_transforms`

**Purpose:** Tracks feature transformation lineage and dependencies.

**Key Fields:**
- `transform_id` (PK): Unique identifier (UUID)
- `feature_id` (FK): Feature being created
- `transform_type`: Type of transformation (e.g., `diff`, `log`, `seasonal_adj`)
- `transform_params`: JSONB parameters used
- `parent_feature_id` (FK): Parent feature (NULL if raw data)
- `applied_at`: Timestamp of transformation

**Supported Transform Types:**
- `diff` - First difference
- `log` - Logarithm
- `log_diff` - Log difference
- `pct_change` - Percentage change
- `midas_lag` - MIDAS lag construction
- `seasonal_adj` - Seasonal adjustment
- `detrend` - Detrending
- `standardize` - Standardization (z-score)
- `normalize` - Min-max normalization
- `rolling_mean` - Rolling average
- `rolling_std` - Rolling standard deviation
- `ewm` - Exponentially weighted moving average
- `aggregation` - Temporal aggregation
- `custom` - Custom transformation

**Relationships:**
- Self-referencing foreign key allows tracking multi-level transformations
- Cascade delete when parent feature is deleted
- Set NULL on parent delete (orphaned transforms retained)

**Indexes:**
- `idx_feature_transforms_feature_id` - Find transforms for a feature
- `idx_feature_transforms_parent_id` - Find derived features
- `idx_feature_transforms_type` - Filter by transform type
- `idx_feature_transforms_applied_at` - Chronological ordering

---

### 3. `features.feature_versions`

**Purpose:** Version control for features with integrity verification.

**Key Fields:**
- `version_id` (PK): Unique identifier (UUID)
- `feature_id` (FK): Feature reference
- `version`: Version number (1, 2, 3, ...)
- `checksum`: SHA256 hash for data integrity
- `row_count`, `null_count`: Data quality metrics
- `min_value`, `max_value`, `mean_value`, `std_dev`: Statistical summary
- `storage_location`: External storage path (e.g., S3/MinIO)

**Use Cases:**
- **Rollback:** Revert to previous version if issues detected
- **Comparison:** Compare versions to understand changes
- **Validation:** Verify data integrity using checksums
- **Auditing:** Track who created each version and when

**Indexes:**
- `idx_feature_versions_feature_id` - Find versions for a feature
- `idx_feature_versions_version` - Sort by version number
- `idx_feature_versions_checksum` - Integrity verification
- `idx_feature_versions_created_at` - Chronological ordering

**Constraints:**
- Unique constraint on `(feature_id, version)` - One version per number
- Check constraint on `version` - Must be positive

---

## Database Functions

### `get_feature_lineage(feature_id UUID)`

**Purpose:** Recursively retrieves the full lineage of a feature.

**Returns:** Table with columns:
- `feature_id`: Feature UUID
- `feature_name`: Feature name
- `transform_type`: Transformation applied
- `depth`: Depth in lineage tree (0 = target feature)

**Example:**
```sql
SELECT * FROM features.get_feature_lineage('a1b2c3d4-...');
```

**Output:**
```
feature_id | feature_name           | transform_type | depth
-----------+------------------------+----------------+-------
a1b2c3d4   | ces_total_nonfarm_diff | diff           | 0
e5f6g7h8   | ces_total_nonfarm_sa   | seasonal_adj   | 1
i9j0k1l2   | ces_total_nonfarm_raw  | NULL           | 2
```

---

### `get_feature_descendants(feature_id UUID)`

**Purpose:** Finds all features derived from a given feature.

**Returns:** Table with columns:
- `feature_id`: Derived feature UUID
- `feature_name`: Derived feature name
- `transform_type`: Transformation applied

**Example:**
```sql
SELECT * FROM features.get_feature_descendants('e5f6g7h8-...');
```

---

## Database Views

### `v_active_features`

**Purpose:** Shows active features with latest version information.

**Columns:**
- All `feature_metadata` columns
- `latest_checksum`: Checksum of current version
- `row_count`: Number of rows in current version
- `version_created_at`: When current version was created

**Example:**
```sql
SELECT name, source, frequency, current_version, row_count
FROM features.v_active_features
WHERE source = 'bls_ces'
ORDER BY created_at DESC
LIMIT 10;
```

---

### `v_feature_lineage`

**Purpose:** Shows feature transformation relationships.

**Columns:**
- `feature_id`, `feature_name`: Target feature
- `source`: Data source
- `transform_type`: Transformation applied
- `parent_feature_name`: Parent feature name
- `transform_params`: Transformation parameters
- `applied_at`: Timestamp

**Example:**
```sql
SELECT 
    feature_name,
    transform_type,
    parent_feature_name,
    transform_params
FROM features.v_feature_lineage
WHERE transform_type = 'seasonal_adj'
ORDER BY applied_at DESC;
```

---

## Common Query Patterns

### Find Feature by Name
```sql
SELECT * 
FROM features.feature_metadata
WHERE name = 'ces_total_nonfarm_sa'
  AND vintage_date = '2025-01-01';
```

### List All Active Features
```sql
SELECT name, source, frequency, current_version
FROM features.v_active_features
ORDER BY created_at DESC;
```

### Find Features by Source
```sql
SELECT name, frequency, vintage_date
FROM features.feature_metadata
WHERE source = 'bls_ces'
  AND status = 'active'
ORDER BY name;
```

### Get Feature Lineage
```sql
-- Find all ancestors of a feature
SELECT * 
FROM features.get_feature_lineage('a1b2c3d4-5e6f-7g8h-9i0j-k1l2m3n4o5p6');

-- Find all descendants of a feature
SELECT * 
FROM features.get_feature_descendants('a1b2c3d4-5e6f-7g8h-9i0j-k1l2m3n4o5p6');
```

### Get Feature Version History
```sql
SELECT 
    version,
    checksum,
    row_count,
    created_at,
    change_description
FROM features.feature_versions
WHERE feature_id = 'a1b2c3d4-5e6f-7g8h-9i0j-k1l2m3n4o5p6'
ORDER BY version DESC;
```

### Find Features Using Specific Transform
```sql
SELECT 
    fm.name,
    ft.transform_params,
    ft.applied_at
FROM features.feature_transforms ft
JOIN features.feature_metadata fm ON ft.feature_id = fm.feature_id
WHERE ft.transform_type = 'seasonal_adj'
  AND fm.status = 'active'
ORDER BY ft.applied_at DESC;
```

### Search Features by Tag
```sql
SELECT name, tags
FROM features.feature_metadata
WHERE tags @> '{"category": "employment"}'::JSONB
  AND status = 'active';
```

---

## Schema Evolution

### Version History

| Version | Date       | Changes                                      |
|---------|------------|----------------------------------------------|
| 1.0.0   | 2025-11-21 | Initial schema with 3 tables, views, functions |

### Future Enhancements

Planned additions for later phases:
- **Feature dependencies graph:** Materialized view for complex lineage queries
- **Feature usage tracking:** Track which models use which features
- **Feature quality metrics:** Store data quality scores over time
- **Feature documentation:** Link to external documentation (Confluence, etc.)
- **Access control:** Row-level security for sensitive features

---

## Migration Guide

### Initial Setup

```bash
# Run schema creation script
psql -h localhost -U forecast_labor -d forecast_labor_db \
     -f infra/postgres/feature_registry_schema.sql
```

### Migrating from In-Memory Registry

Use the migration script (to be implemented in Phase 5.2.2):

```bash
python scripts/migrate_feature_registry.py \
    --source in-memory \
    --target database \
    --validate
```

### Backup and Restore

```bash
# Backup schema and data
pg_dump -h localhost -U forecast_labor -d forecast_labor_db \
        -n features > feature_registry_backup.sql

# Restore
psql -h localhost -U forecast_labor -d forecast_labor_db \
     -f feature_registry_backup.sql
```

---

## Performance Considerations

### Index Usage

All queries should leverage indexes:
- Name lookups use `idx_feature_metadata_name`
- Source filtering uses `idx_feature_metadata_source`
- Vintage filtering uses `idx_feature_metadata_vintage_date`
- Tag searches use GIN index on `tags` JSONB field

### Query Optimization

- Use `EXPLAIN ANALYZE` to verify index usage
- Consider partitioning by `vintage_date` for very large datasets
- Use connection pooling (e.g., PgBouncer) for high concurrency
- Enable query logging for slow queries (> 1s)

### Maintenance

- Run `VACUUM ANALYZE` regularly to update statistics
- Monitor table bloat with `pg_stat_user_tables`
- Set up automated backups (daily recommended)

---

## Security

### Recommended Permissions

```sql
-- Application user (read/write)
GRANT USAGE ON SCHEMA features TO feature_registry_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA features TO feature_registry_app;
GRANT SELECT ON ALL SEQUENCES IN SCHEMA features TO feature_registry_app;

-- Read-only user (analytics, reporting)
GRANT USAGE ON SCHEMA features TO feature_registry_readonly;
GRANT SELECT ON ALL TABLES IN SCHEMA features TO feature_registry_readonly;

-- Restrict direct access to sensitive fields if needed
-- (Implement row-level security in future versions)
```

### Best Practices

- Use connection pooling with separate credentials for read vs. write
- Never store credentials in code (use environment variables)
- Enable SSL for database connections in production
- Audit all schema changes and migrations
- Monitor for suspicious query patterns

---

## Troubleshooting

### Common Issues

**Problem:** Duplicate feature registration fails
```
ERROR: duplicate key value violates unique constraint "feature_metadata_name_vintage_unique"
```
**Solution:** Check if feature already exists for that vintage date.

**Problem:** Foreign key constraint violation on delete
```
ERROR: update or delete on table "feature_metadata" violates foreign key constraint
```
**Solution:** Use CASCADE delete or manually remove dependent records first.

**Problem:** Slow queries on tag search
```sql
-- Bad: Sequential scan
WHERE tags->>'category' = 'employment'

-- Good: Uses GIN index
WHERE tags @> '{"category": "employment"}'::JSONB
```

---

## References

- **PostgreSQL Documentation:** https://www.postgresql.org/docs/
- **JSONB Indexing:** https://www.postgresql.org/docs/current/datatype-json.html
- **Recursive CTEs:** https://www.postgresql.org/docs/current/queries-with.html

---

**Document Version:** 1.0.0  
**Maintained By:** Forecast-Labor Development Team  
**Last Review:** 2025-11-21

