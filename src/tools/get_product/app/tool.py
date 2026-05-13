"""get_product — fetch a product with brand + active promotions."""
from __future__ import annotations

from typing import Self

from pydantic import BaseModel, Field, model_validator
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from tool_base import Tool


class GetProductArgs(BaseModel):
    """Inputs for ``get_product``. Exactly one of ``product_id`` or ``sku`` must be set."""

    product_id: int | None = Field(None, ge=1)
    sku: str | None = None

    @model_validator(mode="after")
    def _one_of(self) -> Self:
        if (self.product_id is None) == (self.sku is None):
            raise ValueError("exactly one of product_id or sku must be provided")
        return self


class Promotion(BaseModel):
    """Active promotion attached to a product."""

    id: int
    code: str
    description: str
    discount_pct: float


class ProductDetail(BaseModel):
    """Full product payload."""

    id: int
    sku: str
    name: str
    description: str | None
    price_usd: float
    brand: str | None
    stock_qty: int


class GetProductResult(BaseModel):
    """Result payload for ``get_product``."""

    product: ProductDetail
    promotions: list[Promotion]


class GetProduct(Tool):
    NAME = "get_product"
    SIDE_EFFECT = False
    IDEMPOTENT = True
    TIMEOUT_SEC = 5
    MAX_CONCURRENCY = 50
    CACHE_TTL_SEC = 120
    RETRIES = 1
    BACKING_TABLES = ["catalog_items", "brands", "promotions"]
    REPLICAS = 2

    Args = GetProductArgs
    Result = GetProductResult

    async def execute(
        self,
        args: GetProductArgs,
        session: AsyncSession | None = None,
    ) -> GetProductResult:
        assert session is not None, "get_product requires a DB session"
        if args.product_id is not None:
            where = "ci.id = :id"
            params: dict[str, object] = {"id": args.product_id}
        else:
            where = "ci.sku = :sku"
            params = {"sku": args.sku}

        prod_stmt = text(
            f"""
            SELECT ci.id, ci.sku, ci.name, ci.description, ci.price_usd,
                   ci.stock_qty, b.name AS brand
              FROM catalog_items ci
              LEFT JOIN brands b ON b.id = ci.brand_id
             WHERE {where}
             LIMIT 1
            """
        )
        row = (await session.execute(prod_stmt, params)).one_or_none()
        if row is None:
            raise LookupError(f"product not found: {args.model_dump_json()}")

        product = ProductDetail(
            id=row.id,
            sku=row.sku,
            name=row.name,
            description=row.description,
            price_usd=float(row.price_usd),
            brand=row.brand,
            stock_qty=int(row.stock_qty),
        )

        promo_stmt = text(
            """
            SELECT id, code, description, discount_pct
              FROM promotions
             WHERE product_id = :pid AND active
            """
        )
        promo_rows = (
            await session.execute(promo_stmt, {"pid": product.id})
        ).all()
        promotions = [
            Promotion(
                id=r.id,
                code=r.code,
                description=r.description,
                discount_pct=float(r.discount_pct),
            )
            for r in promo_rows
        ]
        return GetProductResult(product=product, promotions=promotions)
