# syntax=docker/dockerfile:1.7
# place_order - Order creation / submission tool.
# Thin layer on top of the shared tool-base image.

ARG TOOL_BASE=ghcr.io/stephenwagner-grafana/observibelity-tool-base:0.1.0
FROM ${TOOL_BASE}

LABEL org.opencontainers.image.title="observibelity-place_order" \
      org.opencontainers.image.description="Order creation / submission tool" \
      org.opencontainers.image.source="https://github.com/stephenwagner-grafana/observibelity" \
      org.opencontainers.image.licenses="Apache-2.0"

ENV OTEL_SERVICE_NAME=place_order \
    TOOL_NAME=place_order

COPY --chown=app:app app/ /app/app/

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
