# Multi-stage Dockerfile für Hugo Backend
# Build-Stage: Abhängigkeiten installieren
# Runtime-Stage: Schlankes Produktions-Image

# Stage 1: Builder
FROM python:3.12-slim AS builder

WORKDIR /build

# Installiere Build-Dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Kopiere requirements.txt und installiere Python-Dependencies
COPY backend/requirements.txt .
RUN pip install --user --no-cache-dir -r requirements.txt

# Stage 2: Runtime
FROM python:3.12-slim

# Setze Arbeitsverzeichnis
WORKDIR /app

# Installiere Runtime-Dependencies (ohne Build-Tools)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Erstelle Non-Root User
RUN groupadd -r hugo && useradd -r -g hugo hugo

# Kopiere Python-Dependencies vom Builder
COPY --from=builder /root/.local /home/hugo/.local

# Kopiere die Backend-Anwendung
COPY backend/app /app/app
COPY backend/migrations /app/migrations
COPY backend/schema.sql /app/

# Setze Permissions
RUN chown -R hugo:hugo /app

# Wechsle zu Non-Root User
USER hugo

# Setze PATH für pip install --user
ENV PATH=/home/hugo/.local/bin:$PATH
ENV PYTHONUNBUFFERED=1

# Healthcheck für die App (Port 8000)
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Standard-Entrypoint: Web-Server (FastAPI)
# Worker kann mit "python -m app.worker" überschrieben werden
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
