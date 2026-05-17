"""llm-gateway FastAPI app.

Single entrypoint every specialist calls. POST /v1/complete fans out to the
selected provider (default: anthropic), tracks cost, emits a Sigil generation
event, and returns the model's response with usage attached.

OTel spans wrap every call so traces, metrics, and logs share trace_id —
that's how the dashboard joins "this expensive call" to "this slow tool".

Routing model (tiered-sampler redesign):

* **Default lane** — loadgen + non-interactive callers. Each request rolls
  a die: ``P(target=anthropic) == claude_sample_rate(default_spend_today)``.
  The sample rate is 10% under $40 of spend and decays by 10x for every
  additional $20 of spend. The dice IS the admission — there is no
  fallback between providers. If the dice says Ollama and Ollama is full,
  the caller gets a 429. A $200 sanity sentinel hard-stops Claude.
* **Interactive lane** — ``ai_o11y.traffic_origin == "interactive"`` OR the
  ``X-Traffic-Origin: interactive`` header. Bypasses admission entirely and
  always routes to Claude. Spend tracked separately + uncapped.

Admission tests live in ``app.admission`` as pure functions; this module
wires the dispatcher to them.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import random
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import AsyncIterator

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, PlainTextResponse, Response
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

from .admission import (
    CLAUDE_SANITY_SENTINEL_USD,
    REASON_CLAUDE_NOT_SAMPLED,
    REASON_OLLAMA_POOL_EMPTY,
    REASON_OLLAMA_SATURATED,
    claude_admit_default,
    claude_sample_rate,
    claude_sample_tier,
    ollama_admit,
)
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
from .scheduler import maybe_start_scheduler

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

    # Start the Ollama model-pool scheduler — replaces the old fixed-window
    # rotation with a state machine (LOADING -> ACTIVE -> DRAINING). Pool
    # targets pool_min ACTIVE models, caps at pool_max, drains a model
    # after requests_per_lifecycle completions. tick() runs every 10s and
    # consults a GPUSensor (Prometheus DCGM/nvidia metrics + the gateway's
    # own TTFT histogram) to decide add/hold/drain. See app/scheduler.py.
    def _ollama_in_flight() -> int:
        provider = _provider_state.get("ollama")
        return int(getattr(provider, "in_flight", 0) or 0)

    try:
        app.state.scheduler = maybe_start_scheduler(in_flight_getter=_ollama_in_flight)
    except Exception:  # noqa: BLE001 — scheduler must never block boot
        log.exception("scheduler init failed; Ollama pool will be empty")
        app.state.scheduler = None
    # Expose to OTel observable-gauge callbacks (background metrics thread).
    _scheduler_state["scheduler"] = app.state.scheduler

    log.info(
        "llm-gateway ready: providers=%s default=%s pricing=%s routing=%s "
        "claude_sentinel=$%.2f/day claude_sample_base=%.3f claude_tier_base=$%.2f",
        list(providers.keys()),
        DEFAULT_PROVIDER,
        PRICING_CONFIG_PATH,
        ROUTING_CONFIG_PATH,
        CLAUDE_SANITY_SENTINEL_USD,
        claude_sample_rate(0.0),
        float(os.environ.get("CLAUDE_SAMPLE_TIER_BASE", "40.0")),
    )
    yield
    # Flush + close the Sigil client on shutdown so in-flight generation
    # events don't get dropped during a rolling restart.
    try:
        sigil_shutdown()
    except Exception:  # noqa: BLE001
        log.exception("Sigil shutdown failed")
    # Stop the scheduler ticker before the event loop tears down.
    scheduler = getattr(app.state, "scheduler", None)
    if scheduler is not None:
        try:
            await scheduler.stop()
        except Exception:  # noqa: BLE001
            log.exception("scheduler shutdown failed")


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

# Admission + Claude-spend metrics — OTel-native so they flow through the
# collector → Grafana Cloud Prometheus alongside gen_ai.*. Names use dots
# here; the Prometheus serializer converts them to underscores.
#
# DEPRECATED: spillover counter. The "ollama-first + spillover" model has
# been retired in favor of admission-controlled coin-flip routing. Kept as
# an always-zero counter so existing dashboards still parse it cleanly;
# remove once every downstream panel has migrated to admission.* metrics.
SPILLOVER_TOTAL = _meter.create_counter(
    name="llm_gateway.spillover.total",
    description="DEPRECATED. Always 0 since the admission-routing redesign "
                "retired ollama-first+spillover. Use llm_gateway.admission.* "
                "instead.",
)

# Per-request admission outcome. ``decision ∈ {admit, deny}``, one row per
# admission test (so a denied primary + admitted secondary emits two rows).
# Lane lets the dashboard split default vs interactive even though admission
# only actually runs for the default lane today.
ADMISSION_TOTAL = _meter.create_counter(
    name="llm_gateway.admission.total",
    description="Admission decisions, one per provider tested. "
                "Labels: provider, decision (admit|deny), lane (default|interactive).",
)

# Per-request DENY breakdown by reason. Emitted exactly once per /v1/complete
# call that ends in a 429. Live reasons under the tiered-sampler model:
# ollama_saturated, claude_not_sampled (the "dice picked Ollama AND Ollama
# was full" hint), claude_sanity_sentinel ($200 paranoia ceiling).
# Legacy reasons (claude_overpace, claude_daily_cap_reached, both) are kept
# in the back-compat enum but never emitted live.
ADMISSION_DENIED = _meter.create_counter(
    name="llm_gateway.admission.denied",
    description="Admission denials by reason. "
                "Live reasons: ollama_saturated, claude_not_sampled, "
                "claude_sanity_sentinel. Lane: default|interactive.",
)

# DEPRECATED: linear-pace observable. The tiered-sampler model replaced the
# linear pacing check; this gauge is kept as a flat 0 so any dashboard panel
# that still queries the series stays parseable. Remove once dashboards
# migrate to llm_gateway.claude.sample.rate.
def _observe_claude_pace(options):  # type: ignore[no-untyped-def]
    from opentelemetry.metrics import Observation
    return [Observation(0.0, {})]


_meter.create_observable_gauge(
    name="llm_gateway.claude.pace.usd",
    description="DEPRECATED. Always 0 since the tiered-sampler redesign "
                "retired linear pacing. Use llm_gateway.claude.sample.rate "
                "instead.",
    callbacks=[_observe_claude_pace],
)


# Current Claude sample probability, given today's default-lane spend.
# Reads off the same ledger the dispatcher rolls against, so this gauge is
# the live "what fraction of default-lane requests are trying Claude
# right now" signal for dashboards.
def _observe_claude_sample_rate(options):  # type: ignore[no-untyped-def]
    from opentelemetry.metrics import Observation
    _maybe_reset_daily_counters()
    return [Observation(
        float(claude_sample_rate(_claude_default_spend_today)), {}
    )]


_meter.create_observable_gauge(
    name="llm_gateway.claude.sample.rate",
    description="Probability that the next default-lane request will try "
                "Claude. 10% under $40 of today's default-lane spend; "
                "/10x per additional $20 above $40.",
    callbacks=[_observe_claude_sample_rate],
)


# Integer tier index for the sample-rate step function. 0 == base (10%),
# 1 == /10 (1%), 2 == /100 (0.1%), … Useful for state-timeline panels.
def _observe_claude_sample_tier(options):  # type: ignore[no-untyped-def]
    from opentelemetry.metrics import Observation
    _maybe_reset_daily_counters()
    return [Observation(
        int(claude_sample_tier(_claude_default_spend_today)), {}
    )]


_meter.create_observable_gauge(
    name="llm_gateway.claude.sample.tier",
    description="Discrete tier index for the Claude sample-rate step "
                "function. 0 == base rate, each +1 step divides the rate "
                "by 10.",
    callbacks=[_observe_claude_sample_tier],
)

# Histogram of the retry_after_s value we *told* callers to wait when 429ing
# them. Server-side "how patient are callers told to be" signal. Bucket
# boundaries cover the typical Ollama queue-drain range (<5s) through to
# midnight rollover (worst case for the hard-cap reason ~86k s).
CALLER_WAIT_SECONDS = _meter.create_histogram(
    name="llm_gateway.caller.wait.seconds",
    description="Retry-After seconds returned to a caller in a 429 admission "
                "denial. Server-side view of caller wait time.",
    unit="s",
)


# Module-level holder for the Ollama provider dict; populated by the
# lifespan handler at startup. The observable-gauge callbacks below read
# from it instead of the FastAPI request-scoped state.
_provider_state: dict[str, Provider] = {}

# Module-level holder for the OllamaScheduler (populated by lifespan). The
# pool/scheduler observable-gauge callbacks read from it on the background
# metrics thread so they don't reach into FastAPI request state.
_scheduler_state: dict[str, "object | None"] = {"scheduler": None}


def _observe_ollama_in_flight(options):  # type: ignore[no-untyped-def]
    """Callback: report the live Ollama in-flight count for the OTel gauge."""
    from opentelemetry.metrics import Observation
    ollama_provider = _provider_state.get("ollama")
    value = 0
    if ollama_provider is not None:
        value = int(getattr(ollama_provider, "in_flight", 0) or 0)
    return [Observation(value, {})]


def _observe_claude_daily_spend(options):  # type: ignore[no-untyped-def]
    """Callback: report today's cumulative Claude spend (both lanes summed).

    Retained for backwards compat with existing dashboards that read
    ``llm_gateway_claude_daily_spend_usd``. The lane-specific gauges
    (default / interactive) are the canonical signals going forward.
    """
    from opentelemetry.metrics import Observation
    _maybe_reset_daily_counters()
    total = _claude_default_spend_today + _claude_interactive_spend_today
    return [Observation(float(total), {})]


def _observe_claude_default_spend(options):  # type: ignore[no-untyped-def]
    """Callback: report today's default-lane Claude spend (subject to cap)."""
    from opentelemetry.metrics import Observation
    _maybe_reset_daily_counters()
    return [Observation(float(_claude_default_spend_today), {})]


