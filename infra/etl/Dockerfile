# ===========================
# ETL SERVICE DOCKERFILE
# ===========================
# Data ingestion, validation, and vintage management
# Handles public and private data sources

FROM python:3.9-slim

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

