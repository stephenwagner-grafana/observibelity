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
    row = _StubRow(
        id=11, ticket_number="T-deadbeef", status="open",
        priority="medium", created_at=now,
    )
    sess = _StubSession(row)
    tool = CreateTicket.__new__(CreateTicket)
    res = await tool.execute(
        CreateTicketArgs(subject="VPN broken", body="..", category="it", persona_id="u-tim-l"),
        sess,
    )
    assert res.ticket_id == 11
    assert res.ticket_number == "T-deadbeef"
    assert sess.committed is True
    # persona_id is a STRING slug (FK to personas.persona_id); the tool
    # must pass it through verbatim — not coerce to int.
    assert sess.last_params["pid"] == "u-tim-l"
    # category "it" is not a high-priority bucket → priority defaults to medium.
    assert sess.last_params["prio"] == "medium"


@pytest.mark.asyncio
async def test_escalation_promotes_priority():
    now = datetime.now(tz=timezone.utc)
    row = _StubRow(
        id=12, ticket_number="T-esc", status="open",
        priority="high", created_at=now,
    )
    sess = _StubSession(row)
    tool = CreateTicket.__new__(CreateTicket)
    await tool.execute(
        CreateTicketArgs(
            subject="prod down", body="urgent",
            category="escalation", persona_id="u-mara-chen",
        ),
        sess,
    )
    assert sess.last_params["prio"] == "high"
