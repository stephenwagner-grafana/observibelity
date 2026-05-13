"""kb_search — full-text search over the supportbot_kb table.

Phase 2 contract:
  Args:    query (>=1 char), limit (1..50), include_confidential (default False)
  Result:  items (id, slug, title, snippet, category), total

Schema sync (migrations/versions/0007_supportbot_kb.py): supportbot_kb has
slug, title, body, tags, created_at — NO ``category`` or ``is_confidential``
columns. The "confidential" flag is encoded in ``tags`` (a ';'-separated
list); category is the first tag. Older drafts of this tool referenced
the column names directly and 500'd with UndefinedColumn.

Confidential articles are excluded unless include_confidential=True is
explicitly passed AND the caller is in CONFIDENTIAL_CALLERS.
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
        clauses = [
            "(title ILIKE :q OR body ILIKE :q OR COALESCE(tags, '') ILIKE :q)"
        ]
        params: dict = {"q": f"%{args.query}%", "lim": args.limit}
        if not args.include_confidential:
            # Confidentiality is stored in the tags string.
            clauses.append("(tags IS NULL OR tags NOT ILIKE '%confidential%')")
        if args.category:
            # Category = the first tag in a ';'-separated list.
            clauses.append(
                "(tags = :cat "
                "OR tags ILIKE :catprefix "
                "OR tags ILIKE :catmid "
                "OR tags ILIKE :catsuffix)"
            )
            params["cat"] = args.category
            params["catprefix"] = f"{args.category};%"
            params["catmid"] = f"%;{args.category};%"
            params["catsuffix"] = f"%;{args.category}"
        where = " AND ".join(clauses)
        stmt = text(
            f"""
            SELECT id, slug, title, body, tags
              FROM supportbot_kb
             WHERE {where}
             ORDER BY title
             LIMIT :lim
            """
        )
        rows = (await session.execute(stmt, params)).all()
        items: list[KbHit] = []
        for r in rows:
            # Derive category from the first ';'-separated tag.
            tags_str = r.tags or ""
            first_tag = tags_str.split(";")[0].strip() if tags_str else None
            items.append(
                KbHit(
                    id=r.id,
                    slug=r.slug,
                    title=r.title,
                    snippet=(r.body or "")[:240],
                    category=first_tag or None,
                )
            )
        return KbSearchResult(items=items, total=len(items))
