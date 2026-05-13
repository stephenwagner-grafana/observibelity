# syntax=docker/dockerfile:1.7
# reset_password — Support Bot tool microservice.
# Thin layer on top of the shared tool-base image.

ARG TOOL_BASE=ghcr.io/stephenwagner-grafana/observibelity-tool-base:latest
FROM ${TOOL_BASE}

LABEL org.opencontainers.image.title="observibelity-reset_password" \
      org.opencontainers.image.description="Trigger an AD password reset (side-effect, stubbed)." \
      org.opencontainers.image.source="https://github.com/stephenwagner-grafana/observibelity" \
      org.opencontainers.image.licenses="Apache-2.0"

ENV OTEL_SERVICE_NAME=reset_password \
    TOOL_NAME=reset_password

COPY --chown=app:app app/ /app/app/

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
