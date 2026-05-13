"""create_ticket — insert a new support ticket. Side-effect, NOT idempotent."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from tool_base import Tool


class CreateTicketArgs(BaseModel):
    subject: str = Field(..., min_length=1, max_length=255)
    body: Optional[str] = Field(None, max_length=4096)
    category: Optional[str] = Field("other", max_length=64)
    persona_id: Optional[str] = Field(None, max_length=64)


class CreateTicketResult(BaseModel):
    ticket_id: int
    status: str
    created_at: datetime


class CreateTicket(Tool):
    NAME = "create_ticket"
    SIDE_EFFECT = True
    IDEMPOTENT = False
    TIMEOUT_SEC = 5
    MAX_CONCURRENCY = 20
    CACHE_TTL_SEC = 0
    RETRIES = 0  # side-effect, non-idempotent → no retries
    BACKING_TABLES = ["tickets"]
    REPLICAS = 1

    Args = CreateTicketArgs
    Result = CreateTicketResult

    async def execute(
        self,
        args: CreateTicketArgs,
        session: AsyncSession | None = None,
    ) -> CreateTicketResult:
        assert session is not None, "create_ticket requires a DB session"
        now = datetime.now(tz=timezone.utc)
        pid: Optional[int] = None
        if args.persona_id and args.persona_id.isdigit():
            pid = int(args.persona_id)
        stmt = text(
            """
            INSERT INTO tickets
                   (persona_id, subject, body, status, category, created_at)
            VALUES (:pid, :subj, :body, 'open', :cat, :ts)
            RETURNING id, status, created_at
            """
        )
        row = (
            await session.execute(
                stmt,
                {
                    "pid": pid,
                    "subj": args.subject,
                    "body": args.body,
                    "cat": args.category or "other",
                    "ts": now,
                },
            )
        ).one()
        await session.commit()
        return CreateTicketResult(
            ticket_id=int(row.id),
            status=row.status,
            created_at=row.created_at,
        )
