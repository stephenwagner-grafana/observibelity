"""FastAPI mount for an ObserVIBElity Tool.

Each tool's ``app/main.py`` does::

    from tool_base.main import build_app
    from .tool import SearchProducts
    app = build_app(SearchProducts())

This module exposes the standard tool HTTP surface:

* ``POST /v1/invoke``   — execute the tool (body = Args schema)
* ``GET  /v1/schema``  — Args + Result JSON Schemas
* ``GET  /health``     — liveness
* ``GET  /readyz``     — readiness
* ``GET  /metrics``    — Prometheus metrics
"""
from __future__ import annotations

import logging
import os

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse, Response
from opentelemetry import trace
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest

from .tool import Tool

log = logging.getLogger("tool_base")


def _init_otel(default_service_name: str) -> None:
    """Stand up a TracerProvider + OTLP/HTTP exporter for the tool pod.

    Idempotent: if another caller already installed a real TracerProvider
    (e.g. opentelemetry-instrument), we leave it alone. Best-effort: telemetry
    failures must never knock a tool offline.
    """
    service_name = os.environ.get("OTEL_SERVICE_NAME", default_service_name)
    namespace = os.environ.get("OBSERVIBELITY_NAMESPACE", "observibelity")
    try:
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor

        if not isinstance(trace.get_tracer_provider(), TracerProvider):
            resource = Resource.create(
                {
                    "service.name": service_name,
                    "service.namespace": namespace,
                    "service.instance.id": os.environ.get("HOSTNAME", "unknown"),
                    "deployment.environment": os.environ.get(
                        "DEPLOYMENT_ENVIRONMENT", "demo"
                    ),
                    "telemetry.sdk.name": "opentelemetry",
                    "observibelity.role": "tool",
                }
            )
            provider = TracerProvider(resource=resource)
            endpoint = os.environ.get(
                "OTEL_EXPORTER_OTLP_ENDPOINT", "http://otel-collector:4318"
            ).rstrip("/")
            from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
                OTLPSpanExporter,
            )

            exporter = OTLPSpanExporter(endpoint=f"{endpoint}/v1/traces")
            provider.add_span_processor(BatchSpanProcessor(exporter))
            trace.set_tracer_provider(provider)
        try:
            from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor

            HTTPXClientInstrumentor().instrument()
        except Exception:  # noqa: BLE001
            pass
        log.info("OTel SDK initialized for tool %s", service_name)
    except Exception as exc:  # noqa: BLE001 — never crash on telemetry
        log.warning("OTel init failed for tool %s (%s)", service_name, exc)

INVOCATIONS = Counter(
    "tool_invocations_total",
    "Total tool invocations.",
    ["tool", "status"],
)
LATENCY = Histogram(
    "tool_invocation_duration_seconds",
    "Tool invocation latency in seconds.",
    ["tool"],
)


def build_app(tool: Tool) -> FastAPI:
    """Return a FastAPI app wrapping ``tool``."""
    app = FastAPI(
        title=f"observibelity-tool-{tool.NAME}",
        version="0.2.0",
        description=f"ObserVIBElity tool microservice: {tool.NAME}",
    )
    # Wire up the SDK *before* FastAPIInstrumentor.instrument_app at the
    # bottom of this function — the instrumentor only attaches handlers,
    # it doesn't install a TracerProvider, so spans are no-op without this.
    _init_otel(default_service_name=tool.NAME)

    @app.post("/v1/invoke")
    async def invoke(
        request: Request,
        x_caller: str | None = Header(default=None, alias="X-Caller"),
        x_persona_id: str | None = Header(default=None, alias="X-Persona-Id"),
    ) -> JSONResponse:
        try:
            body = await request.json()
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"invalid JSON: {exc}") from exc
        try:
            args = tool.Args.model_validate(body)
        except Exception as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        # Attach caller + persona to the current HTTP server span so Tempo
        # filters work even when the tool short-circuits (e.g. on a 403).
        current_span = trace.get_current_span()
        if current_span is not None:
            if x_caller:
                current_span.set_attribute("ai_o11y.tool.caller", x_caller)
            if x_persona_id:
                current_span.set_attribute("ai_o11y.persona_id", x_persona_id)
        with LATENCY.labels(tool=tool.NAME).time():
            try:
                result = await tool.invoke(args, caller=x_caller)
            except PermissionError as exc:
                INVOCATIONS.labels(tool=tool.NAME, status="denied").inc()
                raise HTTPException(status_code=403, detail=str(exc)) from exc
            except TimeoutError as exc:
                INVOCATIONS.labels(tool=tool.NAME, status="timeout").inc()
                raise HTTPException(status_code=504, detail="tool timed out") from exc
            except Exception as exc:
                INVOCATIONS.labels(tool=tool.NAME, status="error").inc()
                raise HTTPException(status_code=500, detail=str(exc)) from exc
        INVOCATIONS.labels(tool=tool.NAME, status="ok").inc()
        return JSONResponse(content=result.model_dump(mode="json"))

    @app.get("/v1/schema")
    async def schema() -> dict[str, object]:
        return {
            "tool": tool.NAME,
            "args": tool.Args.model_json_schema(),
            "result": tool.Result.model_json_schema(),
            "knobs": {
                "side_effect": tool.SIDE_EFFECT,
                "idempotent": tool.IDEMPOTENT,
                "timeout_sec": tool.TIMEOUT_SEC,
                "max_concurrency": tool.MAX_CONCURRENCY,
                "cache_ttl_sec": tool.CACHE_TTL_SEC,
                "retries": tool.RETRIES,
                "allowed_callers": tool.ALLOWED_CALLERS,
                "requires_acl": tool.REQUIRES_ACL,
                "backing_tables": tool.BACKING_TABLES,
                "requires_secrets": tool.REQUIRES_SECRETS,
                "replicas": tool.REPLICAS,
            },
        }

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok", "tool": tool.NAME}

    @app.get("/readyz")
    async def readyz() -> dict[str, str]:
        # If we have a DB engine, a cheap connectivity check would go here.
        # Helm pre-install jobs guarantee DB readiness, so we return ok.
        return {"status": "ready", "tool": tool.NAME}

    @app.get("/metrics")
    async def metrics() -> Response:
        return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

    FastAPIInstrumentor.instrument_app(app)
    return app
