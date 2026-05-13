"""Tests for the Sigil generation-event emitter.

Verifies the module:
  * builds the legacy stdout payload exactly as Phase 1 did (so the AI o11y
    Loki dashboards keep parsing),
  * no-ops cleanly when SIGIL_GENERATION_EXPORT_ENDPOINT is unset (the
    fresh-deploy case before the wizard fills in credentials),
  * accepts an unconfigured environment without raising.

We do NOT import sigil_sdk in CI — the module must work without it for
local dev + tests. Real ingest is exercised via the e2e smoke run.
"""
from __future__ import annotations

import asyncio
import os

import pytest

from app import sigil
from app.providers.base import CompleteRequest, CompleteResponse


def _make_req() -> CompleteRequest:
    return CompleteRequest(
        specialist="nc-chatbot",
        messages=[
            {"role": "system", "content": "You are a helpful shopping assistant."},
            {"role": "user", "content": "do you have mice?"},
        ],
        max_tokens=128,
        ai_o11y={"usecase": "mice-rca", "persona_id": "u-tim-l", "traffic_origin": "continuous"},
    )


def _make_resp(with_tools: bool = False) -> CompleteResponse:
    return CompleteResponse(
        content="We sell several mice — here are three popular options.",
        tool_calls=(
            [{"id": "toolu_xyz", "name": "search_products", "input": {"query": "mice"}}]
            if with_tools
            else []
        ),
        finish_reason="tool_use" if with_tools else "stop",
        usage={
            "input_tokens": 200,
            "output_tokens": 50,
            "cost_usd": {"input_usd": 0.0002, "output_usd": 0.00025, "total_usd": 0.00045},
        },
        provider="anthropic",
        model="claude-haiku-4-5-20251001",
    )


def test_build_event_returns_canonical_payload():
    """Stdout shape carries canonical OTel GenAI attrs + session/user.

    Sigil owns Anthropic pricing — events for Sigil-licensed providers
    must NOT carry gen_ai.usage.cost.* so the plugin doesn't double-count
    against its own pricing table.
    """
    req = _make_req()
    resp = _make_resp()
    event = sigil.build_event(req, resp, trace_id="abc", span_id="def")
    # Canonical gen_ai.* attrs.
    assert event["gen_ai.system"] == "anthropic"
    assert event["gen_ai.operation.name"] == "chat"
    assert event["gen_ai.request.model"] == "claude-haiku-4-5-20251001"
    assert event["gen_ai.response.model"] == "claude-haiku-4-5-20251001"
    assert event["gen_ai.usage.input_tokens"] == 200
    assert event["gen_ai.usage.output_tokens"] == 50
    assert event["gen_ai.response.finish_reasons"] == ["stop"]
    # Cost is stripped for Anthropic — Sigil computes it from its own table.
    assert "gen_ai.usage.cost.total_usd" not in event
    assert "gen_ai.usage.cost.input_usd" not in event
    assert "gen_ai.usage.cost.output_usd" not in event
    # Service identity mirrored onto every event so the plugin's namespace
    # filter works even when ingest drops resource metadata.
    assert event["service.name"] == "llm-gateway"
    assert event["service.namespace"] == "observibelity"
    assert "deployment.environment" in event
    # Conversation grouping + user attribution.
    assert event["session.id"] == event["gen_ai.conversation.id"]
    assert event["session.id"]  # non-empty
    assert event["user.id"] == "u-tim-l"
    assert event["enduser.id"] == "u-tim-l"
    # Legacy ai_o11y.* mirrors preserved.
    assert event["ai_o11y.usecase"] == "mice-rca"
    assert event["ai_o11y.persona_id"] == "u-tim-l"
    assert event["ai_o11y.specialist"] == "nc-chatbot"
    assert event["traffic_origin"] == "continuous"
    assert event["trace_id"] == "abc"


