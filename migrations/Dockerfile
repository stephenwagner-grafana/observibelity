# syntax=docker/dockerfile:1.7
ARG PYTHON_VERSION=3.12
FROM python:${PYTHON_VERSION}-slim

LABEL org.opencontainers.image.title="observibelity-migrate" \
      org.opencontainers.image.description="Alembic migrations runner for ObserVIBElity Postgres" \
      org.opencontainers.image.source="https://github.com/stephenwagner-grafana/observibelity"

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update && apt-get install -y --no-install-recommends \
      libpq5 \
    && rm -rf /var/lib/apt/lists/*

RUN groupadd -r app --gid=1000 && \
    useradd -r -g app --uid=1000 --home-dir=/app --shell=/sbin/nologin app && \
    mkdir -p /app && chown -R app:app /app

WORKDIR /app

RUN pip install --no-cache-dir \
      "alembic>=1.13" \
      "sqlalchemy[asyncio]>=2.0" \
      "psycopg2-binary>=2.9" \
      "asyncpg>=0.30"

# Copy migrations (build context is the migrations/ directory)
COPY --chown=app:app alembic.ini ./alembic.ini
COPY --chown=app:app env.py ./env.py
COPY --chown=app:app versions ./versions

USER app:app

CMD ["alembic", "upgrade", "head"]
