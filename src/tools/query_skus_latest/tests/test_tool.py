"""Tests for the query_skus_latest tool."""
from __future__ import annotations

import pytest

from app.tool import (
    ProductRef,
    QuerySkusLatest,
    QuerySkusLatestArgs,
    QuerySkusLatestResult,
)


class _StubRow:
    def __init__(self, id, sku, name, price_usd):
        self.id = id
        self.sku = sku
        self.name = name
        self.price_usd = price_usd


class _StubResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _StubSession:
    """Captures the rendered SQL + params for each `.execute()` call."""

    def __init__(self, rows):
        self._rows = rows
        self.last_params: dict | None = None
        self.executed: list[tuple[str, dict]] = []

    async def execute(self, stmt, params):
        self.last_params = params
        self.executed.append((str(stmt), dict(params)))
        return _StubResult(self._rows)


def test_args_validation():
    args = QuerySkusLatestArgs(
        pattern="1004-corsair-0072-..GB\\.DDR.-....-.......",
        queried_product_id="1004-corsair-0072-64GB.DDR5-2026-1061873",
        limit=4,
    )
    assert args.limit == 4
    assert args.queried_product_id == "1004-corsair-0072-64GB.DDR5-2026-1061873"
    # default limit is 4; queried_product_id is optional
    bare = QuerySkusLatestArgs(pattern="x")
    assert bare.limit == 4
    assert bare.queried_product_id is None


def test_knobs():
    assert QuerySkusLatest.NAME == "query_skus_latest"
    assert QuerySkusLatest.SIDE_EFFECT is False
    assert QuerySkusLatest.IDEMPOTENT is True
    assert QuerySkusLatest.BACKING_TABLES == ["catalog_items"]
    assert QuerySkusLatest.REPLICAS == 2


@pytest.mark.asyncio
async def test_execute_returns_four_candidates():
    """The visual punchline: 4 near-identical, year-suffixed SKU rows come
    back. The result must surface all four (items=4, total=4) and the SQL
    parameter dict must carry the regex pattern as ``pattern`` (matching
    what the tool advertised).
    """
    pattern = r"1004-corsair-0072-..GB\.DDR.-....-......."
    rows = [
        _StubRow(
            519,
            "1004-corsair-0072-64GB.DDR5-2026-1061873.2026",
            "Corsair Dominator DDR5 64GB",
            999.00,
        ),
        _StubRow(
            520,
            "1004-corsair-0072-64GB.DDR4-2023-1061873.2023",
            "Corsair Dominator DDR4 64GB",
            199.00,
        ),
        _StubRow(
            521,
            "1004-corsair-0072-32GB.DDR5-2026-1061874.2026",
            "Corsair Dominator DDR5 32GB",
            599.00,
        ),
        _StubRow(
            522,
            "1004-corsair-0072-32GB.DDR4-2023-1061874.2023",
            "Corsair Dominator DDR4 32GB",
            129.00,
        ),
    ]
    session = _StubSession(rows)
    tool = QuerySkusLatest.__new__(QuerySkusLatest)  # skip DB engine init

    res = await tool.execute(
        QuerySkusLatestArgs(
            pattern=pattern,
            queried_product_id="1004-corsair-0072-64GB.DDR5-2026-1061873.2026",
            limit=4,
        ),
        session,
    )

    assert isinstance(res, QuerySkusLatestResult)
    assert res.total == 4
    assert len(res.items) == 4
    assert isinstance(res.items[0], ProductRef)
    # First candidate is the head of the returned rows — "selected_index = 0".
    assert res.items[0].sku.endswith(".2026")
    # Bound parameter the tool sent to Postgres carries the verbatim regex.
    assert session.last_params is not None
    assert session.last_params["pattern"] == pattern


@pytest.mark.asyncio
async def test_execute_accepts_usecase_kwarg_and_ignores_it():
    """The base class introspects execute()'s signature and forwards the
    X-Usecase header. This tool accepts the kwarg per the contract but is
    explicitly behavior-neutral on it — the same SQL runs regardless.
    """
    rows = [_StubRow(1, "abc.2026", "Item", 10.0)]
    session = _StubSession(rows)
    tool = QuerySkusLatest.__new__(QuerySkusLatest)

    res_a = await tool.execute(
        QuerySkusLatestArgs(pattern="abc.*", queried_product_id="abc.2026"),
        session,
        usecase="cross-gen-retrieval-drift",
    )
    res_b = await tool.execute(
        QuerySkusLatestArgs(pattern="abc.*", queried_product_id="abc.2026"),
        session,
        usecase=None,
    )
    assert res_a.total == res_b.total == 1
    # Both invocations sent the same bound params.
    assert session.executed[0][1] == session.executed[1][1] == {"pattern": "abc.*"}


@pytest.mark.asyncio
async def test_execute_caps_results_at_limit():
    """The SQL hard-caps at 16, but the in-memory slice respects ``limit``
    so the audience sees exactly 4 candidates in the punchline column."""
    rows = [
        _StubRow(i, f"sku-{i}.2026", f"Item {i}", float(i))
        for i in range(1, 9)
    ]
    session = _StubSession(rows)
    tool = QuerySkusLatest.__new__(QuerySkusLatest)
    res = await tool.execute(
        QuerySkusLatestArgs(pattern="sku-.*", limit=4),
        session,
    )
    assert res.total == 4
    assert len(res.items) == 4
