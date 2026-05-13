"""Tests for the place_order tool."""
from __future__ import annotations

import pytest

from app.tool import PlaceOrder, PlaceOrderArgs, PlaceOrderResult


class _Row:
    def __init__(self, **kw):
        self.__dict__.update(kw)


class _StubResult:
    def __init__(self, row=None):
        self._row = row

    def one_or_none(self):
        return self._row

    def one(self):
        if self._row is None:
            raise LookupError("no rows")
        return self._row


class _StubSession:
    def __init__(self, item_row, order_id=999):
        self._item = item_row
        self._order_id = order_id
        self.executed: list[tuple[str, dict]] = []
        self.committed = False

    async def execute(self, stmt, params):
        s = str(stmt)
        self.executed.append((s, params))
        if "FROM catalog_items" in s and "FOR UPDATE" in s:
            return _StubResult(self._item)
        if "INSERT INTO orders" in s:
            return _StubResult(_Row(id=self._order_id))
        return _StubResult(None)

    async def commit(self):
        self.committed = True


def test_knobs():
    assert PlaceOrder.NAME == "place_order"
    assert PlaceOrder.SIDE_EFFECT is True
    assert PlaceOrder.IDEMPOTENT is False
    assert PlaceOrder.CACHE_TTL_SEC == 0
    assert PlaceOrder.RETRIES == 0
    assert set(PlaceOrder.BACKING_TABLES) == {"orders", "order_items", "catalog_items"}


@pytest.mark.asyncio
async def test_execute_writes_and_decrements():
    session = _StubSession(_Row(id=1, price_usd=10.0, stock_qty=5), order_id=42)
    tool = PlaceOrder.__new__(PlaceOrder)
    res = await tool.execute(
        PlaceOrderArgs(sku="neon-1", qty=2, persona_id="p-1"),
        session,
    )
    assert isinstance(res, PlaceOrderResult)
    assert res.order_id == 42
    assert res.total_usd == 20.0
    assert res.status == "paid"
    statements = [s for s, _ in session.executed]
    assert any("INSERT INTO orders" in s for s in statements)
    assert any("INSERT INTO order_items" in s for s in statements)
    assert any("stock_qty = stock_qty - :qty" in s for s in statements)
    assert session.committed is True


@pytest.mark.asyncio
async def test_unknown_sku_raises():
    session = _StubSession(None)
    tool = PlaceOrder.__new__(PlaceOrder)
    with pytest.raises(LookupError):
        await tool.execute(
            PlaceOrderArgs(sku="missing", qty=1, persona_id="p-1"),
            session,
        )


@pytest.mark.asyncio
async def test_insufficient_stock_raises():
    session = _StubSession(_Row(id=1, price_usd=10.0, stock_qty=1))
    tool = PlaceOrder.__new__(PlaceOrder)
    with pytest.raises(ValueError):
        await tool.execute(
            PlaceOrderArgs(sku="neon-1", qty=5, persona_id="p-1"),
            session,
        )
