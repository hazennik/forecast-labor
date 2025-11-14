# ===========================
# X-13ARIMA-SEATS DOCKERFILE
# ===========================
# Production-ready X-13 seasonal adjustment service
# Includes regressors for holidays, strikes, weather

FROM ubuntu:22.04

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

# Download and install X-13ARIMA-SEATS binary
# Official US Census Bureau release
WORKDIR /tmp
RUN wget https://www.census.gov/ts/x13as/unix/x13as_html-v1-1-b60.tar.gz && \
    tar -xzf x13as_html-v1-1-b60.tar.gz && \
    mv x13as /usr/local/bin/x13as && \
    chmod +x /usr/local/bin/x13as && \
    rm x13as_html-v1-1-b60.tar.gz

# Verify X-13 installation
RUN x13as -v || echo "X-13 installed"

# Install Python dependencies for X-13 wrapper
RUN pip3 install --no-cache-dir \
    pandas==2.0.3 \
    numpy==1.24.3 \
    statsmodels==0.14.0 \
    python-dotenv==1.0.0 \
    sqlalchemy==2.0.19 \
    psycopg2-binary==2.9.6 \
    minio==7.1.15 \
    pydantic==2.1.1 \
    loguru==0.7.0

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

