#!/bin/bash
# ===========================
# X-13 SERVICE ENTRYPOINT
# ===========================
# Initializes X-13 seasonal adjustment service
# Validates environment and creates working directories

set -e

echo "========================================="
echo "X-13 Seasonal Adjustment Service"
echo "========================================="

# Validate X-13 binary (non-fatal - can use statsmodels instead)
if ! command -v x13as &> /dev/null; then
    echo "WARNING: x13as binary not found in PATH"
    echo "✓ Will use statsmodels X-13 integration instead"
else
    echo "✓ X-13 binary found: $(x13as -v 2>&1 | head -1 || echo 'v1.1-b60')"
fi

# Create working directories
mkdir -p /app/data/seasonal_output
mkdir -p /tmp/x13_work
chmod 755 /tmp/x13_work

echo "✓ Working directories created"

# Validate environment variables
if [ -z "$POSTGRES_HOST" ]; then
    echo "WARNING: POSTGRES_HOST not set, using default: postgres"
    export POSTGRES_HOST="postgres"
fi

if [ -z "$MINIO_ENDPOINT" ]; then
    echo "WARNING: MINIO_ENDPOINT not set, using default: http://minio:9000"
    export MINIO_ENDPOINT="http://minio:9000"
fi

echo "✓ Environment validated"
echo ""
echo "Configuration:"
echo "  - Postgres: $POSTGRES_HOST"
echo "  - MinIO: $MINIO_ENDPOINT"
echo "  - Work dir: /tmp/x13_work"
echo ""

# Execute the command passed to docker run
exec "$@"

