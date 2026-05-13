"""Tests for the create_ticket tool."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.tool import CreateTicket, CreateTicketArgs


class _StubResult:
    def __init__(self, row): self._row = row
    def one(self): return self._row


class _StubRow:
    def __init__(self, **kw): self.__dict__.update(kw)


class _StubSession:
    def __init__(self, row): self._row = row; self.committed = False; self.last_params = None
    async def execute(self, stmt, params): self.last_params = params; return _StubResult(self._row)
    async def commit(self): self.committed = True


def test_knobs():
    assert CreateTicket.NAME == "create_ticket"
    assert CreateTicket.SIDE_EFFECT is True
    assert CreateTicket.IDEMPOTENT is False
    assert CreateTicket.RETRIES == 0


@pytest.mark.asyncio
async def test_execute_inserts_and_commits():
    now = datetime.now(tz=timezone.utc)
    row = _StubRow(id=11, status="open", created_at=now)
    sess = _StubSession(row)
    tool = CreateTicket.__new__(CreateTicket)
    res = await tool.execute(
        CreateTicketArgs(subject="VPN broken", body="..", category="it", persona_id="3"),
        sess,
    )
    assert res.ticket_id == 11
    assert sess.committed is True
    assert sess.last_params["pid"] == 3
