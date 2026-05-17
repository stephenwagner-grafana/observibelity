"""Tests for the search_products tool."""
from __future__ import annotations

import pytest

from app.tool import ProductRef, SearchProducts, SearchProductsArgs, SearchProductsResult


class _StubResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _StubRow:
    def __init__(self, id, sku, name, price_usd):
        self.id = id
        self.sku = sku
        self.name = name
        self.price_usd = price_usd


class _StubSession:
    def __init__(self, rows):
        self._rows = rows
        self.last_params: dict | None = None

    async def execute(self, stmt, params):
        self.last_params = params
        return _StubResult(self._rows)


def test_args_validation():
    args = SearchProductsArgs(query="neon", limit=5)
    assert args.query == "neon"
    assert args.limit == 5


def test_knobs():
    assert SearchProducts.NAME == "search_products"
    assert SearchProducts.SIDE_EFFECT is False
    assert SearchProducts.CACHE_TTL_SEC == 60
    assert "catalog_items" in SearchProducts.BACKING_TABLES
    assert SearchProducts.REPLICAS == 2


@pytest.mark.asyncio
async def test_execute_maps_rows():
    rows = [
        _StubRow(1, "neon-1", "Neon T-Shirt", 19.99),
        _StubRow(2, "neon-2", "Neon Hat", 9.50),
    ]
    session = _StubSession(rows)
    tool = SearchProducts.__new__(SearchProducts)  # skip DB engine init
    res = await tool.execute(SearchProductsArgs(query="neon", limit=10), session)
    assert isinstance(res, SearchProductsResult)
    assert res.total == 2
    assert res.items[0] == ProductRef(id=1, sku="neon-1", name="Neon T-Shirt", price_usd=19.99)
    assert session.last_params == {"q": "%neon%", "lim": 10}
