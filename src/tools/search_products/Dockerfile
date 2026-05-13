# syntax=docker/dockerfile:1.7
# search_products - Product catalog search tool.
# Thin layer on top of the shared tool-base image.

ARG TOOL_BASE=ghcr.io/stephenwagner-grafana/observibelity-tool-base:0.1.0
FROM ${TOOL_BASE}

LABEL org.opencontainers.image.title="observibelity-search_products" \
      org.opencontainers.image.description="Product catalog search tool" \
      org.opencontainers.image.source="https://github.com/stephenwagner-grafana/observibelity" \
      org.opencontainers.image.licenses="Apache-2.0"

ENV OTEL_SERVICE_NAME=search_products \
    TOOL_NAME=search_products

COPY --chown=app:app app/ /app/app/

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
