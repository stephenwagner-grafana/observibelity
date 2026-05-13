"""Tests for the request_access tool."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.tool import RequestAccess, RequestAccessArgs


class _StubResult:
    def __init__(self, row): self._row = row
    def one(self): return self._row


class _StubRow:
    def __init__(self, **kw): self.__dict__.update(kw)


class _StubSession:
    def __init__(self, row): self._row = row; self.committed = False
    async def execute(self, stmt, params): self.last_params = params; return _StubResult(self._row)
    async def commit(self): self.committed = True


def test_knobs():
    assert RequestAccess.NAME == "request_access"
    assert RequestAccess.SIDE_EFFECT is True
    assert "sb-it-troubleshoot" in RequestAccess.ALLOWED_CALLERS


@pytest.mark.asyncio
async def test_execute_files_ticket():
    now = datetime.now(tz=timezone.utc)
    row = _StubRow(id=22, status="open", created_at=now)
    sess = _StubSession(row)
    tool = RequestAccess.__new__(RequestAccess)
    res = await tool.execute(
        RequestAccessArgs(persona_id="3", resource="prod-db", justification="audit"),
        sess,
    )
    assert res.ticket_id == 22
    assert "prod-db" in sess.last_params["subj"]
    assert sess.committed
