"""create_ticket — insert a new support ticket. Side-effect, NOT idempotent.

Schema sync (migrations/versions/0006_tickets.py):
  * ``tickets`` columns: id, ticket_number (NOT NULL, unique), persona_id
    (string FK to personas.persona_id), subject, body, status, priority,
    created_at. There is NO ``category`` column — older drafts inserted
    ``category`` (Postgres rejected with UndefinedColumn) AND skipped
    ``ticket_number`` (NOT-NULL constraint violation). ``category`` from
    the caller is mapped onto ``priority`` (escalation → high, otherwise
    medium) so the routing intent isn't lost.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from tool_base import Tool


class CreateTicketArgs(BaseModel):
    subject: str = Field(..., min_length=1, max_length=255)
    body: Optional[str] = Field(None, max_length=4096)
    # Caller-facing label; mapped onto the DB's ``priority`` column.
    category: Optional[str] = Field("other", max_length=64)
    persona_id: Optional[str] = Field(None, max_length=64)


class CreateTicketResult(BaseModel):
    ticket_id: int
    ticket_number: str
    status: str
    priority: str
    created_at: datetime


# Categories that justify a "high" priority in the DB.
_HIGH_PRIORITY_CATEGORIES = {"escalation", "security", "incident", "outage"}


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
        ticket_number = f"T-{uuid.uuid4().hex[:10]}"
        # persona_id is a STRING slug FK in the schema; pass through verbatim.
        priority = (
            "high"
            if (args.category or "").lower() in _HIGH_PRIORITY_CATEGORIES
            else "medium"
        )
        stmt = text(
            """
            INSERT INTO tickets
                   (ticket_number, persona_id, subject, body, status, priority, created_at)
            VALUES (:tnum, :pid, :subj, :body, 'open', :prio, :ts)
            RETURNING id, ticket_number, status, priority, created_at
            """
        )
        row = (
            await session.execute(
                stmt,
                {
                    "tnum": ticket_number,
                    "pid": args.persona_id,
                    "subj": args.subject,
                    "body": args.body,
                    "prio": priority,
                    "ts": now,
                },
            )
        ).one()
        await session.commit()
        return CreateTicketResult(
            ticket_id=int(row.id),
            ticket_number=row.ticket_number,
            status=row.status,
            priority=row.priority,
            created_at=row.created_at,
        )
