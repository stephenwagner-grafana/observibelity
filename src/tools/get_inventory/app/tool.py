"""get_inventory — check stock for a SKU.

KEY for the mice-rca demo: when the SKU prefix is ``mice-`` or ``rodent-``
this tool deliberately runs a query that references the non-existent column
``rodent_qty``. Postgres raises ``UndefinedColumn`` (SQLSTATE 42703), which
flows up through OTel as a tool-level error and seeds the RCA narrative.
"""
from __future__ import annotations

from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from tool_base import Tool


class GetInventoryArgs(BaseModel):
    """Inputs for ``get_inventory``."""

    sku: str = Field(..., min_length=1)


class GetInventoryResult(BaseModel):
    """Stock level for a single SKU."""

    sku: str
    stock_qty: int
    in_stock: bool


class GetInventory(Tool):
    NAME = "get_inventory"
    SIDE_EFFECT = False
    IDEMPOTENT = True
    TIMEOUT_SEC = 5
    MAX_CONCURRENCY = 50
    CACHE_TTL_SEC = 10
    RETRIES = 1
    ALLOWED_CALLERS = ["nc-fulfillment-orchestrator", "nc-chatbot"]
    BACKING_TABLES = ["catalog_items"]
    REPLICAS = 2

    Args = GetInventoryArgs
    Result = GetInventoryResult

    async def execute(
        self,
        args: GetInventoryArgs,
        session: AsyncSession | None = None,
    ) -> GetInventoryResult:
        assert session is not None, "get_inventory requires a DB session"
        if args.sku.startswith("mice-") or args.sku.startswith("rodent-"):
            # Artificial demo error path — Postgres throws
            # "column rodent_qty does not exist" (sqlstate 42703).
            stmt = text("SELECT rodent_qty FROM catalog_items WHERE sku = :sku")
            await session.execute(stmt, {"sku": args.sku})
            # If somehow no error, fall through (shouldn't happen with seed data).
            return GetInventoryResult(sku=args.sku, stock_qty=0, in_stock=False)

        stmt = text("SELECT stock_qty FROM catalog_items WHERE sku = :sku")
        row = (await session.execute(stmt, {"sku": args.sku})).one_or_none()
        if row is None:
            raise LookupError(f"sku not found: {args.sku}")
        qty = int(row.stock_qty)
        return GetInventoryResult(sku=args.sku, stock_qty=qty, in_stock=qty > 0)
