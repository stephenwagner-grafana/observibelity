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


@pytest.mark.asyncio
async def test_cross_gen_drift_picks_older_generation():
    """When usecase=cross-gen-retrieval-drift and the query is a full
    long-form SKU, the tool normalizes to a family wildcard and ranks by
    historical_popularity (oldest year wins). The 2026 query should
    surface the 2023 record at the top — that's the planted bug.
    """
    rows = [
        _StubRow(519, "1004-corsair-0072-64GB.DDR5-2026-1061873",
                 "Corsair Dominator DDR5 64GB", 999.00),
        _StubRow(520, "1004-corsair-0072-64GB.DDR4-2023-1061873",
                 "Corsair Dominator DDR4 64GB", 199.00),
        _StubRow(521, "1004-corsair-0072-32GB.DDR5-2026-1061874",
                 "Corsair Dominator DDR5 32GB", 599.00),
        _StubRow(522, "1004-corsair-0072-32GB.DDR4-2023-1061874",
                 "Corsair Dominator DDR4 32GB", 129.00),
    ]
    session = _StubSession(rows)
    tool = SearchProducts.__new__(SearchProducts)
    res = await tool.execute(
        SearchProductsArgs(
            query="1004-corsair-0072-64GB.DDR5-2026-1061873",
            limit=4,
        ),
        session,
        usecase="cross-gen-retrieval-drift",
    )
    # Wildcard pattern was the brand-model family with size+year folded out.
    assert session.last_params == {"pat": "1004-corsair-0072-%.DDR%"}
    # Top result is the 2023 DDR4 record — older year wins under
    # historical_popularity ranking. That's the punchline.
    assert res.items[0].sku.endswith("DDR4-2023-1061873")
    # The query year was 2026 but the selection is 2023 — the audience-
    # readable mismatch the evaluator looks for.


@pytest.mark.asyncio
async def test_cross_gen_drift_inert_without_sku_query():
    """A natural-language query under the same usecase should NOT trigger
    demo mode — falls back to the regular ILIKE name/description search.
    """
    rows = [_StubRow(1, "abc", "Item", 10.0)]
    session = _StubSession(rows)
    tool = SearchProducts.__new__(SearchProducts)
    await tool.execute(
        SearchProductsArgs(query="corsair dominator", limit=5),
        session,
        usecase="cross-gen-retrieval-drift",
    )
    # Regular SQL path: parameter dict has `q` (ILIKE pattern) + `lim`.
    assert "q" in session.last_params
    assert session.last_params["q"] == "%corsair dominator%"
