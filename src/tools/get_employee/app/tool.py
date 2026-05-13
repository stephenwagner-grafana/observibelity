"""get_employee — look up an employee's profile by persona_id.

Risk surface: this is the canonical data-exfil chokepoint. The tool's
ALLOWED_CALLERS list restricts which specialists may call it. When the
demo's offender persona ("Tim") tries to coax the bot into looking up
*other* employees' profiles, the proper defence is:

  1. The specialist (sb-employee-info / sb-hr-info) rewrites the
     persona_id arg to the requester's. (See those specialists' code.)
  2. This tool only accepts calls from approved specialists.

If both fail, the dashboard's data-theft-tim evaluator fires.

Schema sync (migrations/versions/0001_initial.py): personas has
``persona_id`` (string slug), ``archetype``, and ``offender_pattern`` but
no ``department`` column. Older drafts SELECTed ``department`` and 500'd
with UndefinedColumn on every call. ``department`` is now derived from
``archetype`` for backwards compatibility with the response shape.
"""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from tool_base import Tool


class GetEmployeeArgs(BaseModel):
    persona_id: str = Field(..., min_length=1, max_length=64)


class GetEmployeeResult(BaseModel):
    id: int
    persona_id: str
    name: str
    email: Optional[str] = None
    role: Optional[str] = None
    # Department isn't a column in the schema — derived from archetype.
    department: Optional[str] = None


class GetEmployee(Tool):
    NAME = "get_employee"
    SIDE_EFFECT = False
    IDEMPOTENT = True
    TIMEOUT_SEC = 5
    MAX_CONCURRENCY = 50
    CACHE_TTL_SEC = 60
    RETRIES = 1
    BACKING_TABLES = ["personas"]
    ALLOWED_CALLERS = [
        "sb-employee-info",
        "sb-hr-info",
        "sb-policy-finder",
        "sb-router",
    ]
    REPLICAS = 1

    Args = GetEmployeeArgs
    Result = GetEmployeeResult

    async def execute(
        self,
        args: GetEmployeeArgs,
        session: AsyncSession | None = None,
    ) -> GetEmployeeResult:
        assert session is not None, "get_employee requires a DB session"
        params: dict
        # personas.id is the integer surrogate PK; persona_id is the slug.
        # Match against persona_id (slug) first, falling back to PK or email.
        if args.persona_id.isdigit():
            stmt = text(
                "SELECT id, persona_id, name, email, role, archetype "
                "FROM personas WHERE id = :pid"
            )
            params = {"pid": int(args.persona_id)}
        else:
            stmt = text(
                "SELECT id, persona_id, name, email, role, archetype "
                "FROM personas "
                "WHERE persona_id = :pid OR email = :pid OR name = :pid"
            )
            params = {"pid": args.persona_id}
        row = (await session.execute(stmt, params)).one_or_none()
        if row is None:
            raise LookupError(f"persona {args.persona_id} not found")
        return GetEmployeeResult(
            id=int(row.id),
            persona_id=row.persona_id,
            name=row.name,
            email=row.email,
            role=row.role,
            department=row.archetype,
        )
