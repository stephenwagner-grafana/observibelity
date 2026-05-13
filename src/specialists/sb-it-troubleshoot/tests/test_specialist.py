"""Mocked tests for sb-it-troubleshoot."""
from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from app.specialist import SbItTroubleshoot
from specialist_base import SpecialistRequest


def test_metadata() -> None:
    spec = SbItTroubleshoot()
    assert spec.NAME == "sb-it-troubleshoot"
    for t in ("kb_search", "reset_password", "request_access"):
        assert t in spec.TOOL_ALLOWLIST


@pytest.mark.asyncio
async def test_handle_consults_kb_then_replies() -> None:
    spec = SbItTroubleshoot()
    spec.call_gateway = AsyncMock(  # type: ignore[method-assign]
        return_value={"content": "Try connecting to GlobalProtect.", "tool_calls": []}
    )
    resp = await spec.handle(SpecialistRequest(message="VPN is offline"))
    assert "GlobalProtect" in resp.reply