def test_build_event_keeps_cost_for_ollama():
    """Ollama isn't in Sigil's licensed pricing — we must still emit cost."""
    req = _make_req()
    resp = CompleteResponse(
        content="ok",
        tool_calls=[],
        finish_reason="stop",
        usage={
            "input_tokens": 100,
            "output_tokens": 50,
            "cost_usd": {"input_usd": 1e-5, "output_usd": 2e-5, "total_usd": 3e-5},
        },
        provider="ollama",
        model="llama3.1:8b",
    )
    event = sigil.build_event(req, resp)
    assert event["gen_ai.usage.cost.total_usd"] == 3e-5
    assert event["gen_ai.usage.cost.input_usd"] == 1e-5
    assert event["gen_ai.usage.cost.output_usd"] == 2e-5


def test_should_emit_cost_strips_only_licensed_providers():
    """The cost-strip predicate must cover Anthropic + OpenAI + Google."""
    assert sigil._should_emit_cost("ollama") is True
    assert sigil._should_emit_cost("custom-local") is True
    assert sigil._should_emit_cost("Anthropic") is False
    assert sigil._should_emit_cost("ANTHROPIC") is False
    assert sigil._should_emit_cost("openai") is False
    assert sigil._should_emit_cost("google") is False
    assert sigil._should_emit_cost("gemini") is False
    assert sigil._should_emit_cost("cohere") is False
    assert sigil._should_emit_cost(None) is True  # safety default: emit


def test_derive_session_id_groups_persona_within_hour():
    """Two requests from the same persona in the same UTC hour share a session."""
    req_a = _make_req()
    req_b = _make_req()
    assert sigil._derive_session_id(req_a) == sigil._derive_session_id(req_b)
    # Different persona -> different session.
    req_c = CompleteRequest(
        specialist="nc-chatbot",
        messages=[{"role": "user", "content": "hi"}],
        ai_o11y={"persona_id": "u-other"},
    )
    assert sigil._derive_session_id(req_a) != sigil._derive_session_id(req_c)
    # Unknown persona -> deterministic anonymous bucket (non-empty).
    req_anon = CompleteRequest(
        specialist="nc-chatbot",
        messages=[{"role": "user", "content": "hi"}],
        ai_o11y={},
    )
    sid = sigil._derive_session_id(req_anon)
    assert sid and isinstance(sid, str) and len(sid) == 16


def test_emit_generation_event_noops_when_sigil_unconfigured(monkeypatch):
    """No SIGIL_* env vars → the helper must run + return without raising."""
    monkeypatch.delenv("SIGIL_GENERATION_EXPORT_ENDPOINT", raising=False)
    monkeypatch.delenv("SIGIL_BASIC_USER", raising=False)
    monkeypatch.delenv("SIGIL_BASIC_PASSWORD", raising=False)
    # Reset the module's lazy-init state so it re-reads env on next get_client().
    sigil._initialized = False
    sigil._client = None

    req = _make_req()
    resp = _make_resp(with_tools=True)
    asyncio.run(sigil.emit_generation_event(req, resp, duration_ms=123.4))


def test_emit_tool_execution_event_noops_when_sigil_unconfigured(monkeypatch):
    monkeypatch.delenv("SIGIL_GENERATION_EXPORT_ENDPOINT", raising=False)
    sigil._initialized = False
    sigil._client = None

    asyncio.run(
        sigil.emit_tool_execution_event(
            specialist="nc-chatbot",
            tool_name="search_products",
            tool_call_id="toolu_xyz",
            arguments={"query": "mice"},
            request_model="claude-haiku-4-5-20251001",
        )
    )


def test_init_sigil_is_idempotent(monkeypatch):
    """Calling init_sigil multiple times must not raise or rebuild the client."""
    monkeypatch.delenv("SIGIL_GENERATION_EXPORT_ENDPOINT", raising=False)
    sigil._initialized = False
    sigil._client = None
    sigil.init_sigil("llm-gateway")
    sigil.init_sigil("llm-gateway")  # second call should be a no-op


def test_extract_system_prompt():
    out = sigil._extract_system_prompt(
        [
            {"role": "system", "content": "Be terse."},
            {"role": "user", "content": "hi"},
            {"role": "system", "content": [{"type": "text", "text": "And kind."}]},
        ]
    )
    assert "Be terse." in out
    assert "And kind." in out
