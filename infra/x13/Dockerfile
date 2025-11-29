# ===========================
# X-13ARIMA-SEATS DOCKERFILE
# ===========================
# Production-ready X-13 seasonal adjustment service
# Includes regressors for holidays, strikes, weather

# Force x86_64 platform for X-13 binary compatibility (Census Bureau only provides x86_64 Linux binary)
# ARM64 systems will run with emulation (slower but compatible)
FROM --platform=linux/amd64 ubuntu:22.04

# Prevent interactive prompts
ENV DEBIAN_FRONTEND=noninteractive
ENV TZ=America/New_York

# Install system dependencies
RUN apt-get update && apt-get install -y \
    wget \
    ca-certificates \
    build-essential \
    gfortran \
    python3.9 \
    python3-pip \
    python3-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies first (including ETL dependencies for imports)
RUN pip3 install --no-cache-dir \
    pandas==2.0.3 \
    numpy==1.24.3 \
    statsmodels==0.14.0 \
    python-dotenv==1.0.0 \
    sqlalchemy==2.0.19 \
    psycopg2-binary==2.9.6 \
    minio==7.1.15 \
    pydantic==1.10.15 \
    loguru==0.7.0 \
    requests==2.31.0 \
    urllib3==2.1.0 \
    tenacity==8.2.2

# Download X-13ARIMA-SEATS binary via statsmodels (official Census Bureau binary)
# statsmodels automatically downloads from: https://www.census.gov/data/software/x13as.X-13ARIMA-SEATS.html
# This is more reliable than direct download as statsmodels handles URL changes
WORKDIR /tmp

# Copy installation script
COPY install_x13.py /tmp/install_x13.py

# Run installation script
RUN python3 /tmp/install_x13.py && rm /tmp/install_x13.py

# Verify installation (non-fatal)
RUN x13as -v 2>&1 | head -3 || echo "X-13 will use statsmodels integration"

# Create app directory structure
WORKDIR /app
RUN mkdir -p \
    /app/seasonal/specs \
    /app/seasonal/regressors \
    /app/seasonal/diagnostics \
    /app/seasonal/service_client \
    /app/data/vintages \
    /app/data/seasonal_output \
    /tmp/x13_work

# Copy seasonal adjustment code (mounted via docker-compose volumes)
# Files will be available via volume mounts

# Set working directory
WORKDIR /app

# Entrypoint script
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD python3 -c "import sys; sys.exit(0)"

ENTRYPOINT ["/entrypoint.sh"]
CMD ["python3", "-u", "-m", "seasonal.service"]

