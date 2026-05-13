# syntax=docker/dockerfile:1.7
# Build context: repo root (so we can pull tools/seed-loader.py + seed_data/**)
ARG PYTHON_VERSION=3.12
FROM python:${PYTHON_VERSION}-slim

LABEL org.opencontainers.image.title="observibelity-seed" \
      org.opencontainers.image.description="Seed data loader for ObserVIBElity Postgres" \
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
      "sqlalchemy>=2.0" \
      "psycopg2-binary>=2.9"

# Bake CSVs into the image — seed Job does NOT mount them.
# seed-loader.py defaults to SEED_DIR=/seed_data and rglobs for <table>.csv,
# so any nested subdir layout under /seed_data works.
COPY --chown=app:app seed_data/catalog/       /seed_data/catalog/
COPY --chown=app:app seed_data/personas/      /seed_data/personas/
COPY --chown=app:app seed_data/geo/           /seed_data/geo/
COPY --chown=app:app seed_data/kb/            /seed_data/kb/
COPY --chown=app:app seed_data/orders/        /seed_data/orders/
COPY --chown=app:app seed_data/conversations/ /seed_data/conversations/
COPY --chown=app:app seed_data/tickets/       /seed_data/tickets/

# Loader script (renamed to seed_loader.py so it's a valid Python module name)
COPY --chown=app:app tools/seed-loader.py /app/seed_loader.py

USER app:app

ENV SEED_DIR=/seed_data \
    SEED_DATA_DIR=/seed_data

CMD ["python", "/app/seed_loader.py"]
