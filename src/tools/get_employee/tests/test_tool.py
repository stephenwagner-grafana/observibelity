"""Tests for the get_employee tool."""
from __future__ import annotations

import pytest

from app.tool import GetEmployee, GetEmployeeArgs


class _StubResult:
    def __init__(self, row): self._row = row
    def one_or_none(self): return self._row


class _StubRow:
    def __init__(self, **kw): self.__dict__.update(kw)


class _StubSession:
    def __init__(self, row): self._row = row; self.last_params = None
    async def execute(self, stmt, params): self.last_params = params; return _StubResult(self._row)


def test_knobs():
    assert GetEmployee.NAME == "get_employee"
    assert "sb-employee-info" in GetEmployee.ALLOWED_CALLERS
    assert "sb-it-troubleshoot" not in GetEmployee.ALLOWED_CALLERS


@pytest.mark.asyncio
async def test_execute_by_id():
    row = _StubRow(id=3, name="Alice", email="a@acme.com", role="eng", department="platform")
    sess = _StubSession(row)
    tool = GetEmployee.__new__(GetEmployee)
    res = await tool.execute(GetEmployeeArgs(persona_id="3"), sess)
    assert res.name == "Alice"
    assert sess.last_params["pid"] == 3


@pytest.mark.asyncio
async def test_execute_by_email_falls_through():
    row = _StubRow(id=3, name="Alice", email="a@acme.com", role="eng", department=None)
    sess = _StubSession(row)
    tool = GetEmployee.__new__(GetEmployee)
    res = await tool.execute(GetEmployeeArgs(persona_id="a@acme.com"), sess)
    assert res.id == 3
    assert sess.last_params["pid"] == "a@acme.com"


@pytest.mark.asyncio
async def test_missing_raises():
    sess = _StubSession(None)
    tool = GetEmployee.__new__(GetEmployee)
    with pytest.raises(LookupError):
        await tool.execute(GetEmployeeArgs(persona_id="999"), sess)
