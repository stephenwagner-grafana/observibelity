"""get_ticket — fetch a single ticket by ID."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from tool_base import Tool


class GetTicketArgs(BaseModel):
    ticket_id: int = Field(..., ge=1)


class GetTicketResult(BaseModel):
    id: int
    persona_id: Optional[int] = None
    subject: str
    body: Optional[str] = None
    status: str
    category: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None


class GetTicket(Tool):
    NAME = "get_ticket"
    SIDE_EFFECT = False
    IDEMPOTENT = True
    TIMEOUT_SEC = 5
    MAX_CONCURRENCY = 50
    CACHE_TTL_SEC = 30
    RETRIES = 1
    BACKING_TABLES = ["tickets"]
    REPLICAS = 1

    Args = GetTicketArgs
    Result = GetTicketResult

    async def execute(
        self,
        args: GetTicketArgs,
        session: AsyncSession | None = None,
    ) -> GetTicketResult:
        assert session is not None, "get_ticket requires a DB session"
        stmt = text(
            """
            SELECT id, persona_id, subject, body, status, category, created_at, updated_at
              FROM tickets
             WHERE id = :tid
            """
        )
        row = (await session.execute(stmt, {"tid": args.ticket_id})).one_or_none()
        if row is None:
            raise LookupError(f"ticket {args.ticket_id} not found")
        return GetTicketResult(
            id=row.id,
            persona_id=row.persona_id,
            subject=row.subject,
            body=row.body,
            status=row.status,
            category=row.category,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )
