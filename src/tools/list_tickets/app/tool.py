"""list_tickets — return recent tickets for a persona, ordered by created_at desc."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from tool_base import Tool


class ListTicketsArgs(BaseModel):
    persona_id: str = Field(..., min_length=1, max_length=64)
    limit: int = Field(20, ge=1, le=100)
    status: Optional[str] = Field(None, description="Filter by status (open/closed/pending).")


class TicketRef(BaseModel):
    id: int
    subject: str
    status: str
    category: Optional[str] = None
    created_at: datetime


class ListTicketsResult(BaseModel):
    persona_id: str
    tickets: list[TicketRef]


class ListTickets(Tool):
    NAME = "list_tickets"
    SIDE_EFFECT = False
    IDEMPOTENT = True
    TIMEOUT_SEC = 5
    MAX_CONCURRENCY = 30
    CACHE_TTL_SEC = 15
    RETRIES = 1
    BACKING_TABLES = ["tickets"]
    REPLICAS = 1

    Args = ListTicketsArgs
    Result = ListTicketsResult

    async def execute(
        self,
        args: ListTicketsArgs,
        session: AsyncSession | None = None,
    ) -> ListTicketsResult:
        assert session is not None, "list_tickets requires a DB session"
        params: dict = {"pid": args.persona_id, "lim": args.limit}
        where = "persona_id = :pid"
        if args.status:
            where += " AND status = :st"
            params["st"] = args.status
        stmt = text(
            f"""
            SELECT id, subject, status, category, created_at
              FROM tickets
             WHERE {where}
             ORDER BY created_at DESC
             LIMIT :lim
            """
        )
        rows = (await session.execute(stmt, params)).all()
        return ListTicketsResult(
            persona_id=args.persona_id,
            tickets=[
                TicketRef(
                    id=r.id,
                    subject=r.subject,
                    status=r.status,
                    category=r.category,
                    created_at=r.created_at,
                )
                for r in rows
            ],
        )
