"""create_expense — insert an expense row, gated by an approval threshold.

Side-effect, NOT idempotent (a duplicate insert duplicates the expense).

Risk surface: the approval threshold is enforced HERE — the calling
specialist cannot bypass it via prompt cleverness. Anything above the
APPROVAL_THRESHOLD_USD (default $500) is inserted with
status='pending_approval'; below the threshold it inserts as 'approved'.

Phase 2 stores expenses in a side table; if it doesn't exist yet, the
INSERT will fail and the failure shows up in the dashboards.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from tool_base import Tool

# Tunable per-deploy via env. Defaults to $500.
APPROVAL_THRESHOLD_USD = float(os.environ.get("EXPENSE_APPROVAL_THRESHOLD_USD", "500"))


class CreateExpenseArgs(BaseModel):
    persona_id: str = Field(..., min_length=1, max_length=64)
    amount_usd: float = Field(..., gt=0, le=1_000_000)
    category: str = Field(..., min_length=1, max_length=64)
    description: Optional[str] = Field(None, max_length=2048)
    receipt_url: Optional[str] = Field(None, max_length=2048)


class CreateExpenseResult(BaseModel):
    expense_id: int
    persona_id: str
    amount_usd: float
    status: str
    created_at: datetime


class CreateExpense(Tool):
    NAME = "create_expense"
    SIDE_EFFECT = True
    IDEMPOTENT = False
    TIMEOUT_SEC = 5
    MAX_CONCURRENCY = 20
    CACHE_TTL_SEC = 0
    RETRIES = 0
    BACKING_TABLES = ["expenses"]
    ALLOWED_CALLERS = ["sb-expense-helper"]
    REPLICAS = 1

    Args = CreateExpenseArgs
    Result = CreateExpenseResult

    async def execute(
        self,
        args: CreateExpenseArgs,
        session: AsyncSession | None = None,
    ) -> CreateExpenseResult:
        assert session is not None, "create_expense requires a DB session"
        now = datetime.now(tz=timezone.utc)
        # Approval gate — ALWAYS evaluated here, regardless of caller args.
        status = (
            "pending_approval"
            if args.amount_usd >= APPROVAL_THRESHOLD_USD
            else "approved"
        )
        pid: Optional[int] = (
            int(args.persona_id) if args.persona_id.isdigit() else None
        )
        stmt = text(
            """
            INSERT INTO expenses
                   (persona_id, amount_usd, category, description, receipt_url, status, created_at)
            VALUES (:pid, :amt, :cat, :desc, :rcpt, :st, :ts)
            RETURNING id, status, created_at
            """
        )
        row = (
            await session.execute(
                stmt,
                {
                    "pid": pid,
                    "amt": args.amount_usd,
                    "cat": args.category,
                    "desc": args.description,
                    "rcpt": args.receipt_url,
                    "st": status,
                    "ts": now,
                },
            )
        ).one()
        await session.commit()
        return CreateExpenseResult(
            expense_id=int(row.id),
            persona_id=args.persona_id,
            amount_usd=args.amount_usd,
            status=row.status,
            created_at=row.created_at,
        )
