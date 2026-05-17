# syntax=docker/dockerfile:1.7
# verify_inventory — LLM-using SKU-forwarding shim with a deliberately
# token-budgeted prompt that truncates the SKU before handing it down to
# nc-best-deals. Thin layer on top of the shared tool-base image.

ARG TOOL_BASE=ghcr.io/stephenwagner-grafana/observibelity-tool-base:latest
FROM ${TOOL_BASE}

LABEL org.opencontainers.image.title="observibelity-tool-verify-inventory" \
      org.opencontainers.image.description="LLM-using inventory verify hop (planted bit-budget truncation)" \
      org.opencontainers.image.source="https://github.com/stephenwagner-grafana/observibelity" \
      org.opencontainers.image.licenses="Apache-2.0"

ENV OTEL_SERVICE_NAME=verify-inventory

COPY --chown=app:app app/ /app/app/

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
