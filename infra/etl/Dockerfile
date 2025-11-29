# ===========================
# ETL SERVICE DOCKERFILE
# ===========================
# Data ingestion, validation, and vintage management
# Handles public and private data sources

# Force x86_64 platform for X-13 binary compatibility
FROM --platform=linux/amd64 python:3.9-slim

# Prevent interactive prompts
ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1
ENV TZ=America/New_York

# Install system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    wget \
    git \
    build-essential \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Create app directories
WORKDIR /app
RUN mkdir -p \
    /app/etl \
    /app/data/raw \
    /app/data/vintages \
    /app/scripts \
    /app/logs

# Copy requirements and install Python dependencies
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Install additional ETL-specific packages
RUN pip install --no-cache-dir \
    beautifulsoup4==4.12.2 \
    lxml==4.9.3 \
    openpyxl==3.1.2 \
    xlrd==2.0.1

# Install X-13ARIMA-SEATS binary for seasonal adjustment
# (ETL container runs seasonal adjustment scripts directly)
RUN apt-get update && apt-get install -y wget ca-certificates && \
    wget -q https://www2.census.gov/software/x-13arima-seats/x13as/unix-linux/program-archives/x13as_ascii-v1-1-b62.tar.gz -O /tmp/x13as.tar.gz && \
    tar -xzf /tmp/x13as.tar.gz -C /tmp && \
    cp /tmp/x13as/x13as_ascii /usr/local/bin/x13as && \
    chmod +x /usr/local/bin/x13as && \
    rm -rf /tmp/x13as* && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# Copy setup.py for package installation
COPY setup.py /app/setup.py

# Install the package in editable mode (makes imports work for pytest)
RUN pip install -e /app

# Set Python path
ENV PYTHONPATH=/app:$PYTHONPATH

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD python3 -c "import sys; sys.exit(0)"

# Keep container running
CMD ["tail", "-f", "/dev/null"]

