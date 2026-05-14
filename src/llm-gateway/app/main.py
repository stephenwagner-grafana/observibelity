"""llm-gateway FastAPI app.

Single entrypoint every specialist calls. POST /v1/complete fans out to the
selected provider (default: anthropic), tracks cost, emits a Sigil generation
event, and returns the model's response with usage attached.

OTel spans wrap every call so traces, metrics, and logs share trace_id —
that's how the dashboard joins "this expensive call" to "this slow tool".
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import PlainTextResponse, Response
from opentelemetry import metrics, trace
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.metrics.view import (
    ExplicitBucketHistogramAggregation,
    View,
)
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest

from .pricing import compute_cost, load_pricing_overrides
from .providers import (
    CompleteRequest,
    CompleteResponse,
    Provider,
    discover_providers,
)
from .sigil import (
    emit_generation_event,
    emit_tool_execution_event,
    init_sigil,
    shutdown as sigil_shutdown,
)

log = logging.getLogger("llm_gateway")
logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"))


def _env_bool(name: str, default: bool = True) -> bool:
    """Read a boolean-ish env var (true/1/yes/on are truthy)."""
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _load_json_file(path: str | None) -> dict | None:
    """Load JSON from ``path`` if set + readable; never raise."""
    if not path:
        return None
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except FileNotFoundError:
        log.warning("config file not found: %s", path)
    except Exception as exc:  # noqa: BLE001 — config must never crash boot
        log.warning("failed to read config %s: %s", path, exc)
    return None


# The chart's ConfigMap mounts pricing.json + routing.json at /etc/llm-gateway/.
# Env vars below let the operator override paths; falling back to the mount path
# means an in-cluster gateway picks up the chart-supplied configs automatically.
PRICING_CONFIG_PATH = os.environ.get(
    "PRICING_CONFIG_PATH", "/etc/llm-gateway/pricing.json"
)
ROUTING_CONFIG_PATH = os.environ.get(
    "ROUTING_CONFIG_PATH", "/etc/llm-gateway/routing.json"
)

_routing_cfg = _load_json_file(ROUTING_CONFIG_PATH) or {}
DEFAULT_PROVIDER = (
    os.environ.get("LLM_GATEWAY_DEFAULT_PROVIDER")
    or _routing_cfg.get("default_provider")
    or "anthropic"
)

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
    """Read the small set of env-var knobs Helm injects into per-provider configs.

    The chart sets ``ANTHROPIC_DEFAULT_MODEL`` and ``OLLAMA_BASE_URL``; we honor
    those first and only fall back to the legacy ``ANTHROPIC_MODEL`` /
    ``OLLAMA_MODEL`` names for backwards compat with hand-rolled deployments.
    Routing config (loaded from ``ROUTING_CONFIG_PATH`` if present) can also
    supply per-provider defaults.
    """
    routing_providers = (_routing_cfg.get("providers") or {}) if _routing_cfg else {}
    anthropic_routing = routing_providers.get("anthropic") or {}
    ollama_routing = routing_providers.get("ollama") or {}

    anthropic_model = (
        os.environ.get("ANTHROPIC_DEFAULT_MODEL")
        or os.environ.get("ANTHROPIC_MODEL")
        or anthropic_routing.get("default_model")
        or "claude-haiku-4-5-20251001"
    )
    ollama_model = (
        os.environ.get("OLLAMA_DEFAULT_MODEL")
        or os.environ.get("OLLAMA_MODEL")
        or ollama_routing.get("default_model")
        or "llama3.1:8b"
    )
    ollama_base_url = (
        os.environ.get("OLLAMA_BASE_URL")
        or ollama_routing.get("base_url")
        or None
    )

    return {
        "anthropic": {
            "model": anthropic_model,
            "api_key": os.environ.get("ANTHROPIC_API_KEY"),
            "enabled": _env_bool(
                "ANTHROPIC_ENABLED",
                bool(anthropic_routing.get("enabled", True)),
            ),
        },
        "ollama": {
            "model": ollama_model,
            "base_url": ollama_base_url,
            "enabled": _env_bool(
                "OLLAMA_ENABLED",
                bool(ollama_routing.get("enabled", True)),
            ),
        },
    }


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Discover provider plugins once at startup and stash them on app.state."""
    # Load pricing overrides from the chart-supplied ConfigMap (if mounted).
    # compute_cost() reads PRICES at call time, so the overrides take effect
    # immediately for every subsequent /v1/complete.
    load_pricing_overrides(_load_json_file(PRICING_CONFIG_PATH))

    configs = _build_provider_configs()
    # Drop providers explicitly disabled by env/routing config so they never load.
    enabled_configs = {
        name: cfg for name, cfg in configs.items() if cfg.get("enabled", True)
    }
    providers = discover_providers(enabled_configs)
    app.state.providers = providers
    app.state.default_provider = DEFAULT_PROVIDER

    # Wake up the Sigil exporter so the first /v1/complete doesn't pay the
    # one-time gRPC channel setup. init_sigil() is a no-op when the
    # SIGIL_* env vars aren't present, so this is safe on every deploy.
    try:
        init_sigil("llm-gateway")
    except Exception:  # noqa: BLE001 — telemetry must never block boot
        log.exception("Sigil init failed; generation events disabled")

    log.info(
        "llm-gateway ready: providers=%s default=%s pricing=%s routing=%s",
        list(providers.keys()),
        DEFAULT_PROVIDER,
        PRICING_CONFIG_PATH,
        ROUTING_CONFIG_PATH,
    )
    yield
    # Flush + close the Sigil client on shutdown so in-flight generation
    # events don't get dropped during a rolling restart.
    try:
        sigil_shutdown()
    except Exception:  # noqa: BLE001
        log.exception("Sigil shutdown failed")


