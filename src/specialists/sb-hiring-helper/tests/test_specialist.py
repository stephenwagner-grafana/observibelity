"""Mocked tests for sb-hiring-helper."""
from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from app.specialist import SbHiringHelper
from specialist_base import SpecialistRequest


def test_metadata() -> None:
    spec = SbHiringHelper()
    assert spec.NAME == "sb-hiring-helper"
    assert spec.TOOL_ALLOWLIST == ["kb_search"]


@pytest.mark.asyncio
async def test_redacts_protected_class_output() -> None:
    spec = SbHiringHelper()
    spec.call_gateway = AsyncMock(  # type: ignore[method-assign]
        return_value={
            "content": "Prefer the male candidate who is younger.",
            "tool_calls": [],
        }
    )
    resp = await spec.handle(SpecialistRequest(message="who is the best candidate"))
    assert "male" not in resp.reply.lower()
    assert "younger" in resp.reply or "[redacted]" in resp.reply
    last_tc = resp.tool_calls[-1]
    assert last_tc["name"] == "_hiring_filter"
    assert last_tc["args"]["flagged_output"] is True


@pytest.mark.asyncio
async def test_normal_query_passes_through() -> None:
    spec = SbHiringHelper()
    spec.call_gateway = AsyncMock(  # type: ignore[method-assign]
        return_value={"content": "Use the standard L4 rubric.", "tool_calls": []}
    )
    resp = await spec.handle(SpecialistRequest(message="what's the L4 interview loop"))
    assert "L4" in resp.reply
