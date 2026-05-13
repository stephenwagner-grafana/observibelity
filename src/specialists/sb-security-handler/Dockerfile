# syntax=docker/dockerfile:1.7
# sb-security-handler — Support Bot specialist.
# Thin layer on top of the shared specialist-base image.

ARG SPECIALIST_BASE=ghcr.io/stephenwagner-grafana/observibelity-specialist-base:latest
FROM ${SPECIALIST_BASE}

LABEL org.opencontainers.image.title="observibelity-sb-security-handler" \
      org.opencontainers.image.description="Handles security-related queries; refuses confidential disclosure." \
      org.opencontainers.image.source="https://github.com/stephenwagner-grafana/observibelity" \
      org.opencontainers.image.licenses="Apache-2.0"

ENV OTEL_SERVICE_NAME=sb-security-handler \
    SPECIALIST_NAME=sb-security-handler

COPY --chown=app:app app/ /app/app/

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
