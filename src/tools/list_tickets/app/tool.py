"""list_tickets — return recent tickets for a persona, ordered by created_at desc.

Schema sync (migrations/versions/0006_tickets.py): tickets has ``priority``
(NOT ``category``). The response's ``category`` field is now an alias for
``priority`` so existing callers keep working — older drafts queried a
non-existent ``category`` column and 500'd.
"""
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
    ticket_number: str
    subject: str
    status: str
    # Sourced from the DB ``priority`` column for response-shape stability.
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
            SELECT id, ticket_number, subject, status,
                   priority AS category, created_at
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
                    ticket_number=r.ticket_number,
                    subject=r.subject,
                    status=r.status,
                    category=r.category,
                    created_at=r.created_at,
                )
                for r in rows
            ],
        )