app = FastAPI(
    title="observibelity-llm-gateway",
    version="0.2.0",
    description="Centralized LLM routing for observibelity specialists.",
    lifespan=lifespan,
)


# ---- OTel bootstrap --------------------------------------------------------
# The collector + env-vars are wired by Helm but the SDK still has to be
# initialized in-process: without a TracerProvider, `tracer.start_as_current_span`
# returns a no-op span and log records emit `trace_id=""` / `span_id=""`.
def _init_otel(fastapi_app: FastAPI) -> None:
    """Stand up a TracerProvider + OTLP/HTTP exporter and instrument FastAPI + httpx.

    Idempotent + best-effort: any failure (libs missing in tests, collector
    unreachable at boot, etc.) downgrades to a warning rather than crashing
    the gateway — observability must never take the process down.
    """
    service_name = os.environ.get("OTEL_SERVICE_NAME", "llm-gateway")
    namespace = os.environ.get("OBSERVIBELITY_NAMESPACE", "observibelity")
    try:
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
                }
            )
            provider = TracerProvider(resource=resource)
            endpoint = os.environ.get(
                "OTEL_EXPORTER_OTLP_ENDPOINT", "http://otel-collector:4318"
            ).rstrip("/")
            # OTLP/HTTP collector exposes /v1/traces; the SDK constructor wants
            # the fully qualified path, not the bare collector root.
            from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
                OTLPSpanExporter,
            )

            exporter = OTLPSpanExporter(endpoint=f"{endpoint}/v1/traces")
            provider.add_span_processor(BatchSpanProcessor(exporter))
            trace.set_tracer_provider(provider)

        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

        FastAPIInstrumentor.instrument_app(fastapi_app)
        try:
            from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor

            HTTPXClientInstrumentor().instrument()
        except Exception:  # noqa: BLE001 — httpx instrumentation is nice-to-have
            pass
        log.info("OTel SDK initialized for %s", service_name)
    except Exception as exc:  # noqa: BLE001 — never crash on telemetry
        log.warning("OTel init failed (%s) — spans will be no-op", exc)


_init_otel(app)


