# ── Stage 0: build React frontend ─────────────────────────────────────────────
# Produces dashboard/dist/ which FastAPI serves as static files.
# VITE_API_URL is intentionally empty — the app is served from the same origin
# as the API, so all fetch calls use relative URLs (/api/...).
FROM node:20-alpine AS frontend
WORKDIR /dashboard
COPY dashboard/package.json dashboard/package-lock.json ./
RUN npm ci
COPY dashboard/ ./
RUN VITE_API_URL="" npm run build

# ── Stage 1: build dependencies ───────────────────────────────────────────────
FROM python:3.11-slim AS builder

WORKDIR /build

# System deps for psycopg2 + Pillow + OpenCV
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ libpq-dev libffi-dev libssl-dev \
    libglib2.0-0 libgl1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

# Install CPU-only PyTorch first (much smaller than CUDA build — ~280 MB vs 2 GB)
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir \
        torch==2.3.0 torchvision==0.18.0 \
        --index-url https://download.pytorch.org/whl/cpu

# Install remaining dependencies
RUN pip install --no-cache-dir -r requirements.txt

# ── Stage 2: runtime image ─────────────────────────────────────────────────────
FROM python:3.11-slim AS runtime

WORKDIR /app

# Runtime-only system libraries
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 libglib2.0-0 libgl1 curl \
    && rm -rf /var/lib/apt/lists/*

# Copy installed packages from builder
COPY --from=builder /usr/local/lib/python3.11 /usr/local/lib/python3.11
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy application code
COPY . .

# Copy pre-built React frontend (served by FastAPI for single-URL access)
COPY --from=frontend /dashboard/dist /app/dashboard/dist

# Don't run as root in production
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

# Health check (Railway / Render will probe this)
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
  CMD curl -f http://localhost:${PORT:-8000}/health || exit 1

EXPOSE 8000

# Default: API server.
# Override CMD in platform config to run celery worker/beat.
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 2"]
