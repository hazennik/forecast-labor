# ===========================
# MODELS SERVICE DOCKERFILE
# ===========================
# Model training, inference, and evaluation
# DFM, MIDAS, GBM quantile, revision, calibration

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
    gfortran \
    libopenblas-dev \
    liblapack-dev \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Create app directories
WORKDIR /app
RUN mkdir -p \
    /app/models_src \
    /app/features \
    /app/backtests \
    /app/recon \
    /app/data/artifacts \
    /app/data/reports \
    /app/scripts \
    /app/logs

# Copy requirements and install Python dependencies
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Set Python path
ENV PYTHONPATH=/app:$PYTHONPATH

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD python3 -c "import sys; sys.exit(0)"

# Keep container running
CMD ["tail", "-f", "/dev/null"]