def _observe_claude_interactive_spend(options):  # type: ignore[no-untyped-def]
    """Callback: report today's interactive-lane Claude spend (informational)."""
    from opentelemetry.metrics import Observation
    _maybe_reset_daily_counters()
    return [Observation(float(_claude_interactive_spend_today), {})]


def _observe_claude_daily_budget(options):  # type: ignore[no-untyped-def]
    """Callback: report the legacy budget gauge value (back-compat).

    DEPRECATED under the tiered-sampler model — there's no longer a daily
    *budget* per se, just a $200 sanity sentinel. We return the sentinel
    here so any dashboard panel that still keys off this series shows a
    sensible ceiling instead of a stale $20.
    """
    from opentelemetry.metrics import Observation
    return [Observation(float(CLAUDE_SANITY_SENTINEL_USD), {})]


def _observe_claude_daily_cap(options):  # type: ignore[no-untyped-def]
    """Callback: report the default-lane hard ceiling (sanity sentinel).

    DEPRECATED — under the tiered-sampler model there is no daily *cap*;
    the sampler decays the rate to vanishingly small instead of slamming
    a door. The number reported here is the sanity sentinel ($200), the
    paranoia ceiling that hard-stops Claude if something pathological
    drives spend that high.
    """
    from opentelemetry.metrics import Observation
    return [Observation(float(CLAUDE_SANITY_SENTINEL_USD), {})]


