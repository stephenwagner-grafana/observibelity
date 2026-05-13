"""Mocked tests for sb-ticket-helper."""
from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from app.specialist import SbTicketHelper
from specialist_base import SpecialistRequest


def test_metadata() -> None:
    spec = SbTicketHelper()
    assert spec.NAME == "sb-ticket-helper"
    for t in ("list_tickets", "get_ticket", "create_ticket", "update_ticket"):
        assert t in spec.TOOL_ALLOWLIST


@pytest.mark.asyncio
async def test_handle_files_a_ticket() -> None:
    spec = SbTicketHelper()
    first = {
        "content": "",
        "tool_calls": [
            {"id": "t1", "name": "create_ticket", "args": {"subject": "VPN broken"}}
        ],
    }
    second = {"content": "Filed ticket #7.", "tool_calls": [], "usage": {"cost": {"total_usd": 0.001}}}
    spec.call_gateway = AsyncMock(side_effect=[first, second])  # type: ignore[method-assign]
    spec.call_tool = AsyncMock(return_value={"ticket_id": 7})  # type: ignore[method-assign]
    resp = await spec.handle(SpecialistRequest(message="My VPN is broken, file a ticket"))
    assert "Filed ticket" in resp.reply
    spec.call_tool.assert_awaited_once()
