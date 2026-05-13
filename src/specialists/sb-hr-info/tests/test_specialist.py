"""Mocked tests for sb-hr-info."""
from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from app.specialist import SbHrInfo
from specialist_base import SpecialistRequest


def test_metadata() -> None:
    spec = SbHrInfo()
    assert spec.NAME == "sb-hr-info"
    assert spec.TOOL_ALLOWLIST == ["kb_search", "get_employee"]


@pytest.mark.asyncio
async def test_handle_simple_response() -> None:
    spec = SbHrInfo()
    spec.call_gateway = AsyncMock(  # type: ignore[method-assign]
        return_value={"content": "PTO is 20 days.", "tool_calls": []}
    )
    resp = await spec.handle(SpecialistRequest(message="how much PTO do I get"))
    assert "20 days" in resp.reply
