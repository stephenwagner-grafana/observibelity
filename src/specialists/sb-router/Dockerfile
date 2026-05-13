# syntax=docker/dockerfile:1.7
# sb-router — Support Bot specialist.
# Thin layer on top of the shared specialist-base image.

ARG SPECIALIST_BASE=ghcr.io/stephenwagner-grafana/observibelity-specialist-base:latest
FROM ${SPECIALIST_BASE}

LABEL org.opencontainers.image.title="observibelity-sb-router" \
      org.opencontainers.image.description="Routes Ask Acme queries to the right downstream specialist." \
      org.opencontainers.image.source="https://github.com/stephenwagner-grafana/observibelity" \
      org.opencontainers.image.licenses="Apache-2.0"

ENV OTEL_SERVICE_NAME=sb-router \
    SPECIALIST_NAME=sb-router

COPY --chown=app:app app/ /app/app/

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
