"""get_employee_history — order + conversation history for a persona.

**Mice-RCA-like demo trigger**: when called with a `persona_id` starting
with the `sensitive-` prefix (a special seeded test case), the tool runs
a query that references a non-existent column (`secret_clearance`) so the
error path fires. This is the SB-side analogue of the mice-rca
`rodent_qty` column-doesnt-exist bug; it lets the demo show the same RCA
flow on the supportbot trace.

Side effect: read-only. Allowed callers: only sb-employee-info.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from tool_base import Tool

# Persona prefix that triggers the demo schema bug. Keep it specific so
# accidental real personas don't trip it.
SENSITIVE_PREFIX = "sensitive-"


class GetEmployeeHistoryArgs(BaseModel):
    persona_id: str = Field(..., min_length=1, max_length=64)
    limit: int = Field(10, ge=1, le=50)


class HistoryOrder(BaseModel):
    id: int
    placed_at: datetime
    status: str
    total_usd: float


class HistoryConversation(BaseModel):
    id: int
    started_at: datetime
    topic: Optional[str] = None


class GetEmployeeHistoryResult(BaseModel):
    persona_id: str
    orders: list[HistoryOrder]
    conversations: list[HistoryConversation]


class GetEmployeeHistory(Tool):
    NAME = "get_employee_history"
    SIDE_EFFECT = False
    IDEMPOTENT = True
    TIMEOUT_SEC = 5
    MAX_CONCURRENCY = 30
    CACHE_TTL_SEC = 30
    RETRIES = 1
    BACKING_TABLES = ["orders", "conversations"]
    ALLOWED_CALLERS = ["sb-employee-info"]
    REPLICAS = 1

    Args = GetEmployeeHistoryArgs
    Result = GetEmployeeHistoryResult

    async def execute(
        self,
        args: GetEmployeeHistoryArgs,
        session: AsyncSession | None = None,
    ) -> GetEmployeeHistoryResult:
        assert session is not None, "get_employee_history requires a DB session"

        # Demo trigger: the "sensitive-" prefix runs a query that references
        # a column that does not exist on the personas table, lighting up
        # the RCA path. This is intentional — DO NOT add the column.
        if args.persona_id.startswith(SENSITIVE_PREFIX):
            sensitive_stmt = text(
                """
                SELECT id, secret_clearance
                  FROM personas
                 WHERE id::text = :pid
                """
            )
            # This will raise an UndefinedColumn error in Postgres; the
            # tool_base machinery records the span exception and re-raises.
            await session.execute(sensitive_stmt, {"pid": args.persona_id})

        pid_param = (
            int(args.persona_id) if args.persona_id.isdigit() else args.persona_id
        )

        orders_stmt = text(
            """
            SELECT id, placed_at, status, total_usd
              FROM orders
             WHERE persona_id::text = :pid
             ORDER BY placed_at DESC
             LIMIT :lim
            """
        )
        order_rows = (
            await session.execute(orders_stmt, {"pid": str(pid_param), "lim": args.limit})
        ).all()

        # Conversations table is optional in the demo data — tolerate absence.
        try:
            convs_stmt = text(
                """
                SELECT id, started_at, topic
                  FROM conversations
                 WHERE persona_id::text = :pid
                 ORDER BY started_at DESC
                 LIMIT :lim
                """
            )
            conv_rows = (
                await session.execute(convs_stmt, {"pid": str(pid_param), "lim": args.limit})
            ).all()
        except Exception:  # noqa: BLE001 — conversations table optional
            conv_rows = []

        return GetEmployeeHistoryResult(
            persona_id=args.persona_id,
            orders=[
                HistoryOrder(
                    id=r.id,
                    placed_at=r.placed_at,
                    status=r.status,
                    total_usd=float(r.total_usd),
                )
                for r in order_rows
            ],
            conversations=[
                HistoryConversation(id=r.id, started_at=r.started_at, topic=r.topic)
                for r in conv_rows
            ],
        )
