"""update_ticket — modify status/body of an existing ticket. Side-effect, idempotent."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from tool_base import Tool


class UpdateTicketArgs(BaseModel):
    ticket_id: int = Field(..., ge=1)
    status: Optional[str] = Field(None, max_length=32)
    body: Optional[str] = Field(None, max_length=4096)


class UpdateTicketResult(BaseModel):
    ticket_id: int
    status: Optional[str]
    updated_at: datetime


class UpdateTicket(Tool):
    NAME = "update_ticket"
    SIDE_EFFECT = True
    IDEMPOTENT = True  # same status/body update is safe to retry
    TIMEOUT_SEC = 5
    MAX_CONCURRENCY = 20
    CACHE_TTL_SEC = 0
    RETRIES = 1
    BACKING_TABLES = ["tickets"]
    REPLICAS = 1

    Args = UpdateTicketArgs
    Result = UpdateTicketResult

    async def execute(
        self,
        args: UpdateTicketArgs,
        session: AsyncSession | None = None,
    ) -> UpdateTicketResult:
        assert session is not None, "update_ticket requires a DB session"
        sets = ["updated_at = :ts"]
        params: dict = {"tid": args.ticket_id, "ts": datetime.now(tz=timezone.utc)}
        if args.status is not None:
            sets.append("status = :st")
            params["st"] = args.status
        if args.body is not None:
            sets.append("body = :body")
            params["body"] = args.body
        if len(sets) == 1:
            raise ValueError("nothing to update — pass status or body")

        stmt = text(
            f"""
            UPDATE tickets
               SET {", ".join(sets)}
             WHERE id = :tid
            RETURNING id, status, updated_at
            """
        )
        row = (await session.execute(stmt, params)).one_or_none()
        if row is None:
            raise LookupError(f"ticket {args.ticket_id} not found")
        await session.commit()
        return UpdateTicketResult(
            ticket_id=int(row.id),
            status=row.status,
            updated_at=row.updated_at,
        )
