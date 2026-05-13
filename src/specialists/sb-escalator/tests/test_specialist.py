"""Mocked tests for sb-escalator."""
from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from app.specialist import SbEscalator
from specialist_base import SpecialistRequest


def test_metadata() -> None:
    spec = SbEscalator()
    assert spec.NAME == "sb-escalator"
    assert spec.TOOL_ALLOWLIST == ["create_ticket"]


@pytest.mark.asyncio
async def test_files_ticket_and_replies() -> None:
    spec = SbEscalator()
    spec.call_tool = AsyncMock(return_value={"ticket_id": 42})  # type: ignore[method-assign]
    spec.call_gateway = AsyncMock(  # type: ignore[method-assign]
        return_value={
            "content": "Filed escalation #42. A human will follow up.",
            "tool_calls": [],
        }
    )
    resp = await spec.handle(SpecialistRequest(message="please escalate this to a human"))
    spec.call_tool.assert_awaited_once()
    call_args = spec.call_tool.await_args
    assert call_args.args[0] == "create_ticket"
    assert call_args.args[1]["category"] == "escalation"
    assert "#42" in resp.reply
