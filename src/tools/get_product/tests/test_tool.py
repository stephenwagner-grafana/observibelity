"""Tests for the get_product tool."""
from __future__ import annotations

import pytest

from app.tool import (
    GetProduct,
    GetProductArgs,
    GetProductResult,
    ProductDetail,
)


class _StubResult:
    def __init__(self, row=None, rows=None):
        self._row = row
        self._rows = rows or []

    def one_or_none(self):
        return self._row

    def all(self):
        return self._rows


class _ProdRow:
    def __init__(self):
        self.id = 1
        self.sku = "neon-1"
        self.name = "Neon T-Shirt"
        self.description = "soft glow"
        self.price_usd = 19.99
        self.stock_qty = 10
        self.brand = "NeonCo"


class _PromoRow:
    def __init__(self, id, code, description, discount_pct):
        self.id = id
        self.code = code
        self.description = description
        self.discount_pct = discount_pct


class _StubSession:
    def __init__(self, prod_row, promo_rows):
        self._prod = prod_row
        self._promos = promo_rows
        self.queries: list[dict] = []

    async def execute(self, stmt, params):
        self.queries.append(params)
        if "promotions" in str(stmt):
            return _StubResult(rows=self._promos)
        return _StubResult(row=self._prod)


def test_one_of_required():
    with pytest.raises(ValueError):
        GetProductArgs()
    with pytest.raises(ValueError):
        GetProductArgs(product_id=1, sku="x")


def test_knobs():
    assert GetProduct.NAME == "get_product"
    assert GetProduct.CACHE_TTL_SEC == 120
    assert set(GetProduct.BACKING_TABLES) == {"catalog_items", "brands", "promotions"}


@pytest.mark.asyncio
async def test_execute_by_id():
    session = _StubSession(_ProdRow(), [_PromoRow(7, "NEON10", "10 percent off", 10.0)])
    tool = GetProduct.__new__(GetProduct)
    res = await tool.execute(GetProductArgs(product_id=1), session)
    assert isinstance(res, GetProductResult)
    assert res.product.sku == "neon-1"
    assert len(res.promotions) == 1
    assert res.promotions[0].code == "NEON10"


@pytest.mark.asyncio
async def test_execute_missing_raises():
    session = _StubSession(None, [])
    tool = GetProduct.__new__(GetProduct)
    with pytest.raises(LookupError):
        await tool.execute(GetProductArgs(sku="missing"), session)
