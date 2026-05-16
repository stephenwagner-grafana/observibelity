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
from .prewarm import maybe_start_prewarm

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

# Phase A: gateway-internal streaming, scoped to nc-chatbot only so the
# blast radius of any streaming-side regression (token-usage extraction,
# SDK quirks, etc.) is one specialist instead of the whole fleet.
# Default ON; flip to "false" to revert to non-streaming without rebuilding.
STREAM_NC_CHATBOT = _env_bool("STREAM_NC_CHATBOT", True)
# The exact specialist name eligible for streaming. Hardcoded list — not a
# regex / env-var set — to keep "what's in the streaming path" trivially
# auditable from the code.
_STREAMING_SPECIALISTS = frozenset({"nc-chatbot"})

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
# Spillover + Claude budget instrumentation lives on the OTel meter (see
# below, ~line 391) — prometheus_client metrics never reach Grafana Cloud
# because nothing scrapes /metrics; the OTel-via-OTLP pipeline is the
# canonical path. Definitions are wired up after `_meter` is initialized.


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
    # Make the provider dict visible to the OTel observable-gauge callbacks
    # (which run on a background thread + can't reach FastAPI request state).
    _provider_state.clear()
    _provider_state.update(providers)

    # Wake up the Sigil exporter so the first /v1/complete doesn't pay the
    # one-time gRPC channel setup. init_sigil() is a no-op when the
    # SIGIL_* env vars aren't present, so this is safe on every deploy.
    try:
        init_sigil("llm-gateway")
    except Exception:  # noqa: BLE001 — telemetry must never block boot
        log.exception("Sigil init failed; generation events disabled")

    # Start the Ollama prewarm task — preloads the next-rotation model into
    # VRAM during the current model's 5-min window so the flip is seamless
    # (zero cold-load latency at the boundary). Requires the daemon to allow
    # at least 2 loaded models (OLLAMA_MAX_LOADED_MODELS=2) on .240.
    try:
        app.state.prewarm_task = maybe_start_prewarm()
    except Exception:  # noqa: BLE001 — prewarm must never block boot
        log.exception("prewarm init failed; rotation flips will see cold loads")
        app.state.prewarm_task = None

    log.info(
        "llm-gateway ready: providers=%s default=%s pricing=%s routing=%s claude_budget=$%.2f/day",
        list(providers.keys()),
        DEFAULT_PROVIDER,
        PRICING_CONFIG_PATH,
        ROUTING_CONFIG_PATH,
        _CLAUDE_DAILY_BUDGET_USD,
    )
    yield
    # Flush + close the Sigil client on shutdown so in-flight generation
    # events don't get dropped during a rolling restart.
    try:
        sigil_shutdown()
    except Exception:  # noqa: BLE001
        log.exception("Sigil shutdown failed")
    # Stop the prewarm ticker before the event loop tears down.
    prewarm_task = getattr(app.state, "prewarm_task", None)
    if prewarm_task is not None:
        try:
            await prewarm_task.stop()
        except Exception:  # noqa: BLE001
            log.exception("prewarm shutdown failed")


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
    description="Time from request start to first token. Real wall-clock "
                "measurement on streaming specialists (Phase A: nc-chatbot); "
                "60% of total response time heuristic on non-streaming ones.",
    unit="s",
)

# Spillover + Claude-budget metrics — OTel-native so they flow through the
# collector → Grafana Cloud Prometheus alongside gen_ai.*. Names use dots
# here; the Prometheus serializer converts them to underscores, so the
# dashboard's `llm_gateway_spillover_total` etc. PromQL keeps working.
SPILLOVER_TOTAL = _meter.create_counter(
    name="llm_gateway.spillover.total",
    description="Times the dispatcher swapped a target=ollama request to "
                "anthropic because Ollama was at the saturation threshold.",
)


# Module-level holder for the Ollama provider dict; populated by the
# lifespan handler at startup. The observable-gauge callbacks below read
# from it instead of the FastAPI request-scoped state.
_provider_state: dict[str, Provider] = {}


def _observe_ollama_in_flight(options):  # type: ignore[no-untyped-def]
    """Callback: report the live Ollama in-flight count for the OTel gauge."""
    from opentelemetry.metrics import Observation
    ollama_provider = _provider_state.get("ollama")
    value = 0
    if ollama_provider is not None:
        value = int(getattr(ollama_provider, "in_flight", 0) or 0)
    return [Observation(value, {})]


def _observe_claude_daily_spend(options):  # type: ignore[no-untyped-def]
    """Callback: report today's cumulative Claude spend in USD."""
    from opentelemetry.metrics import Observation
    _maybe_reset_budget_day()
    return [Observation(float(_claude_daily_spent_usd), {})]


