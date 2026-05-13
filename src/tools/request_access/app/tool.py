"""request_access — file a ticket requesting access to a resource.

Side-effect, idempotent (filing the same access request twice in quick
succession is harmless — the duplicate is closed by the IT team). Reuses
the tickets table with category='access-request'.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from tool_base import Tool


class RequestAccessArgs(BaseModel):
    persona_id: str = Field(..., min_length=1, max_length=64)
    resource: str = Field(..., min_length=1, max_length=255)
    justification: Optional[str] = Field(None, max_length=2048)


class RequestAccessResult(BaseModel):
    ticket_id: int
    resource: str
    status: str
    created_at: datetime


class RequestAccess(Tool):
    NAME = "request_access"
    SIDE_EFFECT = True
    IDEMPOTENT = True
    TIMEOUT_SEC = 5
    MAX_CONCURRENCY = 20
    CACHE_TTL_SEC = 0
    RETRIES = 1
    BACKING_TABLES = ["tickets"]
    ALLOWED_CALLERS = ["sb-it-troubleshoot", "sb-escalator"]
    REPLICAS = 1

    Args = RequestAccessArgs
    Result = RequestAccessResult

    async def execute(
        self,
        args: RequestAccessArgs,
        session: AsyncSession | None = None,
    ) -> RequestAccessResult:
        assert session is not None, "request_access requires a DB session"
        now = datetime.now(tz=timezone.utc)
        pid: Optional[int] = (
            int(args.persona_id) if args.persona_id.isdigit() else None
        )
        body = (
            f"Resource requested: {args.resource}\n"
            f"Justification: {args.justification or '(none provided)'}"
        )
        stmt = text(
            """
            INSERT INTO tickets
                   (persona_id, subject, body, status, category, created_at)
            VALUES (:pid, :subj, :body, 'open', 'access-request', :ts)
            RETURNING id, status, created_at
            """
        )
        row = (
            await session.execute(
                stmt,
                {
                    "pid": pid,
                    "subj": f"Access request: {args.resource}",
                    "body": body,
                    "ts": now,
                },
            )
        ).one()
        await session.commit()
        return RequestAccessResult(
            ticket_id=int(row.id),
            resource=args.resource,
            status=row.status,
            created_at=row.created_at,
        )
