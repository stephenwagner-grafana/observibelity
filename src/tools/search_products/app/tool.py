"""search_products — full-text + filter search over the NeonCart catalog."""
from __future__ import annotations

from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from tool_base import Tool


class SearchProductsArgs(BaseModel):
    """Inputs for ``search_products``."""

    query: str = Field(..., min_length=1, description="ILIKE pattern matched against name + description.")
    limit: int = Field(20, ge=1, le=100, description="Maximum rows returned.")


class ProductRef(BaseModel):
    """Lightweight product summary returned by search."""

    id: int
    sku: str
    name: str
    price_usd: float


class SearchProductsResult(BaseModel):
    """Search response payload."""

    items: list[ProductRef]
    total: int


class SearchProducts(Tool):
    NAME = "search_products"
    SIDE_EFFECT = False
    IDEMPOTENT = True
    TIMEOUT_SEC = 5
    MAX_CONCURRENCY = 50
    CACHE_TTL_SEC = 60
    RETRIES = 1
    BACKING_TABLES = ["catalog_items", "categories"]
    REPLICAS = 2

    Args = SearchProductsArgs
    Result = SearchProductsResult

    async def execute(
        self,
        args: SearchProductsArgs,
        session: AsyncSession | None = None,
    ) -> SearchProductsResult:
        assert session is not None, "search_products requires a DB session"
        stmt = text(
            """
            SELECT id, sku, name, price_usd
              FROM catalog_items
             WHERE name ILIKE :q OR description ILIKE :q
             ORDER BY id
             LIMIT :lim
            """
        )
        rows = (
            await session.execute(stmt, {"q": f"%{args.query}%", "lim": args.limit})
        ).all()
        items = [
            ProductRef(id=r.id, sku=r.sku, name=r.name, price_usd=float(r.price_usd))
            for r in rows
        ]
        return SearchProductsResult(items=items, total=len(items))