def _observe_claude_daily_budget(options):  # type: ignore[no-untyped-def]
    """Callback: report the configured daily Claude budget ceiling."""
    from opentelemetry.metrics import Observation
    return [Observation(float(_CLAUDE_DAILY_BUDGET_USD), {})]


_meter.create_observable_gauge(
    name="llm_gateway.ollama.in_flight",
    description="Live count of Ollama requests currently being served on this gateway pod.",
    callbacks=[_observe_ollama_in_flight],
)
_meter.create_observable_gauge(
    name="llm_gateway.claude.daily.spend.usd",
    description="Cumulative Anthropic spend (USD) for the current UTC day; resets at midnight.",
    callbacks=[_observe_claude_daily_spend],
)
_meter.create_observable_gauge(
    name="llm_gateway.claude.daily.budget.usd",
    description="Configured daily Anthropic budget ceiling (USD).",
    callbacks=[_observe_claude_daily_budget],
)


tracer = trace.get_tracer("llm_gateway")


# Daily Claude budget — enforced as a hard ceiling on actual USD spent. No
# ratios, no rate caps, no random pickers: just a running tally of real cost
# emitted by the Anthropic provider. Spillover is permitted only while
# today's tally is below CLAUDE_DAILY_BUDGET_USD; once the budget is
# exhausted, requests that would have spilled stay on Ollama and accept
# whatever queue latency follows.
_CLAUDE_DAILY_BUDGET_USD = float(os.environ.get("CLAUDE_DAILY_BUDGET_USD", "20.0"))
_claude_daily_spent_usd: float = 0.0
_claude_budget_day_utc: str = ""


def _maybe_reset_budget_day() -> None:
    """Roll the daily ledger over at UTC midnight."""
    global _claude_daily_spent_usd, _claude_budget_day_utc
    from datetime import datetime, timezone  # local import: keep boot light
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if today != _claude_budget_day_utc:
        _claude_daily_spent_usd = 0.0
        _claude_budget_day_utc = today


def _claude_spillover_allowed() -> bool:
    """True iff today's cumulative Claude spend hasn't hit the budget ceiling."""
    _maybe_reset_budget_day()
    return _claude_daily_spent_usd < _CLAUDE_DAILY_BUDGET_USD


def _record_claude_spend(usd: float) -> None:
    """Add a completed Claude call's USD cost to today's tally."""
    global _claude_daily_spent_usd
    _maybe_reset_budget_day()
    _claude_daily_spent_usd += max(0.0, usd)


def claude_budget_state() -> dict[str, float | str]:
    """Snapshot of the running budget — exposed via /metrics for the dashboard."""
    _maybe_reset_budget_day()
    return {
        "budget_usd": _CLAUDE_DAILY_BUDGET_USD,
        "spent_usd": _claude_daily_spent_usd,
        "remaining_usd": max(0.0, _CLAUDE_DAILY_BUDGET_USD - _claude_daily_spent_usd),
        "day_utc": _claude_budget_day_utc,
    }


