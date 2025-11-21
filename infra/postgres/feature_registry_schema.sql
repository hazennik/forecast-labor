-- ============================================================================
-- Feature Registry Database Schema
-- ============================================================================
-- 
-- This schema provides persistent storage for the feature registry, enabling:
-- - Feature metadata tracking (name, source, frequency, vintage)
-- - Transform lineage tracking (parent-child relationships)
-- - Feature versioning and rollback capabilities
-- - Audit trail and reproducibility
--
-- Schema: features
-- Tables: feature_metadata, feature_transforms, feature_versions
--
-- Created: 2025-11-21
-- ============================================================================

-- Create schema if it doesn't exist
CREATE SCHEMA IF NOT EXISTS features;

-- Set search path for this session
SET search_path TO features, public;

-- ============================================================================
-- Table: feature_metadata
-- ============================================================================
-- 
-- Stores core metadata for each feature including name, source, frequency,
-- and vintage information. This is the primary table for feature discovery.
--

CREATE TABLE IF NOT EXISTS features.feature_metadata (
    -- Primary identifier
    feature_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    
    -- Feature identification
    name VARCHAR(255) NOT NULL,
    display_name VARCHAR(255),
    description TEXT,
    
    -- Source and frequency
    source VARCHAR(100) NOT NULL,  -- e.g., 'bls_ces', 'ui_claims'
    frequency VARCHAR(20) NOT NULL,  -- e.g., 'monthly', 'weekly', 'daily'
    
    -- Data vintage information (critical for reproducibility)
    vintage_date DATE NOT NULL,
    
    -- Feature properties
    data_type VARCHAR(50) NOT NULL DEFAULT 'float64',  -- pandas dtype
    unit VARCHAR(100),  -- e.g., 'thousands', 'percent', 'index'
    seasonal_adjustment VARCHAR(50),  -- e.g., 'SA', 'NSA', 'SAAR'
    
    -- Current version
    current_version INTEGER NOT NULL DEFAULT 1,
    
    -- Status tracking
    status VARCHAR(20) NOT NULL DEFAULT 'active',  -- 'active', 'deprecated', 'archived'
    is_synthetic BOOLEAN NOT NULL DEFAULT FALSE,  -- flag for test data
    
    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    deprecated_at TIMESTAMP WITH TIME ZONE,
    
    -- Metadata
    tags JSONB,  -- flexible key-value pairs for custom metadata
    
    -- Constraints
    CONSTRAINT feature_metadata_name_vintage_unique UNIQUE (name, vintage_date),
    CONSTRAINT feature_metadata_status_check CHECK (status IN ('active', 'deprecated', 'archived')),
    CONSTRAINT feature_metadata_frequency_check CHECK (frequency IN ('daily', 'weekly', 'monthly', 'quarterly', 'annual'))
);

-- Indexes for feature_metadata
CREATE INDEX idx_feature_metadata_name ON features.feature_metadata (name);
CREATE INDEX idx_feature_metadata_source ON features.feature_metadata (source);
CREATE INDEX idx_feature_metadata_vintage_date ON features.feature_metadata (vintage_date);
CREATE INDEX idx_feature_metadata_status ON features.feature_metadata (status);
CREATE INDEX idx_feature_metadata_created_at ON features.feature_metadata (created_at DESC);
CREATE INDEX idx_feature_metadata_tags ON features.feature_metadata USING GIN (tags);

-- Comments for documentation
COMMENT ON TABLE features.feature_metadata IS 'Core metadata for all features in the registry';
COMMENT ON COLUMN features.feature_metadata.feature_id IS 'Unique identifier for the feature';
COMMENT ON COLUMN features.feature_metadata.name IS 'Programmatic name of the feature (e.g., ces_total_nonfarm_sa)';
COMMENT ON COLUMN features.feature_metadata.vintage_date IS 'Vintage date of the data source (critical for reproducibility)';
COMMENT ON COLUMN features.feature_metadata.is_synthetic IS 'Flag indicating if this is synthetic test data';
COMMENT ON COLUMN features.feature_metadata.tags IS 'Flexible JSONB field for custom metadata and tags';


-- ============================================================================
-- Table: feature_transforms
-- ============================================================================
--
-- Tracks the lineage of feature transformations, enabling us to understand
-- how features are derived from raw data and other features. This supports
-- dependency tracking and impact analysis.
--