_meter.create_observable_gauge(
    name="llm_gateway.ollama.in_flight",
    description="Live count of Ollama requests currently being served on this gateway pod.",
    callbacks=[_observe_ollama_in_flight],
)
_meter.create_observable_gauge(
    name="llm_gateway.claude.daily.spend.usd",
    description="Cumulative Anthropic spend (USD) for the current UTC day — "
                "sum of default and interactive lanes; resets at midnight. "
                "Retained for back-compat; prefer the lane-specific gauges.",
    callbacks=[_observe_claude_daily_spend],
)
_meter.create_observable_gauge(
    name="llm_gateway.claude.default.spend.usd",
    description="Default-lane Anthropic spend (USD) for the current UTC day. "
                "Drives the tiered Claude sample rate — each $20 above $40 "
                "cuts the sampling probability by 10x.",
    callbacks=[_observe_claude_default_spend],
)
_meter.create_observable_gauge(
    name="llm_gateway.claude.interactive.spend.usd",
    description="Interactive-lane Anthropic spend (USD) for the current UTC "
                "day. Informational only — not subject to admission.",
    callbacks=[_observe_claude_interactive_spend],
)
_meter.create_observable_gauge(
    name="llm_gateway.claude.daily.budget.usd",
    description="DEPRECATED back-compat gauge. Reports the sanity sentinel "
                "($200), not a real daily budget — the tiered-sampler model "
                "retired the hard cap. Migrate dashboards to "
                "llm_gateway.claude.sample.rate.",
    callbacks=[_observe_claude_daily_budget],
)
_meter.create_observable_gauge(
    name="llm_gateway.claude.daily.cap.usd",
    description="DEPRECATED back-compat gauge. Reports the sanity sentinel "
                "($200) — the paranoia ceiling that hard-stops Claude. Not "
                "an operating limit. Use llm_gateway.claude.sample.rate "
                "for the real throttling signal.",
    callbacks=[_observe_claude_daily_cap],
)


# ---- Ollama model-pool scheduler gauges -----------------------------------
# These callbacks read the latest scheduler state on each collection cycle.
# Every gauge falls back to a safe zero when the scheduler isn't running
# (boot races, unit tests with no Helm wiring) so panels never go NaN.

def _get_scheduler():
    """Return the running OllamaScheduler instance, or None when disabled."""
    return _scheduler_state.get("scheduler")


def _scheduler_on_request_complete(
    request: Request, provider_name: str, req: "CompleteRequest"
) -> None:
    """Bump the scheduler's per-model request counter after a completion.

    Safe to call from any error path — no-ops when the scheduler isn't
    running, the provider wasn't Ollama, or no model_override was pinned
    (the latter shouldn't happen post-pinning but we guard anyway).
    """
    if provider_name != "ollama":
        return
    scheduler = getattr(request.app.state, "scheduler", None) or _get_scheduler()
    if scheduler is None:
        return
    model = getattr(req, "model_override", None)
    if not model:
        return
    try:
        from .sigil import _derive_session_id  # local import: avoid cycle
        session_id = _derive_session_id(req)
    except Exception:  # noqa: BLE001
        session_id = ""
    try:
        scheduler.on_request_complete(session_id, model)
    except Exception:  # noqa: BLE001
        log.exception("scheduler.on_request_complete failed")


