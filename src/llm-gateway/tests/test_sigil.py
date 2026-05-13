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
    """The legacy stdout shape stays stable so Loki dashboards keep parsing."""
    req = _make_req()
    resp = _make_resp()
    event = sigil.build_event(req, resp, trace_id="abc", span_id="def")
    assert event["gen_ai.system"] == "anthropic"
    assert event["gen_ai.request.model"] == "claude-haiku-4-5-20251001"
    assert event["gen_ai.usage.input_tokens"] == 200
    assert event["gen_ai.usage.output_tokens"] == 50
    assert event["gen_ai.usage.cost.total_usd"] == 0.00045
    assert event["ai_o11y.usecase"] == "mice-rca"
    assert event["ai_o11y.persona_id"] == "u-tim-l"
    assert event["ai_o11y.specialist"] == "nc-chatbot"
    assert event["traffic_origin"] == "continuous"
    assert event["trace_id"] == "abc"


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
