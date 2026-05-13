"""llm-gateway FastAPI app.

Single entrypoint every specialist calls. POST /v1/complete fans out to the
selected provider (default: anthropic), tracks cost, emits a Sigil generation
event, and returns the model's response with usage attached.

OTel spans wrap every call so traces, metrics, and logs share trace_id —
that's how the dashboard joins "this expensive call" to "this slow tool".
"""
from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import PlainTextResponse, Response
from opentelemetry import trace
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest

from .pricing import compute_cost
from .providers import (
    CompleteRequest,
    CompleteResponse,
    Provider,
    discover_providers,
)
from .sigil import emit_generation_event

log = logging.getLogger("llm_gateway")
logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"))

DEFAULT_PROVIDER = os.environ.get("LLM_GATEWAY_DEFAULT_PROVIDER", "anthropic")

# Prometheus metrics — exposed at /metrics, scraped by the otel-collector.
REQ_COUNT = Counter(
    "llm_gateway_requests_total",
    "Total completion requests handled.",
    ["provider", "model", "specialist", "usecase", "finish_reason"],
)
REQ_LATENCY = Histogram(
    "llm_gateway_request_duration_seconds",
    "Wall-clock latency of /v1/complete.",
    ["provider", "model", "specialist"],
)
COST_TOTAL = Counter(
    "llm_gateway_cost_usd_total",
    "Cumulative spend in USD across all calls.",
    ["provider", "model", "specialist", "usecase"],
)


def _build_provider_configs() -> dict[str, dict]:
    """Read the small set of env-var knobs Helm injects into per-provider configs."""
    return {
        "anthropic": {
            "model": os.environ.get("ANTHROPIC_MODEL", "claude-haiku-4-5-20251001"),
            "api_key": os.environ.get("ANTHROPIC_API_KEY"),
        },
        "ollama": {
            "model": os.environ.get("OLLAMA_MODEL", "llama3.1:8b"),
            "base_url": os.environ.get("OLLAMA_BASE_URL"),
        },
    }


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Discover provider plugins once at startup and stash them on app.state."""
    providers = discover_providers(_build_provider_configs())
    app.state.providers = providers
    app.state.default_provider = DEFAULT_PROVIDER
    log.info(
        "llm-gateway ready: providers=%s default=%s",
        list(providers.keys()),
        DEFAULT_PROVIDER,
    )
    yield
    # Nothing to tear down — httpx + anthropic SDK use short-lived async clients.


app = FastAPI(
    title="observibelity-llm-gateway",
    version="0.2.0",
    description="Centralized LLM routing for observibelity specialists.",
    lifespan=lifespan,
)

tracer = trace.get_tracer("llm_gateway")


def _select_provider(request: Request, name: str | None) -> tuple[str, Provider]:
    """Pick a provider by name (or fall back to default) and return (name, instance)."""
    providers: dict[str, Provider] = request.app.state.providers
    target = name or request.app.state.default_provider
    provider = providers.get(target)
    if provider is None:
        # Fall back to anything healthy rather than 503-ing the specialist.
        if providers:
            target, provider = next(iter(providers.items()))
        else:
            raise HTTPException(status_code=503, detail="No LLM providers loaded.")
    return target, provider


@app.get("/health", response_class=PlainTextResponse)
async def health() -> str:
    """Liveness — always 200 as long as the process is up."""
    return "ok"


@app.get("/readyz")
async def readyz(request: Request) -> dict:
    """Readiness — at least one provider answers .healthy() truthfully."""
    providers: dict[str, Provider] = request.app.state.providers
    statuses: dict[str, bool] = {}
    for name, p in providers.items():
        try:
            statuses[name] = bool(await p.healthy())
        except Exception:  # noqa: BLE001
            statuses[name] = False
    if not any(statuses.values()):
        raise HTTPException(status_code=503, detail={"providers": statuses})
    return {"providers": statuses}


@app.get("/metrics")
async def metrics() -> Response:
    """Prometheus scrape endpoint."""
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.post("/v1/complete", response_model=CompleteResponse)
async def complete(req: CompleteRequest, request: Request) -> CompleteResponse:
    """The one route specialists call. Routes → costs → emits event → returns."""
    provider_name, provider = _select_provider(request, name=None)

    with tracer.start_as_current_span("llm_gateway.complete") as span:
        # gen_ai.* span attrs follow OTel GenAI semantic conventions.
        span.set_attribute("gen_ai.system", provider_name)
        span.set_attribute(
            "gen_ai.request.model",
            req.model_override or getattr(provider, "model", "unknown"),
        )
        span.set_attribute("ai_o11y.specialist", req.specialist)
        span.set_attribute("ai_o11y.usecase", req.ai_o11y.get("usecase", ""))
        span.set_attribute("ai_o11y.persona_id", req.ai_o11y.get("persona_id", ""))
        span.set_attribute(
            "traffic_origin", req.ai_o11y.get("traffic_origin", "continuous")
        )

        with REQ_LATENCY.labels(
            provider=provider_name,
            model=req.model_override or getattr(provider, "model", "unknown"),
            specialist=req.specialist,
        ).time():
            try:
                resp = await provider.complete(req)
            except Exception as exc:  # noqa: BLE001 — translate to HTTP 502 for caller.
                span.record_exception(exc)
                span.set_attribute("error", True)
                log.exception("provider %s failed", provider_name)
                raise HTTPException(status_code=502, detail=f"{provider_name}: {exc}")

        # Compute cost and stitch it back onto the response payload.
        cost = compute_cost(
            resp.model,
            resp.usage.get("input_tokens", 0),
            resp.usage.get("output_tokens", 0),
        )
        resp.usage["cost_usd"] = cost

        # Span attrs for the response side.
        span.set_attribute("gen_ai.response.model", resp.model)
        span.set_attribute("gen_ai.usage.input_tokens", resp.usage.get("input_tokens", 0))
        span.set_attribute("gen_ai.usage.output_tokens", resp.usage.get("output_tokens", 0))
        span.set_attribute("gen_ai.usage.cost.input_usd", cost["input_usd"])
        span.set_attribute("gen_ai.usage.cost.output_usd", cost["output_usd"])
        span.set_attribute("gen_ai.usage.cost.total_usd", cost["total_usd"])
        span.set_attribute("gen_ai.response.finish_reasons", [resp.finish_reason])

        # Prometheus counters.
        labels_full = dict(
            provider=provider_name,
            model=resp.model,
            specialist=req.specialist,
            usecase=req.ai_o11y.get("usecase", "unknown"),
        )
        REQ_COUNT.labels(**labels_full, finish_reason=resp.finish_reason).inc()
        COST_TOTAL.labels(**labels_full).inc(cost["total_usd"])

        # Sigil generation event (fire-and-forget; never blocks the response).
        ctx = span.get_span_context()
        await emit_generation_event(
            req,
            resp,
            span_id=format(ctx.span_id, "016x") if ctx.span_id else "",
            trace_id=format(ctx.trace_id, "032x") if ctx.trace_id else "",
        )

        return resp