def _observe_ollama_pool_size(options):  # type: ignore[no-untyped-def]
    from opentelemetry.metrics import Observation
    sched = _get_scheduler()
    value = 0
    if sched is not None:
        value = int(sched.snapshot_for_metrics()["loaded"])
    return [Observation(value, {})]


def _observe_ollama_pool_min(options):  # type: ignore[no-untyped-def]
    from opentelemetry.metrics import Observation
    sched = _get_scheduler()
    value = int(getattr(sched, "pool_min", 0) or 0)
    return [Observation(value, {})]


def _observe_ollama_pool_max(options):  # type: ignore[no-untyped-def]
    from opentelemetry.metrics import Observation
    sched = _get_scheduler()
    value = int(getattr(sched, "pool_max", 0) or 0)
    return [Observation(value, {})]


def _observe_ollama_model_state(options):  # type: ignore[no-untyped-def]
    """Per-model state indicator. Emits one Observation per (model, state) pair.

    Every state row for every loaded model is reported on each cycle as a
    0/1 indicator so PromQL panels can use ``last_over_time(... ==1)`` to
    show "which state is this model in right now". A model not currently
    loaded emits nothing at all (no row), so the metric naturally tracks
    pool churn.
    """
    from opentelemetry.metrics import Observation
    sched = _get_scheduler()
    obs: list = []
    if sched is None:
        return obs
    info = sched.snapshot_for_metrics()
    for entry in info.get("models", []):
        current = entry["state"]
        for state in ("loading", "active", "draining"):
            obs.append(
                Observation(
                    1 if state == current else 0,
                    {"model": entry["name"], "state": state},
                )
            )
    return obs


def _observe_ollama_model_requests_served(options):  # type: ignore[no-untyped-def]
    """Per-model current-cycle request counter (0..requests_per_lifecycle)."""
    from opentelemetry.metrics import Observation
    sched = _get_scheduler()
    obs: list = []
    if sched is None:
        return obs
    for entry in sched.snapshot_for_metrics().get("models", []):
        obs.append(
            Observation(int(entry["requests_served"]), {"model": entry["name"]})
        )
    return obs


def _observe_ollama_model_assigned_sessions(options):  # type: ignore[no-untyped-def]
    """Per-model sticky-session count (== unique users currently pinned)."""
    from opentelemetry.metrics import Observation
    sched = _get_scheduler()
    obs: list = []
    if sched is None:
        return obs
    for entry in sched.snapshot_for_metrics().get("models", []):
        obs.append(
            Observation(
                int(entry["assigned_sessions"]), {"model": entry["name"]}
            )
        )
    return obs


def _observe_ollama_scheduler_verdict(options):  # type: ignore[no-untyped-def]
    """Verdict from the last tick — 0=add, 1=hold, 2=drain."""
    from opentelemetry.metrics import Observation
    sched = _get_scheduler()
    verdict = "hold"
    if sched is not None:
        verdict = str(sched.snapshot_for_metrics().get("verdict") or "hold")
    code = {"add": 0, "hold": 1, "drain": 2}.get(verdict, 1)
    return [Observation(code, {})]


def _observe_ollama_gpu_vram_pct(options):  # type: ignore[no-untyped-def]
    from opentelemetry.metrics import Observation
    sched = _get_scheduler()
    snap = None
    if sched is not None:
        snap = sched.snapshot_for_metrics().get("snapshot")
    value = float(getattr(snap, "vram_pct", 0.0) or 0.0)
    return [Observation(value, {})]


def _observe_ollama_gpu_util_pct(options):  # type: ignore[no-untyped-def]
    from opentelemetry.metrics import Observation
    sched = _get_scheduler()
    snap = None
    if sched is not None:
        snap = sched.snapshot_for_metrics().get("snapshot")
    value = float(getattr(snap, "gpu_util_pct", 0.0) or 0.0)
    return [Observation(value, {})]


def _observe_ollama_ttft_p95(options):  # type: ignore[no-untyped-def]
    from opentelemetry.metrics import Observation
    sched = _get_scheduler()
    snap = None
    if sched is not None:
        snap = sched.snapshot_for_metrics().get("snapshot")
    value = float(getattr(snap, "ttft_p95_s", 0.0) or 0.0)
    return [Observation(value, {})]


def _observe_ollama_queue_depth(options):  # type: ignore[no-untyped-def]
    from opentelemetry.metrics import Observation
    sched = _get_scheduler()
    value = 0
    if sched is not None:
        value = int(sched.snapshot_for_metrics().get("queue_depth") or 0)
    return [Observation(value, {})]