CREATE TABLE IF NOT EXISTS features.feature_transforms (
    -- Primary identifier
    transform_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    
    -- Feature being created
    feature_id UUID NOT NULL,
    
    -- Transform information
    transform_type VARCHAR(100) NOT NULL,  -- e.g., 'diff', 'log', 'midas_lag', 'seasonal_adj'
    transform_params JSONB,  -- parameters used in the transformation
    
    -- Parent feature (if derived from another feature)
    parent_feature_id UUID,  -- NULL for features derived directly from raw data
    
    -- Execution metadata
    applied_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    applied_by VARCHAR(100),  -- user or system that applied the transform
    
    -- Versioning
    transform_version INTEGER NOT NULL DEFAULT 1,
    
    -- Additional metadata
    notes TEXT,
    
    -- Foreign keys
    CONSTRAINT fk_feature_transforms_feature
        FOREIGN KEY (feature_id) 
        REFERENCES features.feature_metadata (feature_id)
        ON DELETE CASCADE,
    
    CONSTRAINT fk_feature_transforms_parent
        FOREIGN KEY (parent_feature_id)
        REFERENCES features.feature_metadata (feature_id)
        ON DELETE SET NULL,
    
    -- Constraints
    CONSTRAINT feature_transforms_type_check CHECK (
        transform_type IN (
            'diff', 'log', 'log_diff', 'pct_change',
            'midas_lag', 'seasonal_adj', 'detrend',
            'standardize', 'normalize', 'rolling_mean',
            'rolling_std', 'ewm', 'aggregation', 'custom'
        )
    )
);

-- Indexes for feature_transforms
CREATE INDEX idx_feature_transforms_feature_id ON features.feature_transforms (feature_id);
CREATE INDEX idx_feature_transforms_parent_id ON features.feature_transforms (parent_feature_id);
CREATE INDEX idx_feature_transforms_type ON features.feature_transforms (transform_type);
CREATE INDEX idx_feature_transforms_applied_at ON features.feature_transforms (applied_at DESC);

-- Comments for documentation
COMMENT ON TABLE features.feature_transforms IS 'Tracks feature transformation lineage and dependencies';
COMMENT ON COLUMN features.feature_transforms.transform_type IS 'Type of transformation applied (e.g., diff, log, seasonal_adj)';
COMMENT ON COLUMN features.feature_transforms.transform_params IS 'JSONB parameters used in the transformation';
COMMENT ON COLUMN features.feature_transforms.parent_feature_id IS 'Parent feature ID if derived from another feature';


-- ============================================================================
-- Table: feature_versions
-- ============================================================================
--
-- Tracks versions of each feature, enabling rollback and version comparison.
-- Each version includes a checksum for data integrity verification.
--

CREATE TABLE IF NOT EXISTS features.feature_versions (
    -- Primary identifier
    version_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    
    -- Feature reference
    feature_id UUID NOT NULL,
    
    -- Version information
    version INTEGER NOT NULL,
    
    -- Data integrity
    checksum VARCHAR(64) NOT NULL,  -- SHA256 hash of feature data
    row_count BIGINT,
    null_count BIGINT,
    
    -- Statistical summary (for quick validation)
    min_value DOUBLE PRECISION,
    max_value DOUBLE PRECISION,
    mean_value DOUBLE PRECISION,
    std_dev DOUBLE PRECISION,
    
    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    deprecated_at TIMESTAMP WITH TIME ZONE,
    
    -- Version metadata
    change_description TEXT,
    created_by VARCHAR(100),
    
    -- Storage reference (if data is stored externally)
    storage_location TEXT,  -- e.g., S3/MinIO path
    
    -- Foreign keys
    CONSTRAINT fk_feature_versions_feature
        FOREIGN KEY (feature_id)
        REFERENCES features.feature_metadata (feature_id)
        ON DELETE CASCADE,
    
    -- Constraints
    CONSTRAINT feature_versions_unique UNIQUE (feature_id, version),
    CONSTRAINT feature_versions_version_positive CHECK (version > 0)
);

-- Indexes for feature_versions
CREATE INDEX idx_feature_versions_feature_id ON features.feature_versions (feature_id);
CREATE INDEX idx_feature_versions_version ON features.feature_versions (version DESC);
CREATE INDEX idx_feature_versions_checksum ON features.feature_versions (checksum);
CREATE INDEX idx_feature_versions_created_at ON features.feature_versions (created_at DESC);

-- Comments for documentation
COMMENT ON TABLE features.feature_versions IS 'Tracks versions of features for rollback and comparison';
COMMENT ON COLUMN features.feature_versions.version IS 'Version number (1, 2, 3, ...)';
COMMENT ON COLUMN features.feature_versions.checksum IS 'SHA256 hash of feature data for integrity verification';
COMMENT ON COLUMN features.feature_versions.storage_location IS 'External storage path (e.g., s3://bucket/features/...)';


-- ============================================================================
-- Functions and Triggers
-- ============================================================================

-- Function to update updated_at timestamp
CREATE OR REPLACE FUNCTION features.update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Trigger to automatically update updated_at on feature_metadata
CREATE TRIGGER trigger_feature_metadata_updated_at
    BEFORE UPDATE ON features.feature_metadata
    FOR EACH ROW
    EXECUTE FUNCTION features.update_updated_at_column();

