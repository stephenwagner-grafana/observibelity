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

import json
import logging
import os
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Iterator, Optional

from .providers.base import CompleteRequest, CompleteResponse

log = logging.getLogger(__name__)

_AGENT_NAME = "observibelity-llm-gateway"
_DEFAULT_PROVIDER = "anthropic"
# operation_name=streamText is the magic value that makes Sigil's SDK
# auto-emit the gen_ai.client.time_to_first_token histogram on flush —
# the Sigil plugin's TTFT panel reads that series.
_OPERATION = "streamText"
_AGENT_OPERATION_TAG = "gateway.complete"
_TOOL_OPERATION = "gateway.tool_call"

_client: Optional[Any] = None
_initialized = False


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
    return ClientConfig(generation_export=export)


def init_sigil(service_name: str = "llm-gateway") -> None:
    """Lazily construct the Sigil client on first use.

    Idempotent + best-effort: the gateway must boot even when Sigil is
    unreachable, so failures here downgrade to a logged warning. The
    ``service_name`` arg is accepted for API symmetry with the original
    stub but the underlying agent name is fixed (``observibelity-llm-gateway``)
    so the plugin's Conversations page groups every gateway-emitted
    generation under one agent.
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
) -> None:
    """Emit one Sigil generation event for the AI Observability plugin.

    Best-effort: when the Sigil client isn't configured (or import fails),
    we just log the event JSON to stdout for backwards compatibility with
    the original Phase-1 stub — that line is what the legacy Loki dashboards
    parse.
    """
    # Always log a stdout JSON line — preserves the Phase-1 behaviour the
    # ai-obs-app-* dashboards rely on, and gives operators a paper trail
    # whether or not Sigil ingest is reachable.
    cost = resp.usage.get("cost_usd") or {}
    event = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "trace_id": trace_id,
        "span_id": span_id,
        "gen_ai.system": resp.provider,
        "gen_ai.request.model": req.model_override or resp.model,
        "gen_ai.response.model": resp.model,
        "gen_ai.usage.input_tokens": resp.usage.get("input_tokens", 0),
        "gen_ai.usage.output_tokens": resp.usage.get("output_tokens", 0),
        "gen_ai.usage.cost.input_usd": cost.get("input_usd", 0.0),
        "gen_ai.usage.cost.output_usd": cost.get("output_usd", 0.0),
        "gen_ai.usage.cost.total_usd": cost.get("total_usd", 0.0),
        "gen_ai.response.finish_reason": resp.finish_reason,
        "ai_o11y.usecase": req.ai_o11y.get("usecase"),
        "ai_o11y.persona_id": req.ai_o11y.get("persona_id"),
        "ai_o11y.specialist": req.specialist,
        "traffic_origin": req.ai_o11y.get("traffic_origin", "continuous"),
    }
    try:
        log.info("sigil generation: %s", json.dumps(event, default=str))
    except Exception:  # noqa: BLE001 — never let logging break the request.
        pass

    client = get_client()
    if client is None:
        return

    # Use persona_id as the conversation_id when present so multi-turn
    # interactions from the same loadgen persona group under one chat in
    # the plugin's Conversations page. Fall back to a one-shot UUID so
    # every /v1/complete still appears even without persona context.
    persona_id = (req.ai_o11y.get("persona_id") or "").strip()
    conversation_id = persona_id or uuid.uuid4().hex
    conversation_title = (
        f"{req.specialist} / {req.ai_o11y.get('usecase') or 'adhoc'}"
    )

    try:
        from sigil_sdk import GenerationStart, ModelRef  # type: ignore
        from sigil_sdk.models import GenerationMode, TokenUsage  # type: ignore
    except ImportError:
        return

    gen_id = uuid.uuid4().hex
    request_model = req.model_override or resp.model

    # Tags: anything that fits a small string→string map. The plugin
    # surfaces these on conversation-detail and supports filtering.
    tags: dict[str, str] = {
        "agent_operation": _AGENT_OPERATION_TAG,
        "specialist": req.specialist,
        "traffic_origin": str(req.ai_o11y.get("traffic_origin", "continuous")),
    }
    if usecase := (req.ai_o11y.get("usecase") or ""):
        tags["use_case"] = str(usecase)
    if persona_id:
        tags["persona_id"] = persona_id
    if trace_id:
        tags["trace_id"] = trace_id

    start = GenerationStart(
        id=gen_id,
        model=ModelRef(provider=resp.provider or _DEFAULT_PROVIDER, name=request_model),
        conversation_id=conversation_id,
        conversation_title=conversation_title[:120],
        user_id=persona_id,
        agent_name=_AGENT_NAME,
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
            # Approximate TTFT: we don't stream upstream yet, so feed the
            # plugin's TTFT histogram with a best-effort number — 60% of
            # total duration for non-streaming providers — which is what
            # users would observe end-to-end. Real per-token TTFT becomes
            # accurate when the providers move to streaming mode.
            if duration_ms is not None and duration_ms > 0:
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
    usecase: str = "",
    persona_id: str = "",
    result: Any = None,
    error: BaseException | None = None,
    duration_ms: float | None = None,
) -> None:
    """Emit one Sigil tool-execution event for the AI plugin's Tools panel.

    The gateway emits this BEFORE the specialist actually invokes the tool —
    we know the tool_name + arguments from the model's response. ``result``
    and ``error`` stay empty in that mode; populated versions will arrive
    when specialists are instrumented end-to-end. The Tools panel still
    counts invocations, segments by tool name, and shows arguments, which
    is the bulk of its value.
    """
    client = get_client()
    if client is None:
        return

    try:
        from sigil_sdk import ToolExecutionStart  # type: ignore
    except ImportError:
        return

    start = ToolExecutionStart(
        tool_name=tool_name,
        tool_call_id=tool_call_id or uuid.uuid4().hex,
        tool_type="function",
        conversation_id=conversation_id or uuid.uuid4().hex,
        agent_name=_AGENT_NAME,
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

    _ = duration_ms  # accepted for caller symmetry; SDK derives from span time
    _ = specialist
    _ = usecase
    _ = persona_id
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

    The dashboard-shaped fields here are still parsed by the AI o11y
    Loki dashboards, so we keep them stable. Real Sigil ingest goes
    through ``emit_generation_event``.
    """
    cost = resp.usage.get("cost_usd") or {}
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "trace_id": trace_id,
        "span_id": span_id,
        "gen_ai.system": resp.provider,
        "gen_ai.request.model": req.model_override or resp.model,
        "gen_ai.response.model": resp.model,
        "gen_ai.usage.input_tokens": resp.usage.get("input_tokens", 0),
        "gen_ai.usage.output_tokens": resp.usage.get("output_tokens", 0),
        "gen_ai.usage.cost.input_usd": cost.get("input_usd", 0.0),
        "gen_ai.usage.cost.output_usd": cost.get("output_usd", 0.0),
        "gen_ai.usage.cost.total_usd": cost.get("total_usd", 0.0),
        "gen_ai.response.finish_reason": resp.finish_reason,
        "ai_o11y.usecase": req.ai_o11y.get("usecase"),
        "ai_o11y.persona_id": req.ai_o11y.get("persona_id"),
        "ai_o11y.specialist": req.specialist,
        "traffic_origin": req.ai_o11y.get("traffic_origin", "continuous"),
        "messages": req.messages[-1:],
        "completion": resp.content,
        "tool_calls": resp.tool_calls,
    }
