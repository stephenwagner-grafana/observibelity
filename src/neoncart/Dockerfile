# syntax=docker/dockerfile:1.7
# NeonCart - e-commerce frontend (FastAPI + Jinja2 + HTMX)
# Multi-stage build: deps layer for cache; runtime is slim distroless-style.

ARG PYTHON_VERSION=3.12

# --- Builder stage ----------------------------------------------------------
FROM python:${PYTHON_VERSION}-slim AS builder

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    POETRY_VIRTUALENVS_CREATE=false

WORKDIR /build

# Copy pyproject + README + the app/ source so `pip install .` actually
# installs the `app` package (not just its declared deps).
COPY pyproject.toml ./
COPY README.md ./
COPY app/ ./app/

# Install deps + the local `app` package into /opt/venv
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --upgrade pip && \
    pip install .

# --- Runtime stage ----------------------------------------------------------
FROM python:${PYTHON_VERSION}-slim AS runtime

ARG VERSION=0.1.0

LABEL org.opencontainers.image.title="observibelity-neoncart" \
      org.opencontainers.image.description="NeonCart e-commerce frontend" \
      org.opencontainers.image.version="${VERSION}" \
      org.opencontainers.image.source="https://github.com/stephenwagner-grafana/observibelity" \
      org.opencontainers.image.licenses="Apache-2.0"

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    OTEL_SERVICE_NAME=neoncart

# Create non-root user
RUN groupadd -r app --gid=1000 && \
    useradd -r -g app --uid=1000 --home-dir=/app --shell=/sbin/nologin app && \
    mkdir -p /app && chown -R app:app /app

COPY --from=builder --chown=app:app /opt/venv /opt/venv
COPY --from=builder --chown=app:app /build/app /app/app

USER app:app
WORKDIR /app

EXPOSE 8000

HEALTHCHECK --interval=10s --timeout=3s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8000/health',timeout=2).status==200 else 1)"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
