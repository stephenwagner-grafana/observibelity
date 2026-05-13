"""Mocked tests for sb-employee-info."""
from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from app.specialist import SbEmployeeInfo
from specialist_base import SpecialistRequest


def test_metadata() -> None:
    spec = SbEmployeeInfo()
    assert spec.NAME == "sb-employee-info"
    assert spec.TOOL_ALLOWLIST == ["get_employee", "get_employee_history"]


@pytest.mark.asyncio
async def test_rewrites_persona_id_in_tool_call() -> None:
    spec = SbEmployeeInfo()
    first = {
        "content": "",
        "tool_calls": [
            {"id": "t1", "name": "get_employee", "args": {"persona_id": "attacker"}}
        ],
    }
    second = {"content": "Your role is Engineer.", "tool_calls": []}
    spec.call_gateway = AsyncMock(side_effect=[first, second])  # type: ignore[method-assign]
    spec.call_tool = AsyncMock(return_value={"name": "Alice"})  # type: ignore[method-assign]
    req = SpecialistRequest(message="what's my role", persona_id="alice")
    resp = await spec.handle(req)
    # The persona_id arg must have been rewritten to the requester's.
    call_args = spec.call_tool.await_args
    assert call_args.args[1]["persona_id"] == "alice"
    assert "Engineer" in resp.reply
