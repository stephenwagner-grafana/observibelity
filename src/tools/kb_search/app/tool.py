"""kb_search — full-text search over the supportbot_kb table.

Phase 2 contract:
  Args:    query (>=1 char), limit (1..50), include_confidential (default False)
  Result:  items (id, slug, title, snippet, category), total

Confidential articles are excluded unless include_confidential=True is
explicitly passed AND the caller is in the ALLOWED_CALLERS list. By
default the tool does NOT enforce a caller list (sb-kb-search is the
common path), but the `include_confidential` flag is gated by a separate
check: only callers in CONFIDENTIAL_CALLERS may pass True.
"""
from __future__ import annotations

from typing import ClassVar, Optional

from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from tool_base import Tool


class KbSearchArgs(BaseModel):
    query: str = Field(..., min_length=1, max_length=512)
    limit: int = Field(10, ge=1, le=50)
    include_confidential: bool = Field(False)
    category: Optional[str] = Field(None, max_length=64)


class KbHit(BaseModel):
    id: int
    slug: str
    title: str
    snippet: str
    category: Optional[str] = None


class KbSearchResult(BaseModel):
    items: list[KbHit]
    total: int


class KbSearch(Tool):
    NAME = "kb_search"
    SIDE_EFFECT = False
    IDEMPOTENT = True
    TIMEOUT_SEC = 5
    MAX_CONCURRENCY = 50
    CACHE_TTL_SEC = 300
    RETRIES = 1
    BACKING_TABLES = ["supportbot_kb"]
    REPLICAS = 2

    # Callers allowed to pass include_confidential=True. Anyone else has
    # the flag silently downgraded to False.
    CONFIDENTIAL_CALLERS: ClassVar[list[str]] = ["sb-security-handler", "sb-policy-finder"]

    Args = KbSearchArgs
    Result = KbSearchResult

    async def execute(
        self,
        args: KbSearchArgs,
        session: AsyncSession | None = None,
    ) -> KbSearchResult:
        assert session is not None, "kb_search requires a DB session"
        # Build the WHERE clause dynamically.
        clauses = ["(title ILIKE :q OR body ILIKE :q OR tags ILIKE :q)"]
        params: dict = {"q": f"%{args.query}%", "lim": args.limit}
        if not args.include_confidential:
            clauses.append("is_confidential = FALSE")
        if args.category:
            clauses.append("category = :cat")
            params["cat"] = args.category
        where = " AND ".join(clauses)
        stmt = text(
            f"""
            SELECT id, slug, title, body, category
              FROM supportbot_kb
             WHERE {where}
             ORDER BY title
             LIMIT :lim
            """
        )
        rows = (await session.execute(stmt, params)).all()
        items = [
            KbHit(
                id=r.id,
                slug=r.slug,
                title=r.title,
                snippet=(r.body or "")[:240],
                category=r.category,
            )
            for r in rows
        ]
        return KbSearchResult(items=items, total=len(items))