_meter.create_observable_gauge(
    name="llm_gateway.ollama.pool.size",
    description="Count of Ollama models currently LOADED (ACTIVE+DRAINING+LOADING).",
    callbacks=[_observe_ollama_pool_size],
)
_meter.create_observable_gauge(
    name="llm_gateway.ollama.pool.min",
    description="Configured minimum pool size — scheduler loads aggressively below this.",
    callbacks=[_observe_ollama_pool_min],
)
_meter.create_observable_gauge(
    name="llm_gateway.ollama.pool.max",
    description="Configured maximum pool size — scheduler refuses to load above this.",
    callbacks=[_observe_ollama_pool_max],
)
_meter.create_observable_gauge(
    name="llm_gateway.ollama.model.state",
    description="Per-model state indicator (0|1). Labels: model, state in "
                "{loading,active,draining}. Only loaded models emit rows.",
    callbacks=[_observe_ollama_model_state],
)
_meter.create_observable_gauge(
    name="llm_gateway.ollama.model.requests_served",
    description="Per-model current-cycle request count (0..requests_per_lifecycle). "
                "Resets to 0 on every (re)load.",
    callbacks=[_observe_ollama_model_requests_served],
)
_meter.create_observable_gauge(
    name="llm_gateway.ollama.model.assigned_sessions",
    description="Per-model count of sticky-pinned conversation sessions.",
    callbacks=[_observe_ollama_model_assigned_sessions],
)
_meter.create_observable_gauge(
    name="llm_gateway.ollama.scheduler.verdict",
    description="Verdict from the most recent scheduler tick: 0=add, 1=hold, 2=drain.",
    callbacks=[_observe_ollama_scheduler_verdict],
)
_meter.create_observable_gauge(
    name="llm_gateway.ollama.gpu.vram_pct",
    description="Most recent GPU VRAM utilization seen by the scheduler (%).",
    callbacks=[_observe_ollama_gpu_vram_pct],
)
_meter.create_observable_gauge(
    name="llm_gateway.ollama.gpu.util_pct",
    description="Most recent 5m-avg GPU compute utilization seen by the scheduler (%).",
    callbacks=[_observe_ollama_gpu_util_pct],
)
_meter.create_observable_gauge(
    name="llm_gateway.ollama.ttft.p95_seconds",
    description="Most recent 5m-window TTFT p95 (seconds) seen by the scheduler.",
    callbacks=[_observe_ollama_ttft_p95],
)
_meter.create_observable_gauge(
    name="llm_gateway.ollama.queue.depth",
    description="Number of candidate models waiting to be loaded into the pool.",
    callbacks=[_observe_ollama_queue_depth],
)


tracer = trace.get_tracer("llm_gateway")


# Legacy "daily budget" env var. Under the tiered-sampler model this no
# longer drives behavior — the sample-rate curve is fixed by
# CLAUDE_SAMPLE_TIER_BASE/WIDTH/BASE_RATE, and the hard stop is the
# CLAUDE_SANITY_SENTINEL_USD ceiling. We still READ the env var so existing
# Helm values that set CLAUDE_DAILY_BUDGET_USD don't error, and so the
# deprecated llm_gateway.claude.daily.budget.usd gauge has a value to
# emit. Default ($20) is preserved for historical compatibility but is
# strictly informational now.
_CLAUDE_DAILY_BUDGET_USD = float(os.environ.get("CLAUDE_DAILY_BUDGET_USD", "20.0"))

# Split daily ledger: default-lane spend (cap-bearing) + interactive-lane
# spend (informational). The legacy ``_claude_daily_spent_usd`` symbol is
# the SUM of the two — exposed for back-compat with the old gauge.
_claude_default_spend_today: float = 0.0
_claude_interactive_spend_today: float = 0.0
_claude_budget_day_utc: str = ""


def _maybe_reset_daily_counters() -> None:
    """Roll the per-lane daily ledger over at UTC midnight."""
    global _claude_default_spend_today, _claude_interactive_spend_today
    global _claude_budget_day_utc
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if today != _claude_budget_day_utc:
        _claude_default_spend_today = 0.0
        _claude_interactive_spend_today = 0.0
        _claude_budget_day_utc = today


# Backwards-compat alias — pre-existing helpers in other modules may still
# import the old name. Forwards to the lane-aware reset.
def _maybe_reset_budget_day() -> None:
    """Deprecated alias for ``_maybe_reset_daily_counters``."""
    _maybe_reset_daily_counters()


def _record_claude_spend(usd: float, *, lane: str) -> None:
    """Add a completed Claude call's USD cost to today's tally for ``lane``.

    ``lane`` ∈ {"default", "interactive"}. Negative values are clamped to 0
    (cost calc shouldn't ever produce negatives, but belt-and-suspenders).
    """
    global _claude_default_spend_today, _claude_interactive_spend_today
    _maybe_reset_daily_counters()
    delta = max(0.0, float(usd))
    if lane == "interactive":
        _claude_interactive_spend_today += delta
    else:
        _claude_default_spend_today += delta


