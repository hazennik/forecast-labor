# ===========================
# DASHBOARDS SERVICE DOCKERFILE
# ===========================
# Streamlit dashboard for monitoring and visualization
# Displays accuracy, coverage, coherence, miner health

FROM python:3.9-slim

# Prevent interactive prompts
ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1
ENV TZ=America/New_York

# Install system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    wget \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Create app directories
WORKDIR /app
RUN mkdir -p \
    /app/dashboards_src \
    /app/data \
    /app/logs

# Copy requirements and install Python dependencies
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Install additional dashboard packages
RUN pip install --no-cache-dir \
    altair==5.0.1 \
    plotly-express==0.4.1

# Set Python path
ENV PYTHONPATH=/app:$PYTHONPATH

# Expose Streamlit port
EXPOSE 8501

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8501/_stcore/health || exit 1

# Default command (can be overridden in docker-compose)
CMD ["streamlit", "run", "/app/dashboards_src/streamlit/app.py", "--server.port=8501", "--server.address=0.0.0.0"]

