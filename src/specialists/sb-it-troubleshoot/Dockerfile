# syntax=docker/dockerfile:1.7
# sb-it-troubleshoot — Support Bot specialist.
# Thin layer on top of the shared specialist-base image.

ARG SPECIALIST_BASE=ghcr.io/stephenwagner-grafana/observibelity-specialist-base:latest
FROM ${SPECIALIST_BASE}

LABEL org.opencontainers.image.title="observibelity-sb-it-troubleshoot" \
      org.opencontainers.image.description="Handles IT support: password reset, VPN, badge access." \
      org.opencontainers.image.source="https://github.com/stephenwagner-grafana/observibelity" \
      org.opencontainers.image.licenses="Apache-2.0"

ENV OTEL_SERVICE_NAME=sb-it-troubleshoot \
    SPECIALIST_NAME=sb-it-troubleshoot

COPY --chown=app:app app/ /app/app/

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
