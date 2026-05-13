"""Tests for the create_expense tool."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.tool import APPROVAL_THRESHOLD_USD, CreateExpense, CreateExpenseArgs


class _StubResult:
    def __init__(self, row): self._row = row
    def one(self): return self._row


class _StubRow:
    def __init__(self, **kw): self.__dict__.update(kw)


class _StubSession:
    def __init__(self, status):
        self._status = status; self.committed = False; self.last_params = None

    async def execute(self, stmt, params):
        self.last_params = params
        return _StubResult(_StubRow(
            id=99, status=params["st"], created_at=datetime.now(tz=timezone.utc),
        ))

    async def commit(self):
        self.committed = True


def test_knobs():
    assert CreateExpense.NAME == "create_expense"
    assert CreateExpense.SIDE_EFFECT is True
    assert CreateExpense.IDEMPOTENT is False
    assert CreateExpense.ALLOWED_CALLERS == ["sb-expense-helper"]


@pytest.mark.asyncio
async def test_below_threshold_auto_approved():
    sess = _StubSession(status="approved")
    tool = CreateExpense.__new__(CreateExpense)
    res = await tool.execute(
        CreateExpenseArgs(persona_id="3", amount_usd=10.0, category="meals"),
        sess,
    )
    assert res.status == "approved"
    assert sess.last_params["st"] == "approved"


@pytest.mark.asyncio
async def test_above_threshold_pending():
    sess = _StubSession(status="pending_approval")
    tool = CreateExpense.__new__(CreateExpense)
    big = APPROVAL_THRESHOLD_USD + 1
    res = await tool.execute(
        CreateExpenseArgs(persona_id="3", amount_usd=big, category="travel"),
        sess,
    )
    assert res.status == "pending_approval"
