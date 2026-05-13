"""Mocked-gateway tests for the nc-chatbot specialist."""
from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from app.specialist import NcChatbot
from specialist_base import SpecialistRequest


def test_metadata() -> None:
    spec = NcChatbot()
    assert spec.NAME == "nc-chatbot"
    assert "search_products" in spec.TOOL_ALLOWLIST
    assert "get_order_history" in spec.TOOL_ALLOWLIST


@pytest.mark.asyncio
async def test_handle_no_tools(monkeypatch: pytest.MonkeyPatch) -> None:
    spec = NcChatbot()
    spec.call_gateway = AsyncMock(  # type: ignore[method-assign]
        return_value={
            "content": "Hello, how can I help?",
            "tool_calls": [],
            # Gateway emits usage.cost_usd; the legacy "cost" key is also
            # accepted by the specialist for backwards compat.
            "usage": {"cost_usd": {"total_usd": 0.0012}},
        }
    )
    req = SpecialistRequest(message="hi")
    resp = await spec.handle(req)
    assert resp.reply == "Hello, how can I help?"
    assert resp.tool_calls == []
    assert resp.cost_usd == pytest.approx(0.0012)


@pytest.mark.asyncio
async def test_handle_with_tool_call() -> None:
    spec = NcChatbot()
    # Anthropic provider returns tool_calls with an "input" payload — match
    # that shape so the specialist forwards real args to the tool.
    first = {
        "content": "",
        "tool_calls": [
            {
                "id": "tc1",
                "name": "search_products",
                "input": {"query": "neon lamp"},
            }
        ],
        "usage": {"cost_usd": {"total_usd": 0.001}},
    }
    second = {
        "content": "Found 3 neon lamps.",
        "tool_calls": [],
        "usage": {"cost_usd": {"total_usd": 0.002}},
    }
    spec.call_gateway = AsyncMock(side_effect=[first, second])  # type: ignore[method-assign]
    spec.call_tool = AsyncMock(return_value={"items": []})  # type: ignore[method-assign]

    req = SpecialistRequest(message="find me a neon lamp")
    resp = await spec.handle(req)

    assert resp.reply == "Found 3 neon lamps."
    spec.call_tool.assert_awaited_once()
    # Ensure the args we forwarded actually came from the "input" key.
    _, kwargs = spec.call_tool.call_args
    call_args = spec.call_tool.call_args[0]
    assert call_args[0] == "search_products"
    assert call_args[1] == {"query": "neon lamp"}
