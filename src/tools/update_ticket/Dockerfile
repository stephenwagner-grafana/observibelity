# syntax=docker/dockerfile:1.7
# update_ticket — Support Bot tool microservice.
# Thin layer on top of the shared tool-base image.

ARG TOOL_BASE=ghcr.io/stephenwagner-grafana/observibelity-tool-base:latest
FROM ${TOOL_BASE}

LABEL org.opencontainers.image.title="observibelity-update_ticket" \
      org.opencontainers.image.description="Update a support ticket's status/body (side-effect)." \
      org.opencontainers.image.source="https://github.com/stephenwagner-grafana/observibelity" \
      org.opencontainers.image.licenses="Apache-2.0"

ENV OTEL_SERVICE_NAME=update_ticket \
    TOOL_NAME=update_ticket

COPY --chown=app:app app/ /app/app/

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
