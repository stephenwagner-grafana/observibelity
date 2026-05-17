# syntax=docker/dockerfile:1.7
# query_skus_latest - SQL endpoint that resolves a SKU regex pattern to
# the "latest" SKU candidates for a product (multi-hop retrieval demo).
# Thin layer on top of the shared tool-base image.

ARG TOOL_BASE=ghcr.io/stephenwagner-grafana/observibelity-tool-base:latest
FROM ${TOOL_BASE}

LABEL org.opencontainers.image.title="observibelity-query_skus_latest" \
      org.opencontainers.image.description="Resolve a SKU regex pattern to latest-SKU candidates" \
      org.opencontainers.image.source="https://github.com/stephenwagner-grafana/observibelity" \
      org.opencontainers.image.licenses="Apache-2.0"

ENV OTEL_SERVICE_NAME=query_skus_latest \
    TOOL_NAME=query_skus_latest

COPY --chown=app:app app/ /app/app/

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
