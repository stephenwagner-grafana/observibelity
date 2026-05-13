# syntax=docker/dockerfile:1.7
# nc-chatbot - NeonCart chat-driven shopping assistant.
# Thin layer on top of the shared specialist-base image.

ARG SPECIALIST_BASE=ghcr.io/stephenwagner-grafana/observibelity-specialist-base:0.1.0
FROM ${SPECIALIST_BASE}

LABEL org.opencontainers.image.title="observibelity-nc-chatbot" \
      org.opencontainers.image.description="NeonCart chat-driven shopping assistant" \
      org.opencontainers.image.source="https://github.com/stephenwagner-grafana/observibelity" \
      org.opencontainers.image.licenses="Apache-2.0"

ENV OTEL_SERVICE_NAME=nc-chatbot \
    SPECIALIST_NAME=nc-chatbot

COPY --chown=app:app app/ /app/app/

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