def _select_provider(
    request: Request, name: str | None
) -> tuple[str, Provider, bool]:
    """Pick a provider — with saturation-based spillover to Claude.

    Returns ``(provider_name, provider, spilled_over)``. When the chosen
    target is Ollama and the OllamaProvider reports ``is_saturated``, the
    dispatcher swaps to Anthropic IF the rolling per-minute Claude budget
    has room (see :data:`_CLAUDE_SPILLOVER_RPM`). Otherwise the request
    stays on Ollama and accepts whatever queue latency follows.

    ``spilled_over`` flags the swap so the /v1/complete span can annotate it
    for dashboards that want to correlate spillover with Ollama latency.
    """
    providers: dict[str, Provider] = request.app.state.providers
    target = name or request.app.state.default_provider
    provider = providers.get(target)
    if provider is None:
        # Fall back to anything healthy rather than 503-ing the specialist.
        if providers:
            target, provider = next(iter(providers.items()))
        else:
            raise HTTPException(status_code=503, detail="No LLM providers loaded.")

    # Spillover: Ollama is at capacity and there's room in the daily budget.
    spilled = False
    if target == "ollama" and "anthropic" in providers:
        ollama_provider = providers.get("ollama")
        if (
            ollama_provider is not None
            and getattr(ollama_provider, "is_saturated", False)
            and _claude_spillover_allowed()
        ):
            target = "anthropic"
            provider = providers["anthropic"]
            spilled = True
            SPILLOVER_TOTAL.add(1, {"reason": "ollama_saturated"})
    return target, provider, spilled


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
    provider_name, provider, _spilled_over = _select_provider(
        request, name=req.provider_override
    )

    with tracer.start_as_current_span("llm_gateway.complete") as span:
        # gen_ai.* span attrs follow OTel GenAI semantic conventions; the
        # canonical session.id / user.id pair lets the AI Observability
        # plugin correlate traces with sigil generation events and Loki
        # logs without per-deployment glue.
        from .sigil import _derive_session_id  # local import: avoid cycle
        _session_id = _derive_session_id(req)
        span.set_attribute("gen_ai.system", provider_name)
        if _spilled_over:
            # Marks requests that landed on Anthropic only because Ollama
            # was at capacity — the dashboard correlates this with the
            # OLLAMA_SATURATION_THRESHOLD + Claude budget exhaustion.
            span.set_attribute("llm_gateway.spillover", "ollama_saturated")
        span.set_attribute("gen_ai.operation.name", "chat")
        span.set_attribute(
            "gen_ai.request.model",
            req.model_override or getattr(provider, "model", "unknown"),
        )
        span.set_attribute("session.id", _session_id)
        span.set_attribute("gen_ai.conversation.id", _session_id)
        if persona := req.ai_o11y.get("persona_id"):
            from .persona_email import persona_to_email  # local import: avoid cycle
            _persona_email = persona_to_email(str(persona), req.specialist or "")
            span.set_attribute("user.id", _persona_email)
            span.set_attribute("enduser.id", _persona_email)
            span.set_attribute("ai_o11y.persona_email", _persona_email)
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
        # Phase A streaming: scoped to nc-chatbot. Every other specialist
        # keeps the existing non-streaming path. ttft_ms is None on the
        # non-streaming path and filled in by complete_stream() when it
        # observes a real first text chunk.
        use_streaming = (
            STREAM_NC_CHATBOT and req.specialist in _STREAMING_SPECIALISTS
        )
        ttft_ms: float | None = None
        streaming_used = False
        start_time = time.monotonic()
        with REQ_LATENCY.labels(
            provider=provider_name,
            model=req.model_override or getattr(provider, "model", "unknown"),
            specialist=req.specialist,
        ).time():
            try:
                if use_streaming:
                    try:
                        resp, ttft_ms = await asyncio.wait_for(
                            provider.complete_stream(req),
                            timeout=_PROVIDER_TIMEOUT_S,
                        )
                        streaming_used = True
                    except asyncio.TimeoutError:
                        raise
                    except Exception as exc:  # noqa: BLE001
                        # Fail-safe: if streaming blows up mid-flight, fall
                        # back to the non-streaming path for this request so
                        # the specialist still gets an answer. Logged with
                        # full traceback so regressions are visible.
                        log.warning(
                            "streaming failed for specialist=%s provider=%s; "
                            "falling back to non-streaming: %s",
                            req.specialist, provider_name, exc,
                        )
                        span.set_attribute("llm_gateway.streaming.fallback", True)
                        resp = await asyncio.wait_for(
                            provider.complete(req), timeout=_PROVIDER_TIMEOUT_S
                        )
                else:
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
        span.set_attribute("llm_gateway.streaming.used", streaming_used)
        if streaming_used and ttft_ms is not None:
            span.set_attribute("gen_ai.server.time_to_first_token", ttft_ms / 1000.0)

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

        # Add the just-completed call's USD to the daily Claude ledger so
        # the spillover decision in _select_provider can deny further
        # spillover once we hit the day's budget ceiling. The OTel
        # observable-gauge callbacks (see _observe_claude_daily_spend /
        # _observe_ollama_in_flight) read this state on each collection
        # cycle, so no explicit .set() is needed here.
        if provider_name == "anthropic":
            _record_claude_spend(float(cost["total_usd"]))

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
        from .persona_email import persona_to_email  # email-stamp user.id

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
            "user.id": persona_to_email(
                req.ai_o11y.get("persona_id", "") or "", agent_name
            ),
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
            # TTFT: when streaming actually delivered a first chunk
            # (nc-chatbot under Phase A), record the real wall-clock value.
            # Otherwise keep the 60%-of-duration heuristic so panels that
            # average across all specialists don't go empty on the
            # non-streaming majority.
            if streaming_used and ttft_ms is not None:
                ttft_seconds = max(ttft_ms / 1000.0, 0.001)
            else:
                ttft_seconds = max(duration_seconds * 0.6, 0.001)
            GEN_AI_TTFT.record(ttft_seconds, gen_ai_attrs)
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
        # histogram. Real ttft_ms is passed alongside when streaming
        # produced one — sigil.py prefers it over the 60% heuristic.
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
                ttft_ms=ttft_ms if streaming_used else None,
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
