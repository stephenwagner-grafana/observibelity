# syntax=docker/dockerfile:1.7
# llm-gateway - Centralized LLM routing (Anthropic / Ollama / OpenAI compatible)
# Multi-stage build: deps layer for cache; runtime is slim distroless-style.

ARG PYTHON_VERSION=3.12

# --- Builder stage ----------------------------------------------------------
FROM python:${PYTHON_VERSION}-slim AS builder

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    POETRY_VIRTUALENVS_CREATE=false

WORKDIR /build

# Copy only what's needed for dep resolution
COPY pyproject.toml ./
COPY README.md ./

# Install deps into /opt/venv
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --upgrade pip && \
    pip install .

COPY app/ ./app/

# --- Runtime stage ----------------------------------------------------------
FROM python:${PYTHON_VERSION}-slim AS runtime

ARG VERSION=0.1.0

LABEL org.opencontainers.image.title="observibelity-llm-gateway" \
      org.opencontainers.image.description="Centralized LLM routing" \
      org.opencontainers.image.version="${VERSION}" \
      org.opencontainers.image.source="https://github.com/stephenwagner-grafana/observibelity" \
      org.opencontainers.image.licenses="Apache-2.0"

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    OTEL_SERVICE_NAME=llm-gateway

# Create non-root user
RUN groupadd -r app --gid=1000 && \
    useradd -r -g app --uid=1000 --home-dir=/app --shell=/sbin/nologin app && \
    mkdir -p /app && chown -R app:app /app

COPY --from=builder --chown=app:app /opt/venv /opt/venv
COPY --from=builder --chown=app:app /build/app /app/app

USER app:app
WORKDIR /app

EXPOSE 8000

# /health calls Anthropic/Ollama upstream health; allow longer startup.
HEALTHCHECK --interval=15s --timeout=5s --start-period=30s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8000/health',timeout=4).status==200 else 1)"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
