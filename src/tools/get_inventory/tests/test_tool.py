"""Tests for the get_inventory tool — including the mice-rca demo error path."""
from __future__ import annotations

import pytest

from app.tool import GetInventory, GetInventoryArgs, GetInventoryResult


class _Row:
    def __init__(self, stock_qty):
        self.stock_qty = stock_qty


class _StubResult:
    def __init__(self, row):
        self._row = row

    def one_or_none(self):
        return self._row


class _StubSession:
    """Stub session. Raises on the mice-rca rodent_qty path."""

    def __init__(self, row, *, raise_on_rodent=True):
        self._row = row
        self._raise_on_rodent = raise_on_rodent
        self.executed: list[tuple[str, dict]] = []

    async def execute(self, stmt, params):
        s = str(stmt)
        self.executed.append((s, params))
        if "rodent_qty" in s and self._raise_on_rodent:
            raise RuntimeError("column rodent_qty does not exist (sqlstate 42703)")
        return _StubResult(self._row)


def test_knobs():
    assert GetInventory.NAME == "get_inventory"
    assert GetInventory.SIDE_EFFECT is False
    assert GetInventory.ALLOWED_CALLERS == [
        "nc-fulfillment-orchestrator",
        "nc-chatbot",
    ]
    assert GetInventory.BACKING_TABLES == ["catalog_items"]


@pytest.mark.asyncio
async def test_normal_sku_returns_stock():
    session = _StubSession(_Row(5))
    tool = GetInventory.__new__(GetInventory)
    res = await tool.execute(GetInventoryArgs(sku="neon-1"), session)
    assert isinstance(res, GetInventoryResult)
    assert res.stock_qty == 5
    assert res.in_stock is True


@pytest.mark.asyncio
async def test_unknown_sku_raises():
    session = _StubSession(None)
    tool = GetInventory.__new__(GetInventory)
    with pytest.raises(LookupError):
        await tool.execute(GetInventoryArgs(sku="missing"), session)


@pytest.mark.asyncio
async def test_mice_sku_triggers_rodent_qty_error():
    """The whole point of the mice-rca demo path: must hit the bad query."""
    session = _StubSession(None)
    tool = GetInventory.__new__(GetInventory)
    with pytest.raises(RuntimeError) as exc:
        await tool.execute(GetInventoryArgs(sku="mice-1"), session)
    assert "rodent_qty" in str(exc.value)
    assert any("rodent_qty" in s for s, _ in session.executed)


@pytest.mark.asyncio
async def test_rodent_sku_also_triggers_error():
    session = _StubSession(None)
    tool = GetInventory.__new__(GetInventory)
    with pytest.raises(RuntimeError):
        await tool.execute(GetInventoryArgs(sku="rodent-foo"), session)
