# ===========================
# SN41 MINER SERVICE DOCKERFILE
# ===========================
# Bittensor SN41 submission service
# Converts forecasts to probability vectors and submits

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
    /app/sn41 \
    /app/sn41/keys \
    /app/data \
    /app/scripts \
    /app/logs

# Copy requirements and install Python dependencies
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Install Bittensor (commented out until ready for production)
# RUN pip install --no-cache-dir bittensor==6.5.0

# Set Python path
ENV PYTHONPATH=/app:$PYTHONPATH

# Expose health check port
EXPOSE 8080

# Health check endpoint
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8080/health || exit 1

# Keep container running (miner service will run via scripts)
CMD ["tail", "-f", "/dev/null"]

