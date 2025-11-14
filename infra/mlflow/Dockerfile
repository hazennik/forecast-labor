# ===========================
# MLFLOW TRACKING SERVER DOCKERFILE
# ===========================
# Custom MLflow image with PostgreSQL support
# Based on official MLflow image with additional dependencies

FROM ghcr.io/mlflow/mlflow:v2.5.0

# Install PostgreSQL client library
RUN pip install --no-cache-dir \
    psycopg2-binary==2.9.9

# Add health check dependencies
RUN pip install --no-cache-dir \
    requests==2.31.0

# Set working directory
WORKDIR /mlflow

# Expose MLflow port
EXPOSE 5000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:5000/health')"

# Default command (will be overridden by docker-compose)
CMD ["mlflow", "server", "--host", "0.0.0.0", "--port", "5000"]

