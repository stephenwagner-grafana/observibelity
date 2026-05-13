# syntax=docker/dockerfile:1.7
# nc-fulfillment-orchestrator - NeonCart order fulfillment coordination specialist.
# Thin layer on top of the shared specialist-base image.

ARG SPECIALIST_BASE=ghcr.io/stephenwagner-grafana/observibelity-specialist-base:latest
FROM ${SPECIALIST_BASE}

LABEL org.opencontainers.image.title="observibelity-nc-fulfillment-orchestrator" \
      org.opencontainers.image.description="NeonCart order fulfillment coordination specialist" \
      org.opencontainers.image.source="https://github.com/stephenwagner-grafana/observibelity" \
      org.opencontainers.image.licenses="Apache-2.0"

ENV OTEL_SERVICE_NAME=nc-fulfillment-orchestrator \
    SPECIALIST_NAME=nc-fulfillment-orchestrator

COPY --chown=app:app app/ /app/app/

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
