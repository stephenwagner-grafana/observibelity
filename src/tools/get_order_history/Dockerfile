# syntax=docker/dockerfile:1.7
# get_order_history - Per-user order history lookup tool.
# Thin layer on top of the shared tool-base image.

ARG TOOL_BASE=ghcr.io/stephenwagner-grafana/observibelity-tool-base:0.1.0
FROM ${TOOL_BASE}

LABEL org.opencontainers.image.title="observibelity-get_order_history" \
      org.opencontainers.image.description="Per-user order history lookup tool" \
      org.opencontainers.image.source="https://github.com/stephenwagner-grafana/observibelity" \
      org.opencontainers.image.licenses="Apache-2.0"

ENV OTEL_SERVICE_NAME=get_order_history \
    TOOL_NAME=get_order_history

COPY --chown=app:app app/ /app/app/

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
