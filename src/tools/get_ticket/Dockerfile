# syntax=docker/dockerfile:1.7
# get_ticket — Support Bot tool microservice.
# Thin layer on top of the shared tool-base image.

ARG TOOL_BASE=ghcr.io/stephenwagner-grafana/observibelity-tool-base:latest
FROM ${TOOL_BASE}

LABEL org.opencontainers.image.title="observibelity-get_ticket" \
      org.opencontainers.image.description="Fetch a single support ticket by id." \
      org.opencontainers.image.source="https://github.com/stephenwagner-grafana/observibelity" \
      org.opencontainers.image.licenses="Apache-2.0"

ENV OTEL_SERVICE_NAME=get_ticket \
    TOOL_NAME=get_ticket

COPY --chown=app:app app/ /app/app/

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
