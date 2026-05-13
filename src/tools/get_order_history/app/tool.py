"""get_order_history — list recent orders + line items for a persona."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from tool_base import Tool


class GetOrderHistoryArgs(BaseModel):
    """Inputs for ``get_order_history``."""

    persona_id: str = Field(..., min_length=1)
    limit: int = Field(20, ge=1, le=100)


class OrderItem(BaseModel):
    """Single line item within an order."""

    sku: str
    name: str
    qty: int
    price_usd: float


class OrderSummary(BaseModel):
    """Summary of a single order with its items."""

    id: int
    placed_at: datetime
    status: str
    total_usd: float
    items: list[OrderItem]


class GetOrderHistoryResult(BaseModel):
    """Response payload for ``get_order_history``."""

    persona_id: str
    orders: list[OrderSummary]


class GetOrderHistory(Tool):
    NAME = "get_order_history"
    SIDE_EFFECT = False
    IDEMPOTENT = True
    TIMEOUT_SEC = 5
    MAX_CONCURRENCY = 50
    CACHE_TTL_SEC = 30
    RETRIES = 1
    BACKING_TABLES = ["orders", "order_items"]
    REPLICAS = 2

    Args = GetOrderHistoryArgs
    Result = GetOrderHistoryResult

    async def execute(
        self,
        args: GetOrderHistoryArgs,
        session: AsyncSession | None = None,
    ) -> GetOrderHistoryResult:
        assert session is not None, "get_order_history requires a DB session"
        order_stmt = text(
            """
            SELECT id, placed_at, status, total_usd
              FROM orders
             WHERE persona_id = :pid
             ORDER BY placed_at DESC
             LIMIT :lim
            """
        )
        order_rows = (
            await session.execute(order_stmt, {"pid": args.persona_id, "lim": args.limit})
        ).all()

        orders: list[OrderSummary] = []
        if not order_rows:
            return GetOrderHistoryResult(persona_id=args.persona_id, orders=[])

        order_ids = [r.id for r in order_rows]
        items_stmt = text(
            """
            SELECT oi.order_id, oi.sku, oi.qty, oi.price_usd, ci.name
              FROM order_items oi
              LEFT JOIN catalog_items ci ON ci.sku = oi.sku
             WHERE oi.order_id = ANY(:ids)
            """
        )
        item_rows = (
            await session.execute(items_stmt, {"ids": order_ids})
        ).all()

        items_by_order: dict[int, list[OrderItem]] = {}
        for r in item_rows:
            items_by_order.setdefault(r.order_id, []).append(
                OrderItem(
                    sku=r.sku,
                    name=r.name or r.sku,
                    qty=int(r.qty),
                    price_usd=float(r.price_usd),
                )
            )

        for r in order_rows:
            orders.append(
                OrderSummary(
                    id=r.id,
                    placed_at=r.placed_at,
                    status=r.status,
                    total_usd=float(r.total_usd),
                    items=items_by_order.get(r.id, []),
                )
            )
        return GetOrderHistoryResult(persona_id=args.persona_id, orders=orders)
