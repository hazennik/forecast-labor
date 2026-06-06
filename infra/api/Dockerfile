# ===========================
# API SERVICE DOCKERFILE
# ===========================
# Zone 2 forecast-serving API. Loads signed artifacts only.

FROM python:3.9-slim

ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV TZ=America/New_York

RUN apt-get update && apt-get install -y \
    curl \
    ca-certificates \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
RUN mkdir -p \
    /app/app \
    /app/models_src \
    /app/zone2/runner/artifacts \
    /app/zone2/runner/extracted

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

COPY setup.py /app/setup.py
COPY app /app/app
COPY models_src /app/models_src

ENV PYTHONPATH=/app:$PYTHONPATH
ENV ZONE2_ARTIFACT_DIR=/app/zone2/runner/artifacts
ENV ZONE2_EXTRACT_DIR=/app/zone2/runner/extracted

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
