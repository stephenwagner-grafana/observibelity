# syntax=docker/dockerfile:1.7
# nc-fraud-detector - NeonCart transaction fraud assessment specialist.
# Thin layer on top of the shared specialist-base image.

ARG SPECIALIST_BASE=ghcr.io/stephenwagner-grafana/observibelity-specialist-base:0.1.0
FROM ${SPECIALIST_BASE}

LABEL org.opencontainers.image.title="observibelity-nc-fraud-detector" \
      org.opencontainers.image.description="NeonCart transaction fraud assessment specialist" \
      org.opencontainers.image.source="https://github.com/stephenwagner-grafana/observibelity" \
      org.opencontainers.image.licenses="Apache-2.0"

ENV OTEL_SERVICE_NAME=nc-fraud-detector \
    SPECIALIST_NAME=nc-fraud-detector

COPY --chown=app:app app/ /app/app/

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
