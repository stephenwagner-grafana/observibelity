"""Mocked-gateway tests for sb-policy-finder."""
from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from app.specialist import SbPolicyFinder
from specialist_base import SpecialistRequest


def test_metadata() -> None:
    spec = SbPolicyFinder()
    assert spec.NAME == "sb-policy-finder"
    assert "kb_search" in spec.TOOL_ALLOWLIST
    assert "get_employee" in spec.TOOL_ALLOWLIST


@pytest.mark.asyncio
async def test_handle_no_tools() -> None:
    spec = SbPolicyFinder()
    spec.call_gateway = AsyncMock(  # type: ignore[method-assign]
        return_value={"content": "Policy 12 applies.", "tool_calls": []}
    )
    resp = await spec.handle(SpecialistRequest(message="vacation policy?"))
    assert "Policy 12" in resp.reply
