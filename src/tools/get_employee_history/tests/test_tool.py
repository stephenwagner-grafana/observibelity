"""Tests for the get_employee_history tool."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.tool import (
    GetEmployeeHistory,
    GetEmployeeHistoryArgs,
    SENSITIVE_PREFIX,
)


class _StubResult:
    def __init__(self, rows): self._rows = rows
    def all(self): return self._rows


class _StubRow:
    def __init__(self, **kw): self.__dict__.update(kw)


class _StubSession:
    def __init__(self, orders=None, conversations=None, raise_on_sensitive=False):
        self._orders = orders or []
        self._convs = conversations or []
        self.raise_on_sensitive = raise_on_sensitive
        self.calls: list[str] = []

    async def execute(self, stmt, params):
        sql = str(stmt)
        self.calls.append(sql)
        if "secret_clearance" in sql:
            if self.raise_on_sensitive:
                raise Exception('column "secret_clearance" does not exist')
            return _StubResult([])
        if "FROM orders" in sql:
            return _StubResult(self._orders)
        if "FROM conversations" in sql:
            return _StubResult(self._convs)
        return _StubResult([])


def test_knobs():
    assert GetEmployeeHistory.NAME == "get_employee_history"
    assert GetEmployeeHistory.ALLOWED_CALLERS == ["sb-employee-info"]
    assert "orders" in GetEmployeeHistory.BACKING_TABLES


@pytest.mark.asyncio
async def test_normal_persona_returns_rows():
    now = datetime.now(tz=timezone.utc)
    sess = _StubSession(orders=[_StubRow(id=1, placed_at=now, status="paid", total_usd=12.0)])
    tool = GetEmployeeHistory.__new__(GetEmployeeHistory)
    res = await tool.execute(GetEmployeeHistoryArgs(persona_id="3"), sess)
    assert res.persona_id == "3"
    assert len(res.orders) == 1


@pytest.mark.asyncio
async def test_sensitive_prefix_triggers_schema_query():
    sess = _StubSession(raise_on_sensitive=True)
    tool = GetEmployeeHistory.__new__(GetEmployeeHistory)
    pid = SENSITIVE_PREFIX + "alice"
    with pytest.raises(Exception, match="secret_clearance"):
        await tool.execute(GetEmployeeHistoryArgs(persona_id=pid), sess)
    assert any("secret_clearance" in q for q in sess.calls)