# ---- OTel metrics bootstrap -----------------------------------------------
# Span attrs alone don't populate Mimir-backed dashboards — we also need to
# push native OTel metrics through the collector. Native gen_ai.* metrics
# (token usage, op duration, cost) are the source of truth for the
# ai-obs-cost panels in Grafana.
def _init_otel_metrics() -> None:
    """Stand up a MeterProvider + OTLP/HTTP metric exporter.

    Best-effort: failures downgrade to a warning so a collector outage at
    boot never takes the gateway down. Idempotent — only installs a new
    provider if the global is still the SDK default no-op.
    """
    service_name = os.environ.get("OTEL_SERVICE_NAME", "llm-gateway")
    namespace = os.environ.get("OBSERVIBELITY_NAMESPACE", "observibelity")
    try:
        if isinstance(metrics.get_meter_provider(), MeterProvider):
            return
        endpoint = os.environ.get(
            "OTEL_EXPORTER_OTLP_ENDPOINT", "http://otel-collector:4318"
        ).rstrip("/")
        from opentelemetry.exporter.otlp.proto.http.metric_exporter import (
            OTLPMetricExporter,
        )

        reader = PeriodicExportingMetricReader(
            OTLPMetricExporter(endpoint=f"{endpoint}/v1/metrics"),
            export_interval_millis=10000,
        )
        # Bucket boundaries tuned for LLM call latency in SECONDS. OTel's
        # default histogram boundaries [0, 5, 10, 25, 50, ..., 10000] assume
        # milliseconds and produce nonsense P95s when applied to seconds
        # (everything lands in the <=5 bucket, P95 reports as the bucket
        # upper bound, and Sigil's Performance dashboard reads 10000s = 2.78h).
        # Anchor at 120s ceiling (matches the 60s wait_for cap + 2x slack).
        _DURATION_BUCKETS = [
            0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5,
            1.0, 2.5, 5.0, 10.0, 30.0, 60.0, 120.0,
        ]
        duration_views = [
            View(
                instrument_name="gen_ai.client.operation.duration",
                aggregation=ExplicitBucketHistogramAggregation(_DURATION_BUCKETS),
            ),
            View(
                instrument_name="gen_ai.client.time_to_first_token",
                aggregation=ExplicitBucketHistogramAggregation(_DURATION_BUCKETS),
            ),
        ]
        provider = MeterProvider(
            metric_readers=[reader],
            views=duration_views,
            resource=Resource.create(
                {
                    "service.name": service_name,
                    "service.namespace": namespace,
                    "service.instance.id": os.environ.get("HOSTNAME", "unknown"),
                    "deployment.environment": os.environ.get(
                        "DEPLOYMENT_ENVIRONMENT", "demo"
                    ),
                    "telemetry.sdk.name": "opentelemetry",
                }
            ),
        )
        metrics.set_meter_provider(provider)
        log.info("OTel metrics SDK initialized for %s", service_name)
    except Exception as exc:  # noqa: BLE001 — never crash on telemetry
        log.warning("OTel metrics init failed (%s) — gen_ai metrics will be no-op", exc)


_init_otel_metrics()

_meter = metrics.get_meter("llm_gateway")

