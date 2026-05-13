# syntax=docker/dockerfile:1.7
# sb-kb-search — Support Bot specialist.
# Thin layer on top of the shared specialist-base image.

ARG SPECIALIST_BASE=ghcr.io/stephenwagner-grafana/observibelity-specialist-base:latest
FROM ${SPECIALIST_BASE}

LABEL org.opencontainers.image.title="observibelity-sb-kb-search" \
      org.opencontainers.image.description="Searches the supportbot knowledge base for relevant articles." \
      org.opencontainers.image.source="https://github.com/stephenwagner-grafana/observibelity" \
      org.opencontainers.image.licenses="Apache-2.0"

ENV OTEL_SERVICE_NAME=sb-kb-search \
    SPECIALIST_NAME=sb-kb-search

COPY --chown=app:app app/ /app/app/

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
