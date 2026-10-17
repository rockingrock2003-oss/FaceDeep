# FaceGate - self-hosted, Rekognition-compatible face recognition (CPU only).
FROM python:3.11-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
RUN apt-get update && apt-get install -y --no-install-recommends libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 10001 facegate

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY facegate/ facegate/
COPY scripts/download_models.py scripts/download_models.py
COPY models/ models/
# Fetch any model that is not already present and verify every checksum.
RUN python scripts/download_models.py

ENV FACEGATE_ENVIRONMENT=production \
    FACEGATE_DATA_DIR=/data \
    FACEGATE_MODELS_DIR=/app/models
RUN mkdir -p /data && chown facegate /data
USER facegate
VOLUME ["/data"]
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=40s \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health').status==200 else 1)"

CMD ["python", "-m", "facegate", "--host", "0.0.0.0", "--port", "8000"]
