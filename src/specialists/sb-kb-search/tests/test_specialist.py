"""Mocked tests for sb-kb-search."""
from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from app.specialist import SbKbSearch
from specialist_base import SpecialistRequest


def test_metadata() -> None:
    spec = SbKbSearch()
    assert spec.NAME == "sb-kb-search"
    assert spec.TOOL_ALLOWLIST == ["kb_search"]


@pytest.mark.asyncio
async def test_handle_calls_kb_search_then_summarises() -> None:
    spec = SbKbSearch()
    spec.call_tool = AsyncMock(  # type: ignore[method-assign]
        return_value={"items": [{"title": "VPN reset", "body": "..."}]}
    )
    spec.call_gateway = AsyncMock(  # type: ignore[method-assign]
        return_value={"content": "See VPN reset.", "tool_calls": []}
    )
    resp = await spec.handle(SpecialistRequest(message="how to reset VPN"))
    spec.call_tool.assert_awaited_once()
    call_args = spec.call_tool.await_args
    assert call_args.args[0] == "kb_search"
    assert call_args.args[1]["query"] == "how to reset VPN"
    assert "VPN reset" in resp.reply
    assert resp.tool_calls and resp.tool_calls[0]["name"] == "kb_search"
