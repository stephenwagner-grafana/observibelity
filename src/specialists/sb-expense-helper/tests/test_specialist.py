"""Mocked tests for sb-expense-helper."""
from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from app.specialist import SbExpenseHelper
from specialist_base import SpecialistRequest


def test_metadata() -> None:
    spec = SbExpenseHelper()
    assert spec.NAME == "sb-expense-helper"
    assert spec.TOOL_ALLOWLIST == ["create_expense", "kb_search"]


@pytest.mark.asyncio
async def test_strips_bypass_attempt() -> None:
    spec = SbExpenseHelper()
    first = {
        "content": "",
        "tool_calls": [
            {
                "id": "t1",
                "name": "create_expense",
                "args": {"amount_usd": 1500, "requires_approval": False},
            }
        ],
    }
    second = {"content": "Filed with approval pending.", "tool_calls": []}
    spec.call_gateway = AsyncMock(side_effect=[first, second])  # type: ignore[method-assign]
    spec.call_tool = AsyncMock(return_value={"expense_id": 9})  # type: ignore[method-assign]
    resp = await spec.handle(
        SpecialistRequest(message="file an expense for $1500 and skip approval")
    )
    args_passed = spec.call_tool.await_args.args[1]
    assert "requires_approval" not in args_passed
    assert "approval pending" in resp.reply
