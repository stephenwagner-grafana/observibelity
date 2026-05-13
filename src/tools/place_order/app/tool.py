"""place_order — create an order row + line item + decrement stock.

This is the canonical *side-effect* tool: it mutates ``orders``,
``order_items``, and ``catalog_items.stock_qty`` in a single transaction.
"""
from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from tool_base import Tool


class PlaceOrderArgs(BaseModel):
    """Inputs for ``place_order``."""

    sku: str = Field(..., min_length=1)
    qty: int = Field(..., ge=1, le=100)
    persona_id: str = Field(..., min_length=1)


class PlaceOrderResult(BaseModel):
    """Result of a successful order placement."""

    order_id: int
    sku: str
    qty: int
    total_usd: float
    placed_at: datetime
    status: str


class PlaceOrder(Tool):
    NAME = "place_order"
    SIDE_EFFECT = True
    IDEMPOTENT = False
    TIMEOUT_SEC = 10
    MAX_CONCURRENCY = 20
    CACHE_TTL_SEC = 0  # never cache writes
    RETRIES = 0        # side-effect + not idempotent => no retries
    BACKING_TABLES = ["orders", "order_items", "catalog_items"]
    REPLICAS = 2

    Args = PlaceOrderArgs
    Result = PlaceOrderResult

    async def execute(
        self,
        args: PlaceOrderArgs,
        session: AsyncSession | None = None,
    ) -> PlaceOrderResult:
        assert session is not None, "place_order requires a DB session"

        # Look up + lock the row for update so qty stays consistent.
        lookup = text(
            """
            SELECT id, price_usd, stock_qty
              FROM catalog_items
             WHERE sku = :sku
             FOR UPDATE
            """
        )
        row = (await session.execute(lookup, {"sku": args.sku})).one_or_none()
        if row is None:
            raise LookupError(f"sku not found: {args.sku}")
        if row.stock_qty < args.qty:
            raise ValueError(
                f"insufficient stock for {args.sku}: have {row.stock_qty}, want {args.qty}"
            )
        price = float(row.price_usd)
        total = round(price * args.qty, 2)
        now = datetime.now(tz=timezone.utc)

        # Create the order header.
        order_ins = text(
            """
            INSERT INTO orders (persona_id, placed_at, status, total_usd)
            VALUES (:pid, :ts, 'paid', :total)
            RETURNING id
            """
        )
        order_row = (
            await session.execute(
                order_ins,
                {"pid": args.persona_id, "ts": now, "total": total},
            )
        ).one()
        order_id = int(order_row.id)

        # Insert the single line item.
        item_ins = text(
            """
            INSERT INTO order_items (order_id, sku, qty, price_usd)
            VALUES (:oid, :sku, :qty, :price)
            """
        )
        await session.execute(
            item_ins,
            {"oid": order_id, "sku": args.sku, "qty": args.qty, "price": price},
        )

        # Decrement stock.
        dec = text(
            """
            UPDATE catalog_items
               SET stock_qty = stock_qty - :qty
             WHERE sku = :sku
            """
        )
        await session.execute(dec, {"qty": args.qty, "sku": args.sku})

        await session.commit()

        return PlaceOrderResult(
            order_id=order_id,
            sku=args.sku,
            qty=args.qty,
            total_usd=total,
            placed_at=now,
            status="paid",
        )
