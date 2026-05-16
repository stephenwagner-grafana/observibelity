"""Sigil generation-event emitter.

Feeds Grafana Cloud's AI Observability plugin (Sigil) by exporting one
generation record per /v1/complete and one tool-execution record per
``tool_use`` in the model's response. Uses the ``sigil_sdk`` gRPC client
(the same SDK that drives the AI o11y demo's support-copilot), so the
event shape lines up exactly with what the Sigil ingest service +
plugin Conversations/Analytics/Tools panels expect.

Config (env, all optional — when unset the module no-ops cleanly):

  SIGIL_GENERATION_EXPORT_ENDPOINT   sigil-prod-us-east-0.grafana.net:443
  SIGIL_PROTOCOL                     grpc (default) | http
  SIGIL_BASIC_USER                   <stack id>  (required for cloud)
  SIGIL_BASIC_PASSWORD               <grafana cloud token>
  SIGIL_BEARER_TOKEN                 alt to basic
  SIGIL_TENANT_ID                    alt to basic
  SIGIL_INSECURE                     "true" to disable TLS (localhost dev)

The export is fire-and-forget: failures only log, never raise — Sigil is
observability, it must never take a request down.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Iterator, Optional

from opentelemetry import trace

from .providers.base import CompleteRequest, CompleteResponse

log = logging.getLogger(__name__)

# Fallback agent name when a generation event is somehow emitted without a
# specialist tag (shouldn't happen — every /v1/complete request carries one —
# but keeps the Agents page free of empty-string buckets if it ever does).
_AGENT_NAME_FALLBACK = "observibelity-llm-gateway"
_SERVICE_NAME = "llm-gateway"
_SERVICE_NAMESPACE = "observibelity"
_DEFAULT_PROVIDER = "anthropic"
# operation_name=streamText is the magic value that makes Sigil's SDK
# auto-emit the gen_ai.client.time_to_first_token histogram on flush —
# the Sigil plugin's TTFT panel reads that series.
_OPERATION = "streamText"
_AGENT_OPERATION_TAG = "gateway.complete"
_TOOL_OPERATION = "gateway.tool_call"

# Providers whose pricing Sigil already maintains. We omit our local cost
# estimate for these so Sigil's licensed pricing table is the sole source
# of truth, per the "Sigil owns prod license" directive. Anything outside
# this set (Ollama, custom local models) still carries our GPU-amortized
# estimate so the plugin's Cost panel isn't empty.
_SIGIL_LICENSED_PROVIDERS = frozenset(
    {"anthropic", "openai", "google", "gemini", "cohere", "bedrock"}
)

_client: Optional[Any] = None
_initialized = False


def _should_emit_cost(provider: str | None) -> bool:
    """Return True iff WE should emit cost fields for this provider.

    Sigil's built-in pricing table covers Anthropic, OpenAI, Google, etc.
    For those, omit cost from the event so Sigil computes it from the
    canonical pricing it maintains. For Ollama / custom, emit our estimate
    so the plugin's Cost panel still has data.
    """
    if not provider:
        return True
    return provider.strip().lower() not in _SIGIL_LICENSED_PROVIDERS


def _derive_session_id(req: CompleteRequest) -> str:
    """Per-conversation session id for Sigil's Conversations view.

    Explicit ``ai_o11y.session_id`` (threaded from neoncart's chat widget on
    every page load) wins so each interactive visit is one conversation in
    the Conversations view. Falls back to ``persona_id + UTC date+hour`` for
    loadgen + curl callers that don't provide their own id.
    """
    explicit = (req.ai_o11y.get("session_id") if req.ai_o11y else None) or ""
    if isinstance(explicit, str) and explicit.strip():
        return explicit.strip()[:64]
    pid = (req.ai_o11y.get("persona_id") if req.ai_o11y else None) or "anonymous@acme.com"
    bucket = datetime.now(timezone.utc).strftime("%Y%m%d%H")
    return hashlib.sha256(f"{pid}:{bucket}".encode("utf-8")).hexdigest()[:16]


def _conversation_title(req: CompleteRequest) -> str:
    """Pick a human-readable title for Sigil's Conversations view.

    Uses the first user-role message — works for both the first turn (just
    the user's question) and follow-up turns (still the original question,
    since the conversation_id stays the same across turns). Falls back to
    ``specialist / usecase`` when no user message is parseable.
    """
    for msg in req.messages or []:
        if msg.get("role") != "user":
            continue
        content = msg.get("content")
        if isinstance(content, str):
            text = content.strip()
            if text:
                return text[:120]
        elif isinstance(content, list):
            # Anthropic-style content blocks: [{type:"text", text:"..."}].
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    text = (block.get("text") or "").strip()
                    if text:
                        return text[:120]
    return f"{req.specialist} / {req.ai_o11y.get('usecase') or 'adhoc'}"


def _active_trace_context() -> tuple[str, str]:
    """Return (trace_id_hex, span_id_hex) from the current OTel context.

    Returns ("", "") when there's no recording span — keeps callers
    branch-free when running in tests or before SDK init.
    """
    span = trace.get_current_span()
    if span is None:
        return "", ""
    ctx = span.get_span_context()
    if not ctx or not ctx.is_valid:
        return "", ""
    return f"{ctx.trace_id:032x}", f"{ctx.span_id:016x}"


def _agent_version() -> str:
    return os.environ.get("LLM_GATEWAY_VERSION", "v1")


def _build_config() -> Optional[Any]:
    """Construct a sigil_sdk ClientConfig from env, or None if unconfigured."""
    endpoint = os.environ.get("SIGIL_GENERATION_EXPORT_ENDPOINT", "").strip()
    if not endpoint:
        log.info("Sigil disabled: SIGIL_GENERATION_EXPORT_ENDPOINT unset")
        return None
    try:
        from sigil_sdk import ClientConfig  # type: ignore
        from sigil_sdk.config import AuthConfig, GenerationExportConfig  # type: ignore
    except ImportError:
        log.warning("sigil_sdk not installed; Sigil instrumentation disabled")
        return None

    basic_user = os.environ.get("SIGIL_BASIC_USER", "").strip()
    basic_pw = os.environ.get("SIGIL_BASIC_PASSWORD", "").strip()
    bearer = os.environ.get("SIGIL_BEARER_TOKEN", "").strip()
    tenant = os.environ.get("SIGIL_TENANT_ID", "").strip()

    if basic_user and basic_pw:
        auth = AuthConfig(mode="basic", basic_user=basic_user, basic_password=basic_pw)
    elif bearer:
        auth = AuthConfig(mode="bearer", bearer_token=bearer)
    elif tenant:
        auth = AuthConfig(mode="tenant", tenant_id=tenant)
    else:
        auth = AuthConfig(mode="none")

    insecure_default = "true" if endpoint.startswith("localhost") else "false"
    insecure = os.environ.get("SIGIL_INSECURE", insecure_default).lower() == "true"

    export = GenerationExportConfig(
        protocol=os.environ.get("SIGIL_PROTOCOL", "grpc"),
        endpoint=endpoint,
        insecure=insecure,
        auth=auth,
    )

    # Suppress sigil_sdk's auto-emitted gen_ai_client_* metrics by handing it
    # a NoOpMeter. The SDK records duration/token/TTFT histograms with
    # ``gen_ai.provider.name`` instead of the OTel semconv ``gen_ai.system``
    # — which surfaces in the Grafana Cloud AI Observability plugin as
    # "value" / "unknown" provider series alongside our canonical emits from
    # main.py. We already record the same histograms with the right label
    # set, so silencing the SDK's duplicate eliminates the dirty series
    # without losing any data the plugin actually queries.
    from opentelemetry.metrics import NoOpMeter  # local: avoid import cycle

    return ClientConfig(
        generation_export=export,
        meter=NoOpMeter("llm-gateway-sigil-noop"),
    )


def init_sigil(service_name: str = "llm-gateway") -> None:
    """Lazily construct the Sigil client on first use.

    Idempotent + best-effort: the gateway must boot even when Sigil is
    unreachable, so failures here downgrade to a logged warning. The
    ``service_name`` is the resource-level identity ("llm-gateway"); per-event
    ``agent_name`` is set from ``req.specialist`` at emit time so the Sigil
    Agents page groups generations by calling specialist (nc-chatbot,
    sb-router, etc.) instead of rolling everything under the gateway.
    """
    _ = service_name  # noqa: F841 — kept for caller-side clarity
    get_client()


def get_client() -> Optional[Any]:
    """Return the lazily-constructed Sigil client (or None)."""
    global _client, _initialized
    if _initialized:
        return _client
    _initialized = True
    cfg = _build_config()
    if cfg is None:
        return None
    try:
        from sigil_sdk import Client  # type: ignore
        _client = Client(cfg)
        endpoint = os.environ.get("SIGIL_GENERATION_EXPORT_ENDPOINT", "")
        log.info("Sigil generation export initialized: endpoint=%s", endpoint)
    except Exception:  # noqa: BLE001 — never crash on telemetry
        log.exception("failed to construct Sigil client; instrumentation disabled")
        _client = None
    return _client


def shutdown() -> None:
    """Flush + tear down the Sigil client on app shutdown."""
    global _client, _initialized
    if _client is None:
        return
    try:
        _client.shutdown()
    except Exception:  # noqa: BLE001
        log.exception("sigil client shutdown failed")
    finally:
        _client = None
        _initialized = False


# ----------------------------------------------------------------------
# Message conversion helpers
# ----------------------------------------------------------------------
def _messages_to_sigil_input(history: list[dict]) -> list[Any]:
    """Convert OpenAI-style messages -> sigil_sdk Message objects.

    The gateway speaks the OpenAI message format ({role, content}) — content
    may be a string OR a list of Anthropic-style blocks when the caller
    forwarded raw tool_use/tool_result chunks. We handle both.

    System messages are dropped — Sigil's SDK has no SYSTEM role and the
    system prompt is attached to the generation start separately.
    """
    try:
        from sigil_sdk.models import (  # type: ignore
            Message,
            MessageRole,
            Part,
            PartKind,
            ToolCall,
            ToolResult,
        )
    except ImportError:
        return []

    out: list[Any] = []
    for m in history or []:
        role = m.get("role")
        if role == "system":
            continue
        content = m.get("content")
        parts: list[Any] = []

        if isinstance(content, str):
            if content:
                parts.append(Part(kind=PartKind.TEXT, text=content))
        elif isinstance(content, list):
            # Anthropic-style block list passed through by the caller.
            for blk in content:
                if not isinstance(blk, dict):
                    continue
                btype = blk.get("type")
                if btype == "text":
                    parts.append(Part(kind=PartKind.TEXT, text=blk.get("text", "") or ""))
                elif btype == "tool_use":
                    parts.append(Part(
                        kind=PartKind.TOOL_CALL,
                        tool_call=ToolCall(
                            id=blk.get("id", "") or "",
                            name=blk.get("name", "") or "",
                            input_json=json.dumps(blk.get("input") or {}).encode("utf-8"),
                        ),
                    ))
                elif btype == "tool_result":
                    res_content = blk.get("content", "")
                    text_content = (
                        res_content if isinstance(res_content, str) else json.dumps(res_content)
                    )
                    parts.append(Part(
                        kind=PartKind.TOOL_RESULT,
                        tool_result=ToolResult(
                            tool_call_id=blk.get("tool_use_id", "") or "",
                            content=text_content[:50_000],
                            is_error=bool(blk.get("is_error", False)),
                        ),
                    ))

        if not parts:
            continue
        if role == "assistant":
            sigil_role = MessageRole.ASSISTANT
        elif role == "tool":
            sigil_role = MessageRole.TOOL
        elif all(p.kind == PartKind.TOOL_RESULT for p in parts):
            sigil_role = MessageRole.TOOL
        else:
            sigil_role = MessageRole.USER
        out.append(Message(role=sigil_role, parts=parts))

    return out


def _response_to_sigil_output(resp: CompleteResponse) -> Optional[Any]:
    """Build the single ASSISTANT Sigil Message representing the model output."""
    try:
        from sigil_sdk.models import (  # type: ignore
            Message,
            MessageRole,
            Part,
            PartKind,
            ToolCall,
        )
    except ImportError:
        return None

    parts: list[Any] = []
    if resp.content:
        parts.append(Part(kind=PartKind.TEXT, text=resp.content))
    for tc in resp.tool_calls or []:
        parts.append(Part(
            kind=PartKind.TOOL_CALL,
            tool_call=ToolCall(
                id=tc.get("id", "") or "",
                name=tc.get("name", "") or "",
                input_json=json.dumps(tc.get("input") or tc.get("arguments") or {}).encode("utf-8"),
            ),
        ))
    if not parts:
        return None
    return Message(role=MessageRole.ASSISTANT, parts=parts)


# ----------------------------------------------------------------------
# Generation event — the main one. One per /v1/complete.
# ----------------------------------------------------------------------
async def emit_generation_event(
    req: CompleteRequest,
    resp: CompleteResponse,
    span_id: str = "",
    trace_id: str = "",
    duration_ms: float | None = None,
    ttft_ms: float | None = None,
) -> None:
    """Emit one Sigil generation event for the AI Observability plugin.

    Best-effort: when the Sigil client isn't configured (or import fails),
    we just log the event JSON to stdout for backwards compatibility with
    the original Phase-1 stub — that line is what the legacy Loki dashboards
    parse.

    ``ttft_ms``: real measured time-to-first-token in milliseconds when the
    gateway streamed the response (Phase A: nc-chatbot only). When omitted
    or ``None``, ``set_first_token_at`` falls back to the 60%-of-duration
    heuristic.
    """
    # Pull trace context from the active OTel span when the caller didn't
    # pass explicit IDs — sigil events without trace_id can't be correlated
    # back to the Tempo trace, which breaks the AI plugin's drill-down.
    if not trace_id or not span_id:
        active_trace, active_span = _active_trace_context()
        trace_id = trace_id or active_trace
        span_id = span_id or active_span

    persona_id = (req.ai_o11y.get("persona_id") or "").strip()
    session_id = _derive_session_id(req)
    # Per-event agent identity. Pre-fix this was a static
    # "observibelity-llm-gateway" so the Sigil Agents page rolled every
    # generation under one agent. Now each specialist (nc-chatbot,
    # sb-router, sb-policy-finder, ...) shows up as its own row.
    agent_name = (req.specialist or "").strip() or _AGENT_NAME_FALLBACK
    # Email-shaped user identity for OTel user.id / enduser.id. Internal
    # persona_id stays as "u-*" everywhere else; only the outbound user
    # label gets the demo-realistic email so dashboards read like prod.
    from .persona_email import persona_to_email
    user_email = persona_to_email(persona_id, agent_name)

    # Always log a stdout JSON line — preserves the Phase-1 behaviour the
    # ai-obs-app-* dashboards rely on, and gives operators a paper trail
    # whether or not Sigil ingest is reachable. The shape is the OTel GenAI
    # semconv superset: canonical gen_ai.* + service.* + session.* attrs
    # the plugin reads, plus our ai_o11y.* mirrors for legacy dashboards.
    event: dict[str, Any] = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "trace_id": trace_id,
        "span_id": span_id,
        # --- service identity (resource attrs, mirrored on every event so
        # the plugin's namespace filter works even when ingest drops
        # resource metadata) ---
        "service.name": _SERVICE_NAME,
        "service.namespace": _SERVICE_NAMESPACE,
        "deployment.environment": os.environ.get("DEPLOYMENT_ENVIRONMENT", "demo"),
        # --- canonical gen_ai.* (OTel semconv) ---
        "gen_ai.system": resp.provider,
        "gen_ai.operation.name": "chat",
        # Per-event agent identity. gen_ai.agent.name is what Sigil's Agents
        # page groups on; gen_ai.agent.id is an alias some panels read.
        "gen_ai.agent.name": agent_name,
        "gen_ai.agent.id": agent_name,
        "gen_ai.request.model": req.model_override or resp.model,
        "gen_ai.response.model": resp.model,
        "gen_ai.request.max_tokens": int(req.max_tokens or 0),
        "gen_ai.usage.input_tokens": resp.usage.get("input_tokens", 0),
        "gen_ai.usage.output_tokens": resp.usage.get("output_tokens", 0),
        "gen_ai.usage.cached_input_tokens": resp.usage.get(
            "cache_read_input_tokens", 0
        ),
        "gen_ai.response.finish_reasons": [resp.finish_reason]
        if resp.finish_reason
        else [],
        # --- conversation grouping (Sigil's Conversations view) ---
        "session.id": session_id,
        "gen_ai.conversation.id": session_id,
        # --- user attribution (canonical aliases for the persona) ---
        # user.id is the demo-realistic email (acme employees / consumer
        # domains); ai_o11y.persona_id below stays as the internal slug.
        "user.id": user_email,
        "enduser.id": user_email,
        # Caller-supplied email (NeonCart shopper) overrides the derived
        # one — preserved here so explicit shopper emails still take
        # precedence over our persona→email map.
        **({"user.email": req.ai_o11y["email"]}
           if isinstance(req.ai_o11y.get("email"), str) and req.ai_o11y["email"]
           else {"user.email": user_email} if user_email else {}),
        # --- our demo-level fields, kept for the existing Loki dashboards ---
        "ai_o11y.usecase": req.ai_o11y.get("usecase"),
        "ai_o11y.persona_id": persona_id,
        "ai_o11y.specialist": agent_name,
        "traffic_origin": req.ai_o11y.get("traffic_origin", "continuous"),
    }

    # Cost: Sigil owns Anthropic/OpenAI/Google pricing — let it compute
    # those server-side. For Ollama/custom we emit our GPU-amortized
    # estimate so the plugin's Cost panel still has numbers for them.
    cost = resp.usage.get("cost_usd") or {}
    if _should_emit_cost(resp.provider):
        event["gen_ai.usage.cost.input_usd"] = cost.get("input_usd", 0.0)
        event["gen_ai.usage.cost.output_usd"] = cost.get("output_usd", 0.0)
        event["gen_ai.usage.cost.total_usd"] = cost.get("total_usd", 0.0)

    try:
        log.info("sigil generation: %s", json.dumps(event, default=str))
    except Exception:  # noqa: BLE001 — never let logging break the request.
        pass

    client = get_client()
    if client is None:
        return

    # Conversation id for the Sigil SDK == session id derived above.
    # This is what groups multi-turn chats from the same persona into a
    # single conversation row in the plugin's Conversations page.
    conversation_id = session_id
    conversation_title = _conversation_title(req)

    try:
        from sigil_sdk import GenerationStart, ModelRef  # type: ignore
        from sigil_sdk.models import GenerationMode, TokenUsage  # type: ignore
    except ImportError:
        return

    gen_id = uuid.uuid4().hex
    request_model = req.model_override or resp.model

    # Tags: anything that fits a small string→string map. The plugin
    # surfaces these on conversation-detail and supports filtering.
    # Canonical keys (service.namespace, session.id, user.id, gen_ai.agent.*,
    # etc.) are included so the AI Observability plugin's filter dropdowns
    # and default panels light up without per-deployment tweaking.
    tags: dict[str, str] = {
        "agent_operation": _AGENT_OPERATION_TAG,
        "specialist": agent_name,
        "traffic_origin": str(req.ai_o11y.get("traffic_origin", "continuous")),
        "service.name": _SERVICE_NAME,
        "service.namespace": _SERVICE_NAMESPACE,
        "deployment.environment": os.environ.get("DEPLOYMENT_ENVIRONMENT", "demo"),
        "session.id": session_id,
        "gen_ai.conversation.id": session_id,
        # Mirror agent identity into tags so panels that filter by tag
        # (rather than the top-level agent_name) also break down per
        # specialist.
        "gen_ai.agent.name": agent_name,
        "gen_ai.agent.id": agent_name,
        "ai_o11y.specialist": agent_name,
    }
    if usecase := (req.ai_o11y.get("usecase") or ""):
        tags["use_case"] = str(usecase)
        tags["ai_o11y.usecase"] = str(usecase)
    if persona_id:
        tags["persona_id"] = persona_id
        # user.id / enduser.id are the demo-realistic email; persona_id slug
        # stays in ai_o11y.persona_id for internal joins.
        tags["user.id"] = user_email or persona_id
        tags["enduser.id"] = user_email or persona_id
        tags["ai_o11y.persona_id"] = persona_id
    email_tag = req.ai_o11y.get("email") if req.ai_o11y else None
    if isinstance(email_tag, str) and email_tag.strip():
        tags["user.email"] = email_tag.strip()
    elif user_email:
        tags["user.email"] = user_email
    if trace_id:
        tags["trace_id"] = trace_id
    if span_id:
        tags["span_id"] = span_id

    # user_id == persona_id when available (the OTel canonical user.id).
    # Conversation id == derived session id, so the SDK's user filter and
    # the plugin's session-aware Conversations view agree on grouping.
    # agent_name = req.specialist (computed above) — drives the Sigil
    # Agents page; previously hardcoded to "observibelity-llm-gateway"
    # which collapsed every specialist into one row.
    start = GenerationStart(
        id=gen_id,
        model=ModelRef(provider=resp.provider or _DEFAULT_PROVIDER, name=request_model),
        conversation_id=conversation_id,
        conversation_title=conversation_title[:120],
        user_id=user_email or persona_id,
        agent_name=agent_name,
        agent_version=_agent_version(),
        # SYNC because the gateway proxies non-streaming Anthropic / Ollama
        # calls. Sigil still produces a generation record + token usage; the
        # TTFT histogram is only populated when we call set_first_token_at().
        mode=GenerationMode.SYNC,
        operation_name=_OPERATION,
        system_prompt=_extract_system_prompt(req.messages),
        max_tokens=int(req.max_tokens or 0),
        parent_generation_ids=[],
        tags=tags,
    )

    try:
        rec_ctx = client.start_generation(start)
    except Exception:  # noqa: BLE001
        log.exception("sigil start_generation failed")
        return

    try:
        with rec_ctx as rec:
            # TTFT: prefer the real wall-clock measurement provided by the
            # gateway when it actually streamed (Phase A: nc-chatbot). For
            # non-streaming specialists, fall back to 60%-of-duration so
            # the Performance dashboard's TTFT P95 panel keeps reading
            # something for the rest of the fleet.
            if ttft_ms is not None and ttft_ms > 0 and duration_ms is not None:
                try:
                    ttft_s = max(ttft_ms / 1000.0, 0.001)
                    rec.set_first_token_at(
                        datetime.fromtimestamp(
                            time.time() - (duration_ms / 1000.0) + ttft_s,
                            tz=timezone.utc,
                        )
                    )
                except Exception:  # noqa: BLE001
                    log.debug("sigil set_first_token_at skipped", exc_info=True)
            elif duration_ms is not None and duration_ms > 0:
                try:
                    approx_ttft_s = max(duration_ms * 0.6 / 1000.0, 0.001)
                    rec.set_first_token_at(
                        datetime.fromtimestamp(time.time() - (duration_ms / 1000.0)
                                                + approx_ttft_s, tz=timezone.utc)
                    )
                except Exception:  # noqa: BLE001
                    log.debug("sigil set_first_token_at skipped", exc_info=True)

            usage = TokenUsage(
                input_tokens=int(resp.usage.get("input_tokens", 0) or 0),
                output_tokens=int(resp.usage.get("output_tokens", 0) or 0),
                total_tokens=int(
                    (resp.usage.get("input_tokens", 0) or 0)
                    + (resp.usage.get("output_tokens", 0) or 0)
                ),
                cache_read_input_tokens=int(resp.usage.get("cache_read_input_tokens", 0) or 0),
                cache_write_input_tokens=0,
                reasoning_tokens=0,
                cache_creation_input_tokens=int(
                    resp.usage.get("cache_creation_input_tokens", 0) or 0
                ),
            )
            kwargs: dict[str, Any] = {
                "response_model": resp.model or request_model,
                "stop_reason": resp.finish_reason or "stop",
                "usage": usage,
            }
            sigil_input = _messages_to_sigil_input(req.messages)
            if sigil_input:
                kwargs["input"] = sigil_input
            sigil_output = _response_to_sigil_output(resp)
            if sigil_output is not None:
                kwargs["output"] = [sigil_output]
            try:
                rec.set_result(**kwargs)
            except Exception:  # noqa: BLE001
                log.exception("sigil set_result failed")
    except Exception:  # noqa: BLE001
        log.exception("sigil generation context failed")

    # Force a flush so events show up in the plugin quickly even for
    # low-traffic stretches (the SDK's batcher waits seconds by default).
    try:
        client.flush()
    except Exception:  # noqa: BLE001
        log.exception("sigil flush failed: id=%s", gen_id)

    # Stash the generation id on the response so callers/tests can
    # correlate. The CompleteResponse model doesn't have a dedicated
    # field for it, so we slip it into usage["generation_id"].
    try:
        resp.usage["generation_id"] = gen_id
    except Exception:  # noqa: BLE001
        pass


def _extract_system_prompt(messages: list[dict] | None) -> str:
    """Pull out the system prompt from the request messages (if any).

    The gateway accepts OpenAI-style messages; system content lives in
    messages[*] where role=="system". Concatenate all of them.
    """
    parts: list[str] = []
    for m in messages or []:
        if m.get("role") != "system":
            continue
        content = m.get("content")
        if isinstance(content, str) and content:
            parts.append(content)
        elif isinstance(content, list):
            for blk in content:
                if isinstance(blk, dict) and blk.get("type") == "text":
                    parts.append(blk.get("text", ""))
    return "\n\n".join(p for p in parts if p)


# ----------------------------------------------------------------------
# Tool-execution event — one per tool_use block in the model response.
# ----------------------------------------------------------------------
async def emit_tool_execution_event(
    *,
    specialist: str,
    tool_name: str,
    tool_call_id: str,
    arguments: Any,
    request_model: str,
    provider: str = _DEFAULT_PROVIDER,
    conversation_id: str = "",
    session_id: str = "",
    usecase: str = "",
    persona_id: str = "",
    result: Any = None,
    error: BaseException | None = None,
    duration_ms: float | None = None,
    trace_id: str = "",
    span_id: str = "",
) -> None:
    """Emit one Sigil tool-execution event for the AI plugin's Tools panel.

    The gateway emits this BEFORE the specialist actually invokes the tool —
    we know the tool_name + arguments from the model's response. ``result``
    and ``error`` stay empty in that mode; populated versions will arrive
    when specialists are instrumented end-to-end. The Tools panel still
    counts invocations, segments by tool name, and shows arguments, which
    is the bulk of its value.

    Carries the same canonical correlation envelope as
    :func:`emit_generation_event` so the Tools panel and Conversations
    view share session.id/user.id/trace_id/service identity.
    """
    # Pull trace context from the active span if the caller didn't pass it.
    if not trace_id or not span_id:
        active_trace, active_span = _active_trace_context()
        trace_id = trace_id or active_trace
        span_id = span_id or active_span

    # Always log a structured line for the stdout-based Loki dashboards so
    # tool events are traceable even when Sigil ingest is disabled. Mirrors
    # the canonical OTel GenAI tool-call attributes.
    try:
        arg_json = (
            arguments if isinstance(arguments, str) else json.dumps(arguments, default=str)
        )
    except Exception:  # noqa: BLE001
        arg_json = ""
    try:
        res_json = ""
        if result is not None:
            res_json = (
                result if isinstance(result, str) else json.dumps(result, default=str)
            )
            res_json = res_json[:50_000]
    except Exception:  # noqa: BLE001
        res_json = ""
    # For tool events, the Tools tab's "Top agents" panel groups on
    # gen_ai.agent.name — so we set it to the TOOL name (search_products,
    # get_inventory, kb_search, ...) and stash the calling specialist as
    # gen_ai.agent.parent so per-specialist breakdowns are still possible.
    tool_agent_name = (tool_name or "").strip() or "unknown-tool"
    parent_specialist = (specialist or "").strip() or _AGENT_NAME_FALLBACK
    from .persona_email import persona_to_email
    tool_user_email = persona_to_email(persona_id, parent_specialist)
    tool_event: dict[str, Any] = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "trace_id": trace_id,
        "span_id": span_id,
        "service.name": _SERVICE_NAME,
        "service.namespace": _SERVICE_NAMESPACE,
        "deployment.environment": os.environ.get("DEPLOYMENT_ENVIRONMENT", "demo"),
        "gen_ai.operation.name": "tool_use",
        "gen_ai.system": provider,
        "gen_ai.request.model": request_model,
        # Tool-level agent identity. Sigil's Tools tab "Top agents" panel
        # reads gen_ai.agent.name — setting it to the tool name is what
        # makes search_products / get_inventory / kb_search etc. show up
        # as distinct entries rather than a single "llm-gateway" row.
        "gen_ai.agent.name": tool_agent_name,
        "gen_ai.agent.id": tool_agent_name,
        # Parent specialist preserved for drill-down — which specialist
        # invoked this tool. Useful for "tools per specialist" breakdowns.
        "gen_ai.agent.parent": parent_specialist,
        "gen_ai.tool.name": tool_name,
        "gen_ai.tool.call.id": tool_call_id,
        "gen_ai.tool.arguments": arg_json,
        "gen_ai.tool.result": res_json,
        "gen_ai.tool.duration_ms": duration_ms,
        "session.id": session_id,
        "gen_ai.conversation.id": session_id,
        "user.id": tool_user_email or persona_id,
        "enduser.id": tool_user_email or persona_id,
        "ai_o11y.specialist": parent_specialist,
        "ai_o11y.usecase": usecase,
        "ai_o11y.persona_id": persona_id,
    }
    try:
        log.info("sigil tool: %s", json.dumps(tool_event, default=str))
    except Exception:  # noqa: BLE001 — telemetry must never break the request.
        pass

    client = get_client()
    if client is None:
        return

    try:
        from sigil_sdk import ToolExecutionStart  # type: ignore
    except ImportError:
        return

    # agent_name = the tool name (search_products, get_inventory, ...).
    # The Sigil Tools tab's "Top agents" panel groups on agent_name, so
    # setting it to the tool gives one row per tool in that panel; pre-fix
    # everything rolled up under "observibelity-llm-gateway".
    start = ToolExecutionStart(
        tool_name=tool_name,
        tool_call_id=tool_call_id or uuid.uuid4().hex,
        tool_type="function",
        conversation_id=conversation_id or session_id or uuid.uuid4().hex,
        agent_name=tool_agent_name,
        agent_version=_agent_version(),
        request_model=request_model,
        request_provider=provider,
        include_content=True,
    )
    try:
        rec_ctx = client.start_tool_execution(start)
    except Exception:  # noqa: BLE001
        log.exception("sigil start_tool_execution failed: tool=%s", tool_name)
        return

    try:
        with rec_ctx as rec:
            try:
                if error is not None:
                    rec.set_exec_error(error)
                else:
                    rec.set_result(arguments=arguments, result=result if result is not None else {})
            except Exception:  # noqa: BLE001
                log.exception("sigil tool set_result failed: tool=%s", tool_name)
    except Exception:  # noqa: BLE001
        log.exception("sigil tool_execution context failed: tool=%s", tool_name)

    try:
        client.flush()
    except Exception:  # noqa: BLE001
        log.debug("sigil flush after tool failed", exc_info=True)


# ----------------------------------------------------------------------
# Backwards-compatible helper retained for tests + legacy callers.
# ----------------------------------------------------------------------
def build_event(
    req: CompleteRequest,
    resp: CompleteResponse,
    span_id: str = "",
    trace_id: str = "",
) -> dict[str, Any]:
    """Build the legacy stdout-JSON Sigil event payload.

    Used by tests and any caller that wants the event dict without
    actually shipping it to Sigil. Mirrors the shape
    :func:`emit_generation_event` writes to stdout: canonical OTel GenAI
    attributes + service identity + session/user/trace correlation, with
    cost stripped for Sigil-licensed providers so we don't shadow the
    plugin's own pricing.
    """
    persona_id = (req.ai_o11y.get("persona_id") or "").strip()
    session_id = _derive_session_id(req)
    agent_name = (req.specialist or "").strip() or _AGENT_NAME_FALLBACK
    from .persona_email import persona_to_email
    user_email = persona_to_email(persona_id, agent_name)
    event: dict[str, Any] = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "trace_id": trace_id,
        "span_id": span_id,
        "service.name": _SERVICE_NAME,
        "service.namespace": _SERVICE_NAMESPACE,
        "deployment.environment": os.environ.get("DEPLOYMENT_ENVIRONMENT", "demo"),
        "gen_ai.system": resp.provider,
        "gen_ai.operation.name": "chat",
        # Per-event agent identity — see emit_generation_event for context.
        "gen_ai.agent.name": agent_name,
        "gen_ai.agent.id": agent_name,
        "gen_ai.request.model": req.model_override or resp.model,
        "gen_ai.response.model": resp.model,
        "gen_ai.request.max_tokens": int(req.max_tokens or 0),
        "gen_ai.usage.input_tokens": resp.usage.get("input_tokens", 0),
        "gen_ai.usage.output_tokens": resp.usage.get("output_tokens", 0),
        "gen_ai.usage.cached_input_tokens": resp.usage.get("cache_read_input_tokens", 0),
        "gen_ai.response.finish_reason": resp.finish_reason,
        "gen_ai.response.finish_reasons": [resp.finish_reason] if resp.finish_reason else [],
        "session.id": session_id,
        "gen_ai.conversation.id": session_id,
        "user.id": user_email or persona_id,
        "enduser.id": user_email or persona_id,
        "ai_o11y.usecase": req.ai_o11y.get("usecase"),
        "ai_o11y.persona_id": persona_id,
        "ai_o11y.specialist": agent_name,
        "traffic_origin": req.ai_o11y.get("traffic_origin", "continuous"),
        "messages": req.messages[-1:],
        "completion": resp.content,
        "tool_calls": resp.tool_calls,
    }
    cost = resp.usage.get("cost_usd") or {}
    if _should_emit_cost(resp.provider):
        event["gen_ai.usage.cost.input_usd"] = cost.get("input_usd", 0.0)
        event["gen_ai.usage.cost.output_usd"] = cost.get("output_usd", 0.0)
        event["gen_ai.usage.cost.total_usd"] = cost.get("total_usd", 0.0)
    return event