# Native OTel GenAI semantic-convention instruments. Names follow the
# semconv (https://opentelemetry.io/docs/specs/semconv/gen-ai/) so Grafana
# can rely on stable PromQL series like `gen_ai_client_token_usage_total`.
GEN_AI_TOKEN_USAGE = _meter.create_counter(
    name="gen_ai.client.token.usage",
    description="Tokens consumed by GenAI requests.",
    unit="{token}",
)
GEN_AI_OPERATION_DURATION = _meter.create_histogram(
    name="gen_ai.client.operation.duration",
    description="Wall-clock duration of a GenAI client operation.",
    unit="s",
)
GEN_AI_COST_USD = _meter.create_counter(
    name="gen_ai.client.cost.total",
    description="Cumulative cost in USD of GenAI client operations.",
    unit="USD",
)
GEN_AI_TTFT = _meter.create_histogram(
    name="gen_ai.client.time_to_first_token",
    description="Time from request start to first token (approximated as 60% "
                "of total response time for non-streaming upstreams).",
    unit="s",
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
    """The one route specialists call. Routes → costs → emits event → returns.

    Per-request ``provider_override`` lets callers pin a specific provider
    (e.g. the loadgen's 80/20 Ollama vs Claude split). When unset we fall
    back to the gateway's configured default provider.
    """
    provider_name, provider = _select_provider(request, name=req.provider_override)

    with tracer.start_as_current_span("llm_gateway.complete") as span:
        # gen_ai.* span attrs follow OTel GenAI semantic conventions; the
        # canonical session.id / user.id pair lets the AI Observability
        # plugin correlate traces with sigil generation events and Loki
        # logs without per-deployment glue.
        from .sigil import _derive_session_id  # local import: avoid cycle
        _session_id = _derive_session_id(req)
        span.set_attribute("gen_ai.system", provider_name)
        span.set_attribute("gen_ai.operation.name", "chat")
        span.set_attribute(
            "gen_ai.request.model",
            req.model_override or getattr(provider, "model", "unknown"),
        )
        span.set_attribute("session.id", _session_id)
        span.set_attribute("gen_ai.conversation.id", _session_id)
        if persona := req.ai_o11y.get("persona_id"):
            span.set_attribute("user.id", str(persona))
            span.set_attribute("enduser.id", str(persona))
        span.set_attribute("ai_o11y.specialist", req.specialist)
        span.set_attribute("ai_o11y.usecase", req.ai_o11y.get("usecase", ""))
        span.set_attribute("ai_o11y.persona_id", req.ai_o11y.get("persona_id", ""))
        span.set_attribute(
            "traffic_origin", req.ai_o11y.get("traffic_origin", "continuous")
        )

        # Hard-cap per-call latency so a stuck upstream can't smear a 10000s
        # outlier across the latency histogram (which is what was making the
        # Sigil Performance panel's P95 read as 2.78 hours). 60s is more than
        # any healthy gen completion needs; Anthropic SDK's own default is
        # 600s, Ollama's is 120s — this is the tightest of the three.
        _PROVIDER_TIMEOUT_S = float(os.environ.get("LLM_GATEWAY_PROVIDER_TIMEOUT_S", "60"))
        start_time = time.monotonic()
        with REQ_LATENCY.labels(
            provider=provider_name,
            model=req.model_override or getattr(provider, "model", "unknown"),
            specialist=req.specialist,
        ).time():
            try:
                resp = await asyncio.wait_for(
                    provider.complete(req), timeout=_PROVIDER_TIMEOUT_S
                )
            except asyncio.TimeoutError as exc:
                span.record_exception(exc)
                span.set_attribute("error", True)
                span.set_attribute("error.kind", "provider_timeout")
                log.warning(
                    "provider %s timed out after %.1fs", provider_name, _PROVIDER_TIMEOUT_S
                )
                raise HTTPException(
                    status_code=504,
                    detail=f"{provider_name}: timed out after {_PROVIDER_TIMEOUT_S:.0f}s",
                )
            except Exception as exc:  # noqa: BLE001 — translate to HTTP 502 for caller.
                span.record_exception(exc)
                span.set_attribute("error", True)
                log.exception("provider %s failed", provider_name)
                raise HTTPException(status_code=502, detail=f"{provider_name}: {exc}")
        duration_seconds = time.monotonic() - start_time

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

        # Native OTel GenAI metrics — flow through the collector into Mimir
        # so the ai-obs-cost dashboards AND the Sigil plugin can query
        # gen_ai_client_* series with a consistent label set. Canonical OTel
        # GenAI keys (gen_ai.*, service.namespace) come first; ai_o11y.*
        # mirrors stay so the existing custom dashboards keep working.
        from .sigil import _derive_session_id  # local import: avoid cycle

        # Default agent.name to "llm-gateway" when the caller didn't pass a
        # specialist (direct curl, eval-judge replay, etc.) so the OTel meter
        # never emits an empty/"unknown" label — Sigil's Performance dashboard
        # buckets unattributed traffic into "unknown" otherwise.
        agent_name = (req.specialist or "").strip() or "llm-gateway"
        gen_ai_attrs: dict[str, str | int | float] = {
            "gen_ai.system": provider_name,
            "gen_ai.operation.name": "chat",
            "gen_ai.agent.name": agent_name,
            "gen_ai.request.model": resp.model,
            "gen_ai.response.model": resp.model,
            "service.name": "llm-gateway",
            "service.namespace": os.environ.get(
                "OBSERVIBELITY_NAMESPACE", "observibelity"
            ),
            "deployment.environment": os.environ.get(
                "DEPLOYMENT_ENVIRONMENT", "demo"
            ),
            "session.id": _derive_session_id(req),
            "user.id": req.ai_o11y.get("persona_id", "") or "",
            "ai_o11y.usecase": req.ai_o11y.get("usecase", "") or "",
            "ai_o11y.specialist": agent_name,
            "ai_o11y.persona_id": req.ai_o11y.get("persona_id", "") or "",
        }
        try:
            input_tokens = int(resp.usage.get("input_tokens", 0) or 0)
            output_tokens = int(resp.usage.get("output_tokens", 0) or 0)
            GEN_AI_TOKEN_USAGE.add(
                input_tokens, {**gen_ai_attrs, "gen_ai.token.type": "input"}
            )
            GEN_AI_TOKEN_USAGE.add(
                output_tokens, {**gen_ai_attrs, "gen_ai.token.type": "output"}
            )
            GEN_AI_OPERATION_DURATION.record(duration_seconds, gen_ai_attrs)
            # TTFT approximated as 60% of total response duration since our
            # upstreams are non-streaming. Mirrors the same heuristic the
            # Sigil exporter uses (see sigil.py:_approx_ttft_s). The Sigil
            # Performance dashboard's TTFT P95 panel reads this histogram.
            GEN_AI_TTFT.record(max(duration_seconds * 0.6, 0.001), gen_ai_attrs)
            GEN_AI_COST_USD.add(
                float(cost["input_usd"]),
                {**gen_ai_attrs, "gen_ai.cost.type": "input"},
            )
            GEN_AI_COST_USD.add(
                float(cost["output_usd"]),
                {**gen_ai_attrs, "gen_ai.cost.type": "output"},
            )
        except Exception:  # noqa: BLE001 — telemetry must never break the request.
            log.exception("failed to record gen_ai OTel metrics")

        # Sigil generation event (fire-and-forget; never blocks the response).
        # Pass duration_ms so the Sigil exporter can populate the TTFT
        # histogram even though we're not streaming upstream yet.
        ctx = span.get_span_context()
        span_id_hex = format(ctx.span_id, "016x") if ctx.span_id else ""
        trace_id_hex = format(ctx.trace_id, "032x") if ctx.trace_id else ""
        try:
            await emit_generation_event(
                req,
                resp,
                span_id=span_id_hex,
                trace_id=trace_id_hex,
                duration_ms=duration_seconds * 1000.0,
            )
        except Exception:  # noqa: BLE001
            log.exception("Sigil generation emit failed")

        # Tool-execution events — one per tool_use block. Lets the AI plugin's
        # Tools tab segment by name + show arguments without us having to
        # instrument every individual specialist. Specialists can still emit
        # their own richer tool spans later; the gateway-side emit is the
        # always-on baseline that keeps the panel populated.
        if resp.tool_calls:
            # conversation_id == session_id so the Tools panel groups tool
            # invocations with their parent chat in the Conversations view.
            for tc in resp.tool_calls:
                try:
                    await emit_tool_execution_event(
                        specialist=req.specialist,
                        tool_name=tc.get("name", "unknown"),
                        tool_call_id=tc.get("id", ""),
                        arguments=tc.get("input") or tc.get("arguments") or {},
                        request_model=resp.model,
                        provider=provider_name,
                        conversation_id=_session_id,
                        session_id=_session_id,
                        usecase=req.ai_o11y.get("usecase", ""),
                        persona_id=req.ai_o11y.get("persona_id", ""),
                        trace_id=trace_id_hex,
                        span_id=span_id_hex,
                    )
                except Exception:  # noqa: BLE001
                    log.exception("Sigil tool emit failed: tool=%s", tc.get("name"))

        return resp
