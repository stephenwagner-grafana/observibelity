"""FastAPI route mounting helper for specialist pods.

Each specialist's ``app/main.py`` just calls ``build_app(MySpecialist())`` and
exports the resulting FastAPI app. Routes mounted:
  * POST /v1/run   — main entry (delegates to ``specialist.handle``)
  * GET  /health   — liveness
  * GET  /readyz   — readiness
  * GET  /metrics  — Prometheus scrape endpoint
"""
from __future__ import annotations

import importlib
import os

from fastapi import FastAPI, HTTPException
from fastapi.responses import Response
from opentelemetry import trace
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from .specialist import Specialist, SpecialistRequest, SpecialistResponse


def build_app(specialist: Specialist) -> FastAPI:
    """Wrap a Specialist instance in a FastAPI app with the standard routes."""
    app = FastAPI(
        title=f"observibelity-specialist-{specialist.NAME}",
        version=os.environ.get("SPECIALIST_VERSION", "0.2.0"),
    )

    @app.post("/v1/run", response_model=SpecialistResponse)
    async def run(req: SpecialistRequest) -> SpecialistResponse:
        # Stamp the run-level span with persona + usecase so every child
        # span (call_gateway, call_tool, asyncpg, etc.) inherits the
        # attributes through OTel's resource-detector cascade.
        span = trace.get_current_span()
        if span and span.is_recording():
            span.set_attribute("ai_o11y.specialist", specialist.NAME)
            if req.persona_id:
                span.set_attribute("ai_o11y.persona_id", req.persona_id)
            if req.usecase:
                span.set_attribute("ai_o11y.usecase", req.usecase)
        try:
            resp = await specialist.handle(req)
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        # Attach the current span id so callers can correlate downstream
        if resp.span_id is None:
            ctx = span.get_span_context() if span else None
            if ctx and ctx.is_valid:
                resp.span_id = format(ctx.span_id, "016x")
        return resp

    @app.get("/health")
    async def health() -> dict:
        return {"status": "ok", "specialist": specialist.NAME}

    @app.get("/readyz")
    async def readyz() -> dict:
        return {"ready": True, "specialist": specialist.NAME}

    @app.get("/metrics")
    async def metrics() -> Response:
        """Prometheus scrape endpoint — matches the tool_base / app pattern."""
        return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)

    return app


def build_app_from_env() -> FastAPI:
    """Resolve a specialist class from the SPECIALIST_NAME env var and build its app.

    SPECIALIST_NAME determines the import path:
        nc-chatbot -> app.specialist.NcChatbot
    """
    name = os.environ.get("SPECIALIST_NAME")
    if not name:
        raise RuntimeError("SPECIALIST_NAME env var is required")
    # nc-chatbot -> NcChatbot
    class_name = "".join(part.capitalize() for part in name.split("-"))
    module = importlib.import_module("app.specialist")
    cls = getattr(module, class_name)
    return build_app(cls())
