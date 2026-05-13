"""Tests for the get_ticket tool."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.tool import GetTicket, GetTicketArgs, GetTicketResult


class _StubResult:
    def __init__(self, row): self._row = row
    def one_or_none(self): return self._row


class _StubRow:
    def __init__(self, **kw): self.__dict__.update(kw)


class _StubSession:
    def __init__(self, row): self._row = row; self.last_params = None
    async def execute(self, stmt, params): self.last_params = params; return _StubResult(self._row)


def test_knobs():
    assert GetTicket.NAME == "get_ticket"
    assert GetTicket.BACKING_TABLES == ["tickets"]


@pytest.mark.asyncio
async def test_execute_found():
    now = datetime.now(tz=timezone.utc)
    # Schema fields per 0006_tickets.py: ticket_number, persona_id (string),
    # priority — older drafts of the stub used non-existent columns.
    row = _StubRow(
        id=7, ticket_number="T-7", persona_id="u-tim-l", subject="VPN",
        body="...", status="open", priority="medium", created_at=now,
    )
    sess = _StubSession(row)
    tool = GetTicket.__new__(GetTicket)
    res = await tool.execute(GetTicketArgs(ticket_id=7), sess)
    assert isinstance(res, GetTicketResult)
    assert res.id == 7
    assert res.ticket_number == "T-7"
    assert res.persona_id == "u-tim-l"
    # ``category`` is the legacy alias for priority.
    assert res.category == "medium"


@pytest.mark.asyncio
async def test_execute_missing_raises():
    sess = _StubSession(None)
    tool = GetTicket.__new__(GetTicket)
    with pytest.raises(LookupError):
        await tool.execute(GetTicketArgs(ticket_id=999), sess)
