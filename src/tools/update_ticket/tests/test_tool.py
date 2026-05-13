"""Tests for the update_ticket tool."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.tool import UpdateTicket, UpdateTicketArgs


class _StubResult:
    def __init__(self, row): self._row = row
    def one_or_none(self): return self._row


class _StubRow:
    def __init__(self, **kw): self.__dict__.update(kw)


class _StubSession:
    def __init__(self, row): self._row = row; self.committed = False
    async def execute(self, stmt, params): self.last_params = params; return _StubResult(self._row)
    async def commit(self): self.committed = True


def test_knobs():
    assert UpdateTicket.NAME == "update_ticket"
    assert UpdateTicket.SIDE_EFFECT is True
    assert UpdateTicket.IDEMPOTENT is True


@pytest.mark.asyncio
async def test_execute_updates_status():
    now = datetime.now(tz=timezone.utc)
    row = _StubRow(id=1, status="closed", updated_at=now)
    sess = _StubSession(row)
    tool = UpdateTicket.__new__(UpdateTicket)
    res = await tool.execute(UpdateTicketArgs(ticket_id=1, status="closed"), sess)
    assert res.status == "closed"
    assert sess.committed


@pytest.mark.asyncio
async def test_execute_no_fields_raises():
    sess = _StubSession(_StubRow())
    tool = UpdateTicket.__new__(UpdateTicket)
    with pytest.raises(ValueError):
        await tool.execute(UpdateTicketArgs(ticket_id=1), sess)