def claude_budget_state() -> dict[str, float | str]:
    """Snapshot of the running ledger — exposed via /metrics for the dashboard.

    The ``budget_usd`` / ``remaining_usd`` fields are kept for back-compat
    with anything that polls this dict; under the tiered-sampler model the
    real signal is ``sample_rate`` (the live probability that a default-lane
    request will try Claude). The legacy fields report the sanity sentinel
    as if it were a budget so old callers see a sane shape.
    """
    _maybe_reset_daily_counters()
    total_spent = _claude_default_spend_today + _claude_interactive_spend_today
    rate = claude_sample_rate(_claude_default_spend_today)
    return {
        "budget_usd": CLAUDE_SANITY_SENTINEL_USD,
        "spent_usd": total_spent,
        "default_spent_usd": _claude_default_spend_today,
        "interactive_spent_usd": _claude_interactive_spend_today,
        "remaining_usd": max(
            0.0, CLAUDE_SANITY_SENTINEL_USD - _claude_default_spend_today
        ),
        "sample_rate": float(rate),
        "sample_tier": int(claude_sample_tier(_claude_default_spend_today)),
        "sanity_sentinel_usd": CLAUDE_SANITY_SENTINEL_USD,
        "day_utc": _claude_budget_day_utc,
    }


def _detect_lane(req: CompleteRequest, request: Request) -> str:
    """Return ``"interactive"`` iff this call is interactive-lane, else ``"default"``.

    Two routes into the interactive lane (both honored):

    * Body field: ``ai_o11y.traffic_origin == "interactive"``.
    * Header: ``X-Traffic-Origin: interactive`` (case-insensitive value).

    Header form lets non-Python clients tag traffic without rebuilding their
    request body; the body form is the canonical channel for in-cluster
    callers that already carry the ``ai_o11y`` dict.
    """
    body_origin = (req.ai_o11y.get("traffic_origin") or "").strip().lower()
    if body_origin == "interactive":
        return "interactive"
    header_origin = (request.headers.get("x-traffic-origin") or "").strip().lower()
    if header_origin == "interactive":
        return "interactive"
    return "default"


def _sample_target() -> str:
    """Roll the tiered Claude sampler → ``"anthropic"`` or ``"ollama"``.

    Reads today's default-lane Claude spend from the module-level ledger
    and asks ``claude_sample_rate`` for the current probability of trying
    Claude. Wrapped so unit tests can mock ``random.random`` without
    monkey-patching main.py internals.

    Behavior:
      * At $0 spend → 10% Claude.
      * At $50 spend → 1% Claude.
      * At $200+ → effectively 0% (sanity sentinel will deny anyway).
    """
    _maybe_reset_daily_counters()
    rate = claude_sample_rate(_claude_default_spend_today)
    return "anthropic" if random.random() < rate else "ollama"


# Kept for back-compat with any external test that imports it. New code
# should call _sample_target. The legacy 50/50 coin flip is no longer the
# routing primitive — but unit tests in the repo still reference this name.
def _coin_flip() -> str:
    """DEPRECATED. Forwards to ``_sample_target`` for routing parity.

    The original 50/50 coin flip was replaced by the tiered Claude
    sampler. The function name is preserved so existing imports don't
    break; new code should use ``_sample_target`` directly.
    """
    return _sample_target()


def _ollama_admission_state(request: Request) -> dict:
    """Build the state-dict ``ollama_admit`` expects."""
    providers: dict[str, Provider] = request.app.state.providers
    ollama_provider = providers.get("ollama")
    return {
        "in_flight": int(getattr(ollama_provider, "in_flight", 0) or 0),
        "saturation_threshold": int(
            getattr(ollama_provider, "_saturation_threshold", 0)
            or os.environ.get("OLLAMA_SATURATION_THRESHOLD", "8")
        ),
    }


def _claude_admission_state() -> dict:
    """Build the state-dict ``claude_admit_default`` expects."""
    _maybe_reset_daily_counters()
    return {
        "default_spend_usd": _claude_default_spend_today,
        "sentinel_usd": CLAUDE_SANITY_SENTINEL_USD,
    }