-- Function to get feature lineage (recursive CTE)
CREATE OR REPLACE FUNCTION features.get_feature_lineage(p_feature_id UUID)
RETURNS TABLE (
    feature_id UUID,
    feature_name VARCHAR(255),
    transform_type VARCHAR(100),
    depth INTEGER
) AS $$
BEGIN
    RETURN QUERY
    WITH RECURSIVE lineage AS (
        -- Base case: the feature itself
        SELECT 
            fm.feature_id,
            fm.name AS feature_name,
            ft.transform_type,
            0 AS depth
        FROM features.feature_metadata fm
        LEFT JOIN features.feature_transforms ft ON fm.feature_id = ft.feature_id
        WHERE fm.feature_id = p_feature_id
        
        UNION ALL
        
        -- Recursive case: parent features
        SELECT 
            fm.feature_id,
            fm.name AS feature_name,
            ft.transform_type,
            l.depth + 1
        FROM lineage l
        JOIN features.feature_transforms ft ON l.feature_id = ft.feature_id
        JOIN features.feature_metadata fm ON ft.parent_feature_id = fm.feature_id
        WHERE ft.parent_feature_id IS NOT NULL
    )
    SELECT * FROM lineage
    ORDER BY depth;
END;
$$ LANGUAGE plpgsql;

-- Function to get feature descendants (features derived from this feature)
CREATE OR REPLACE FUNCTION features.get_feature_descendants(p_feature_id UUID)
RETURNS TABLE (
    feature_id UUID,
    feature_name VARCHAR(255),
    transform_type VARCHAR(100)
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        fm.feature_id,
        fm.name AS feature_name,
        ft.transform_type
    FROM features.feature_transforms ft
    JOIN features.feature_metadata fm ON ft.feature_id = fm.feature_id
    WHERE ft.parent_feature_id = p_feature_id;
END;
$$ LANGUAGE plpgsql;


-- ============================================================================
-- Views for Common Queries
-- ============================================================================

-- View: Active features with latest version info
CREATE OR REPLACE VIEW features.v_active_features AS
SELECT 
    fm.feature_id,
    fm.name,
    fm.display_name,
    fm.source,
    fm.frequency,
    fm.vintage_date,
    fm.current_version,
    fm.created_at,
    fm.updated_at,
    fv.checksum AS latest_checksum,
    fv.row_count,
    fv.created_at AS version_created_at
FROM features.feature_metadata fm
LEFT JOIN features.feature_versions fv 
    ON fm.feature_id = fv.feature_id 
    AND fm.current_version = fv.version
WHERE fm.status = 'active';

COMMENT ON VIEW features.v_active_features IS 'Active features with their latest version information';

-- View: Feature lineage summary
CREATE OR REPLACE VIEW features.v_feature_lineage AS
SELECT 
    fm.feature_id,
    fm.name AS feature_name,
    fm.source,
    ft.transform_type,
    parent_fm.name AS parent_feature_name,
    ft.transform_params,
    ft.applied_at
FROM features.feature_metadata fm
LEFT JOIN features.feature_transforms ft ON fm.feature_id = ft.feature_id
LEFT JOIN features.feature_metadata parent_fm ON ft.parent_feature_id = parent_fm.feature_id
WHERE fm.status = 'active';

COMMENT ON VIEW features.v_feature_lineage IS 'Feature transformation lineage with parent relationships';


-- ============================================================================
-- Initial Setup Complete
-- ============================================================================

-- Grant permissions (adjust as needed for your environment)
-- Example: GRANT ALL ON SCHEMA features TO feature_registry_app;
-- Example: GRANT SELECT ON ALL TABLES IN SCHEMA features TO feature_registry_readonly;

-- Insert system metadata
INSERT INTO features.feature_metadata (
    name,
    display_name,
    description,
    source,
    frequency,
    vintage_date,
    status,
    is_synthetic,
    tags
) VALUES (
    '_system_metadata',
    'System Metadata',
    'System metadata feature for tracking registry setup',
    'system',
    'daily',
    CURRENT_DATE,
    'active',
    FALSE,
    '{"schema_version": "1.0.0", "created_date": "2025-11-21"}'::JSONB
) ON CONFLICT (name, vintage_date) DO NOTHING;

-- Success message
DO $$
BEGIN
    RAISE NOTICE 'Feature registry schema created successfully!';
    RAISE NOTICE 'Tables created: feature_metadata, feature_transforms, feature_versions';
    RAISE NOTICE 'Views created: v_active_features, v_feature_lineage';
    RAISE NOTICE 'Functions created: get_feature_lineage, get_feature_descendants';
END $$;

