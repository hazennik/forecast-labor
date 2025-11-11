# ===========================
# AI AGENTS SERVICE DOCKERFILE
# ===========================
# AI automation agents for pipeline maintenance
# Optional service (activated with --profile agents)

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
    /app/agents_src \
    /app/repo \
    /app/logs

# Copy requirements and install Python dependencies
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Install agent-specific packages
RUN pip install --no-cache-dir \
    anthropic==0.3.11 \
    langchain==0.0.310 \
    tiktoken==0.5.1

# Set Python path
ENV PYTHONPATH=/app:$PYTHONPATH

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD python3 -c "import sys; sys.exit(0)"

# Keep container running
CMD ["tail", "-f", "/dev/null"]

