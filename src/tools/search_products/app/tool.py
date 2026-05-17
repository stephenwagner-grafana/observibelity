"""search_products — full-text + filter search over the NeonCart catalog."""
from __future__ import annotations

import re

from opentelemetry import trace
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from tool_base import Tool

tracer = trace.get_tracer(__name__)

# Marker the cross-gen-retrieval-drift demo uses to detect that the agent
# passed a full SKU (rather than a natural-language term) as the query.
# Captures the brand-model prefix (e.g. "1004-corsair-0072-") so the
# normalization step folds size + year + suffix down to the DDR family.
_SKU_FAMILY_RE = re.compile(
    r"(?P<prefix>\d+-[a-z0-9]+-\d+-)\d+GB\.(?P<family>DDR\d)",
    re.IGNORECASE,
)
# Year token inside the SKU body (e.g. ".DDR5-2026-1061873" -> "2026").
_SKU_YEAR_RE = re.compile(r"\.DDR\d+-(?P<year>\d{4})-", re.IGNORECASE)


class SearchProductsArgs(BaseModel):
    """Inputs for ``search_products``."""

    query: str = Field(..., min_length=1, description="ILIKE pattern matched against name + description.")
    limit: int = Field(20, ge=1, le=100, description="Maximum rows returned.")


class ProductRef(BaseModel):
    """Lightweight product summary returned by search."""

    id: int
    sku: str
    name: str
    price_usd: float


class SearchProductsResult(BaseModel):
    """Search response payload."""

    items: list[ProductRef]
    total: int


class SearchProducts(Tool):
    NAME = "search_products"
    SIDE_EFFECT = False
    IDEMPOTENT = True
    TIMEOUT_SEC = 5
    MAX_CONCURRENCY = 50
    CACHE_TTL_SEC = 60
    RETRIES = 1
    BACKING_TABLES = ["catalog_items", "categories"]
    REPLICAS = 2

    Args = SearchProductsArgs
    Result = SearchProductsResult

    async def execute(
        self,
        args: SearchProductsArgs,
        session: AsyncSession | None = None,
        usecase: str | None = None,
    ) -> SearchProductsResult:
        assert session is not None, "search_products requires a DB session"
        # Cross-gen-retrieval-drift demo: when the agent passes a full SKU
        # (containing a `<size>.DDR<n>` family marker) and the usecase tag
        # is set, run a wildcard "family normalization" lookup ranked by
        # historical_popularity. The selection deliberately crosses product
        # generations — that's the punchline. Span attributes carry the
        # story for the audience to read in Tempo.
        if usecase == "cross-gen-retrieval-drift":
            family_match = _SKU_FAMILY_RE.search(args.query)
            if family_match:
                return await self._cross_gen_drift(args, session, family_match)
        # Default behavior — the catalog stores singular product names
        # ("Keyboard", "Headphone"); callers often pass plural queries
        # ("keyboards", "headphones"). Strip a trailing "s" so the chatbot
        # doesn't have to second-guess the LLM.
        q = args.query.strip()
        if len(q) > 3 and q.lower().endswith("s") and not q.lower().endswith("ss"):
            q = q[:-1]
        stmt = text(
            """
            SELECT id, sku, name, price_usd
              FROM catalog_items
             WHERE name ILIKE :q OR description ILIKE :q
             ORDER BY id
             LIMIT :lim
            """
        )
        rows = (
            await session.execute(stmt, {"q": f"%{q}%", "lim": args.limit})
        ).all()
        items = [
            ProductRef(id=r.id, sku=r.sku, name=r.name, price_usd=float(r.price_usd))
            for r in rows
        ]
        return SearchProductsResult(items=items, total=len(items))

    async def _cross_gen_drift(
        self,
        args: SearchProductsArgs,
        session: AsyncSession,
        family_match: re.Match,
    ) -> SearchProductsResult:
        """Demo path: planted retrieval-drift bug.

        Audience reads the span and sees: full 2026 SKU went in, the lookup
        normalized it to a wildcard family key (``%64GB.DDR%``), the
        wildcard returned multiple generations of the family, the result
        set was ranked by ``historical_popularity`` (low-priced legacy DDR4
        wins), and a 2023 record was picked even though the caller asked
        about a 2026 product.
        """
        span = trace.get_current_span()
        prefix = family_match.group("prefix")
        # "Token-economy normalization" — drop the size, year, and suffix
        # tokens to derive a family wildcard. Folds every generation of the
        # product line into one lookup, which is the bug.
        normalized = f"{prefix}%.DDR%"
        year_match = _SKU_YEAR_RE.search(args.query)
        query_year = int(year_match.group("year")) if year_match else None

        # SQL the demo wants to render in the trace. The actual statement
        # parameterizes the LIKE pattern; what we expose as `db.statement`
        # is the rendered form so the audience can read it.
        rendered_sql = (
            "SELECT id, sku, name, price_usd FROM catalog_items "
            f"WHERE sku LIKE '{normalized}' "
            "ORDER BY historical_popularity DESC LIMIT 4"
        )
        stmt = text(
            """
            SELECT id, sku, name, price_usd
              FROM catalog_items
             WHERE sku LIKE :pat
             LIMIT 16
            """
        )
        rows = (await session.execute(stmt, {"pat": normalized})).all()

        # Rank by year ASC so the oldest generation wins — this is what
        # the trace labels as ``historical_popularity``. Older = more
        # historically-popular in the made-up ranker; that's the bug.
        def _row_year(sku: str) -> int:
            m = _SKU_YEAR_RE.search(sku)
            return int(m.group("year")) if m else 9999

        ranked = sorted(rows, key=lambda r: (_row_year(r.sku), r.id))[: args.limit]

        # Span attributes carry the punchline. Every key is plain enough
        # that a non-engineer can read the story top to bottom.
        if span is not None:
            span.set_attribute("retrieval.demo_mode", "cross-gen-retrieval-drift")
            span.set_attribute("retrieval.original_query", args.query)
            span.set_attribute("retrieval.normalized_query", normalized)
            span.set_attribute("retrieval.selection_strategy", "historical_popularity")
            span.set_attribute("db.system", "postgresql")
            span.set_attribute("db.statement", rendered_sql)
            span.set_attribute(
                "retrieval.candidates",
                ", ".join(r.sku for r in ranked),
            )
            if ranked:
                span.set_attribute("retrieval.selected_index", 0)
                span.set_attribute("retrieval.selected_sku", ranked[0].sku)
                selected_year = _row_year(ranked[0].sku)
                if selected_year != 9999:
                    span.set_attribute("retrieval.selected_year", selected_year)
            if query_year is not None:
                span.set_attribute("retrieval.query_year", query_year)
                if ranked:
                    sel_year = _row_year(ranked[0].sku)
                    if sel_year != 9999:
                        span.set_attribute(
                            "retrieval.year_mismatch", sel_year != query_year
                        )

        items = [
            ProductRef(id=r.id, sku=r.sku, name=r.name, price_usd=float(r.price_usd))
            for r in ranked
        ]
        return SearchProductsResult(items=items, total=len(items))
