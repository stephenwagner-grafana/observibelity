"""Mocked tests for sb-security-handler."""
from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from app.specialist import SbSecurityHandler
from specialist_base import SpecialistRequest


def test_metadata() -> None:
    spec = SbSecurityHandler()
    assert spec.NAME == "sb-security-handler"
    assert spec.TOOL_ALLOWLIST == ["kb_search"]


@pytest.mark.asyncio
async def test_redacts_confidential_phrase() -> None:
    spec = SbSecurityHandler()
    spec.call_gateway = AsyncMock(  # type: ignore[method-assign]
        return_value={
            "content": "The merger with Initech finalises next week.",
            "tool_calls": [],
        }
    )
    resp = await spec.handle(SpecialistRequest(message="any news on the merger?"))
    assert "merger" not in resp.reply.lower()
    assert "[redacted]" in resp.reply


@pytest.mark.asyncio
async def test_normal_query_passes_through() -> None:
    spec = SbSecurityHandler()
    spec.call_gateway = AsyncMock(  # type: ignore[method-assign]
        return_value={"content": "Always use MFA.", "tool_calls": []}
    )
    resp = await spec.handle(SpecialistRequest(message="how do I enable MFA"))
    assert "MFA" in resp.reply