def _route_default_lane(
    request: Request,
) -> tuple[str, Provider, dict] | tuple[None, None, dict]:
    """Run the tiered-sampler routing for the default lane.

    Returns either:

    * ``(provider_name, provider, debug)`` when the chosen target admits.
      ``debug`` carries which provider the dice landed on + sample-rate
      context for span attributes.
    * ``(None, None, debug)`` when admission refuses. There is no fallback
      between providers under the tiered-sampler model — if the dice
      picks Ollama and Ollama is full, the dispatcher returns 429.
      ``debug`` carries the deny reason + retry_after_s.
    """
    providers: dict[str, Provider] = request.app.state.providers
    _maybe_reset_daily_counters()
    spend = _claude_default_spend_today
    rate = claude_sample_rate(spend)
    target = _sample_target()

    debug: dict = {
        "primary_provider_tried": target,
        # Kept for back-compat with the body schema; the tiered-sampler
        # model has no secondary — empty string signals "not attempted".
        "secondary_provider_tried": "",
        "primary_reason": "",
        "secondary_reason": "",
        "primary_wait_s": 0.0,
        "secondary_wait_s": 0.0,
        "sample_rate": float(rate),
        "sample_tier": int(claude_sample_tier(spend)),
        "default_spend_usd": float(spend),
    }

    if target == "anthropic":
        if "anthropic" not in providers:
            # Anthropic provider not loaded (config missing or disabled).
            # Surface that as a deny so the dispatcher can 429 cleanly.
            debug["primary_reason"] = "anthropic_unavailable"
            debug["primary_wait_s"] = 1.0
            ADMISSION_TOTAL.add(
                1,
                {"provider": "anthropic", "decision": "deny", "lane": "default"},
            )
            return None, None, debug
        admitted, wait_s, reason = claude_admit_default(_claude_admission_state())
        debug["primary_wait_s"] = wait_s
        debug["primary_reason"] = reason
        ADMISSION_TOTAL.add(
            1,
            {
                "provider": "anthropic",
                "decision": "admit" if admitted else "deny",
                "lane": "default",
            },
        )
        if admitted:
            return "anthropic", providers["anthropic"], debug
        return None, None, debug

    # target == ollama
    if "ollama" not in providers:
        debug["primary_reason"] = "ollama_unavailable"
        debug["primary_wait_s"] = 1.0
        ADMISSION_TOTAL.add(
            1, {"provider": "ollama", "decision": "deny", "lane": "default"}
        )
        return None, None, debug
    admitted, wait_s, reason = ollama_admit(_ollama_admission_state(request))
    debug["primary_wait_s"] = wait_s
    # If Ollama denies and the dice didn't pick Claude, tag the reason as
    # ``claude_not_sampled`` to disambiguate "we rolled Ollama, it was
    # full" from "we rolled Ollama because the dice never offered Claude
    # at this spend tier". Wire behavior is identical — the label is
    # informational for the dashboard.
    if not admitted:
        debug["primary_reason"] = REASON_CLAUDE_NOT_SAMPLED
    else:
        debug["primary_reason"] = reason
    ADMISSION_TOTAL.add(
        1,
        {
            "provider": "ollama",
            "decision": "admit" if admitted else "deny",
            "lane": "default",
        },
    )
    if admitted:
        return "ollama", providers["ollama"], debug
    return None, None, debug


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

    Lane detection runs first:

    * Interactive lane (``ai_o11y.traffic_origin == "interactive"`` OR the
      ``X-Traffic-Origin: interactive`` header) bypasses admission and is
      forced to Claude. Spend goes onto the interactive ledger, which is
      NOT subject to the daily cap.
    * Default lane runs a coin-flip + dual admission test. If neither
      provider admits, the dispatcher returns HTTP 429 with a Retry-After
      header and JSON body describing which gate refused.

    The legacy ``provider_override`` field is no longer honored for routing
    — interactive auto-pins to Claude, default goes through admission. The
    field stays on the request schema for backwards-compat (callers can
    keep sending it without erroring out).
    """
    lane = _detect_lane(req, request)
    providers: dict[str, Provider] = request.app.state.providers
    admission_debug: dict = {}

    if lane == "interactive":
        # Interactive bypasses admission entirely and always lands on Claude.
        # Track the admit-decision on the metric for visibility (lane label
        # makes it distinguishable from default-lane admits).
        provider = providers.get("anthropic")
        if provider is None:
            # Fall back to whatever is available — interactive should never
            # 503 just because Anthropic config is missing.
            if not providers:
                raise HTTPException(
                    status_code=503, detail="No LLM providers loaded."
                )
            provider_name, provider = next(iter(providers.items()))
        else:
            provider_name = "anthropic"
        ADMISSION_TOTAL.add(
            1,
            {
                "provider": provider_name,
                "decision": "admit",
                "lane": "interactive",
            },
        )
    else:
        # Default lane — tiered Claude sampler + single-provider admission.
        provider_name, provider, admission_debug = _route_default_lane(request)
        # If admission landed on Ollama, ask the model-pool scheduler which
        # concrete model this conversation should pin to. Sticky routing
        # means the first request in a session picks the model; every
        # subsequent request for the same session_id reuses it — even
        # while the model is DRAINING — until the session expires.
        if provider is not None and provider_name == "ollama":
            # sb-router fast-path: it sends a tiny 12-token classification
            # prompt to pick a downstream specialist — no need for a big
            # model AND no need for sticky session pinning (each request
            # is inherently 1-turn). Pin straight to the fastest pool model
            # so its TTFT collapses from 800-1800ms to ~50-100ms.
            if req.specialist == "sb-router":
                req.model_override = req.model_override or "qwen2.5:0.5b"
                admission_debug["scheduler_model"] = req.model_override
                admission_debug["sb_router_fastpath"] = True
            else:
                scheduler = getattr(request.app.state, "scheduler", None)
                if scheduler is not None:
                    from .sigil import _derive_session_id  # local import: avoid cycle
                    _session_id_for_route = _derive_session_id(req)
                    chosen = scheduler.route(_session_id_for_route)
                    if chosen is None:
                        # Scheduler is up but the pool is currently empty —
                        # next tick (≤10s) will load the first queued model.
                        # Tell the caller to retry shortly. The existing
                        # 429-emitting branch below stamps the deny counter +
                        # caller-wait histogram, so we only need to set state.
                        provider = None
                        admission_debug["primary_reason"] = REASON_OLLAMA_POOL_EMPTY
                        admission_debug["primary_wait_s"] = 5.0
                    else:
                        # Pin the chosen model onto the request so the Ollama
                        # provider serves THIS specific model instead of the
                        # provider's static default (or the retired rotation
                        # ticker). model_override always wins inside the
                        # provider, which is exactly what we need here.
                        req.model_override = req.model_override or chosen
                        admission_debug["scheduler_model"] = chosen
        if provider is None:
            # Admission refused → HTTP 429. No fallback between providers
            # under the tiered-sampler model; the dice IS the admission.
            denied_reason = (
                admission_debug.get("primary_reason") or REASON_OLLAMA_SATURATED
            )
            retry_after = float(admission_debug.get("primary_wait_s", 0.0) or 0.0)
            ADMISSION_DENIED.add(
                1, {"reason": denied_reason, "lane": "default"}
            )
            CALLER_WAIT_SECONDS.record(
                retry_after, {"lane": "default", "reason": denied_reason}
            )
            body = {
                "reason": denied_reason,
                "retry_after_s": round(retry_after, 3),
                "primary_provider_tried": admission_debug.get(
                    "primary_provider_tried", ""
                ),
                # Kept for body-schema back-compat; the tiered-sampler model
                # never tries a second provider so this is always empty.
                "secondary_provider_tried": admission_debug.get(
                    "secondary_provider_tried", ""
                ),
                "sample_rate": admission_debug.get("sample_rate", 0.0),
                "sample_tier": admission_debug.get("sample_tier", 0),
            }
            # Retry-After header is integer seconds per RFC 7231; round up
            # so callers don't immediately retry into the same denial.
            retry_after_header = max(1, int(retry_after + 0.999))
            return JSONResponse(
                status_code=429,
                content=body,
                headers={"Retry-After": str(retry_after_header)},
            )

    with tracer.start_as_current_span("llm_gateway.complete") as span:
        # gen_ai.* span attrs follow OTel GenAI semantic conventions; the
        # canonical session.id / user.id pair lets the AI Observability
        # plugin correlate traces with sigil generation events and Loki
        # logs without per-deployment glue.
        from .sigil import _derive_session_id  # local import: avoid cycle
        _session_id = _derive_session_id(req)
        span.set_attribute("gen_ai.system", provider_name)
        span.set_attribute("llm_gateway.lane", lane)
        if admission_debug:
            # Annotate which provider the coin flip picked + any deny
            # reasons that happened on the way to the eventual admit. Lets
            # the dashboard correlate "primary denied, secondary admitted"
            # with downstream latency or error spikes.
            span.set_attribute(
                "llm_gateway.admission.primary",
                str(admission_debug.get("primary_provider_tried", "")),
            )
            if admission_debug.get("primary_reason"):
                span.set_attribute(
                    "llm_gateway.admission.primary_reason",
                    str(admission_debug["primary_reason"]),
                )
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
                # Scheduler bookkeeping: the model still answered (badly).
                # Count this as a lifecycle increment so a sick model walks
                # itself off the pool instead of saturating it forever.
                _scheduler_on_request_complete(request, provider_name, req)
                raise HTTPException(
                    status_code=504,
                    detail=f"{provider_name}: timed out after {_PROVIDER_TIMEOUT_S:.0f}s",
                )
            except Exception as exc:  # noqa: BLE001 — translate to HTTP 502 for caller.
                span.record_exception(exc)
                span.set_attribute("error", True)
                log.exception("provider %s failed", provider_name)
                _scheduler_on_request_complete(request, provider_name, req)
                raise HTTPException(status_code=502, detail=f"{provider_name}: {exc}")
        duration_seconds = time.monotonic() - start_time
        span.set_attribute("llm_gateway.streaming.used", streaming_used)
        if streaming_used and ttft_ms is not None:
            span.set_attribute("gen_ai.server.time_to_first_token", ttft_ms / 1000.0)

        # Scheduler bookkeeping: bump the per-model request counter so the
        # state machine knows to flip ACTIVE -> DRAINING at the lifecycle
        # boundary (default 100 requests). No-op when the call didn't go
        # to Ollama.
        _scheduler_on_request_complete(request, provider_name, req)

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

        # Add the just-completed call's USD to the per-lane Claude ledger.
        # Default-lane spend feeds back into the tiered sampler — each $20
        # of additional spend above $40 cuts the next request's Claude
        # sample rate by 10x. Interactive-lane spend is informational only.
        # The OTel observable-gauge callbacks (see _observe_claude_*) read
        # this state on each collection cycle, so no explicit .set() needed.
        if provider_name == "anthropic":
            _record_claude_spend(float(cost["total_usd"]), lane=lane)

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
