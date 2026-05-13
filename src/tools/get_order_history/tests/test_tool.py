"""Tests for the get_order_history tool."""
from __future__ import annotations

from datetime import datetime

import pytest

from app.tool import (
    GetOrderHistory,
    GetOrderHistoryArgs,
    GetOrderHistoryResult,
)


class _Row:
    def __init__(self, **kw):
        self.__dict__.update(kw)


class _StubResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _StubSession:
    def __init__(self, order_rows, item_rows):
        self._orders = order_rows
        self._items = item_rows

    async def execute(self, stmt, params):
        if "order_items" in str(stmt):
            return _StubResult(self._items)
        return _StubResult(self._orders)


def test_knobs():
    assert GetOrderHistory.NAME == "get_order_history"
    assert GetOrderHistory.CACHE_TTL_SEC == 30
    assert "orders" in GetOrderHistory.BACKING_TABLES


@pytest.mark.asyncio
async def test_execute_empty():
    session = _StubSession([], [])
    tool = GetOrderHistory.__new__(GetOrderHistory)
    res = await tool.execute(GetOrderHistoryArgs(persona_id="p-1"), session)
    assert isinstance(res, GetOrderHistoryResult)
    assert res.orders == []


@pytest.mark.asyncio
async def test_execute_groups_items():
    now = datetime(2026, 1, 1, 12, 0, 0)
    orders = [
        _Row(id=10, placed_at=now, status="paid", total_usd=42.0),
        _Row(id=11, placed_at=now, status="paid", total_usd=12.0),
    ]
    items = [
        _Row(order_id=10, sku="neon-1", qty=2, price_usd=10.0, name="Neon T"),
        _Row(order_id=10, sku="neon-2", qty=1, price_usd=22.0, name="Neon Hat"),
        _Row(order_id=11, sku="neon-3", qty=1, price_usd=12.0, name="Neon Pin"),
    ]
    session = _StubSession(orders, items)
    tool = GetOrderHistory.__new__(GetOrderHistory)
    res = await tool.execute(GetOrderHistoryArgs(persona_id="p-1", limit=10), session)
    assert len(res.orders) == 2
    assert len(res.orders[0].items) == 2
    assert res.orders[1].items[0].sku == "neon-3"
