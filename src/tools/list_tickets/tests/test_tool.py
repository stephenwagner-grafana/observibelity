"""Tests for the list_tickets tool."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.tool import ListTickets, ListTicketsArgs, ListTicketsResult


class _StubResult:
    def __init__(self, rows): self._rows = rows
    def all(self): return self._rows


class _StubRow:
    def __init__(self, **kw): self.__dict__.update(kw)


class _StubSession:
    def __init__(self, rows): self._rows = rows; self.last_params = None
    async def execute(self, stmt, params): self.last_params = params; return _StubResult(self._rows)


def test_knobs():
    assert ListTickets.NAME == "list_tickets"
    assert ListTickets.BACKING_TABLES == ["tickets"]
    assert ListTickets.SIDE_EFFECT is False


@pytest.mark.asyncio
async def test_execute_returns_rows():
    now = datetime.now(tz=timezone.utc)
    rows = [_StubRow(id=1, subject="VPN", status="open", category="it", created_at=now)]
    sess = _StubSession(rows)
    tool = ListTickets.__new__(ListTickets)
    res = await tool.execute(ListTicketsArgs(persona_id="alice"), sess)
    assert isinstance(res, ListTicketsResult)
    assert len(res.tickets) == 1
    assert res.tickets[0].subject == "VPN"
