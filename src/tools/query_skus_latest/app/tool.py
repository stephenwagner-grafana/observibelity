"""query_skus_latest — resolve a SKU regex pattern to latest-SKU candidates.

Second hop of the multi-hop retrieval-drift demo. The upstream specialist
has taken a product.id like ``1004-corsair-0072-64GB.DDR5-2026-1061873`` and
replaced its version-bearing tokens with ``.`` wildcards (e.g.
``1004-corsair-0072-64GB\\.DDR.-....-.......``), then handed that pattern
to this tool to "look up the latest SKUs for the product."

The catalog has had an ``is_latest_SKU_for_product`` flag added in a parallel
migration. The data bug — and the audience-readable punchline — is that the
flag was mis-backfilled, so a wildcard regex match plus an
``is_latest_SKU_for_product = TRUE`` filter still returns rows from the
*wrong* generation (older year). The selected row is index 0 ("we weren't
expecting an array"), and the span attributes line the candidate SKUs up in
a column you can eye-scan in Tempo.
"""
from __future__ import annotations

import re

from opentelemetry import trace
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from tool_base import Tool

tracer = trace.get_tracer(__name__)

# Year suffix marker — pull the trailing 4-digit year off either the
# original product.id or any candidate SKU. The catalog's verbatim screenshot
# format puts the year at the tail (``...-2026-1061873`` / ``...-2023-...``)
# preceded by a literal ``.``. Capture the year only when it follows that ``.``.
_YEAR_TAIL_RE = re.compile(r"\.(20\d{2})$")


def _extract_year(value: str | None) -> int | None:
    """Return the trailing ``.YYYY`` year as int, or None if absent."""
    if not value:
        return None
    m = _YEAR_TAIL_RE.search(value)
    return int(m.group(1)) if m else None


class QuerySkusLatestArgs(BaseModel):
    """Inputs for ``query_skus_latest``."""

    pattern: str = Field(
        ...,
        min_length=1,
        max_length=512,
        description="Regex pattern to match against the sku column.",
    )
    queried_product_id: str | None = Field(
        None,
        max_length=200,
        description=(
            "The full original product.id the upstream caller was actually "
            "looking for. Used only for span attribution."
        ),
    )
    limit: int = Field(4, ge=1, le=16)


class ProductRef(BaseModel):
    """Lightweight product summary returned by the SKU lookup."""

    id: int
    sku: str
    name: str
    price_usd: float


class QuerySkusLatestResult(BaseModel):
    """Result payload for ``query_skus_latest``."""

    items: list[ProductRef]
    total: int


class QuerySkusLatest(Tool):
    NAME = "query_skus_latest"
    SIDE_EFFECT = False
    IDEMPOTENT = True
    TIMEOUT_SEC = 5
    MAX_CONCURRENCY = 50
    CACHE_TTL_SEC = 60
    RETRIES = 1
    BACKING_TABLES = ["catalog_items"]
    REPLICAS = 2

    Args = QuerySkusLatestArgs
    Result = QuerySkusLatestResult

    async def execute(
        self,
        args: QuerySkusLatestArgs,
        session: AsyncSession | None = None,
        usecase: str | None = None,
    ) -> QuerySkusLatestResult:
        """Run the regex lookup. ``usecase`` is accepted (so the base class
        forwards the header per its introspection contract) but ignored —
        this tool's storytelling lives entirely in span attributes.
        """
        del usecase  # explicit: behavior does not branch on usecase
        assert session is not None, "query_skus_latest requires a DB session"

        # The column name is mixed-case (`is_latest_SKU_for_product`) and
        # Postgres folds unquoted identifiers to lowercase — quote it so the
        # match is literal.
        #
        # "Best deals" ordering — sort by price ASC so the cheapest in-stock
        # variant surfaces first. That's the planted compound-bug shape: a
        # stale `is_latest_SKU_for_product` flag on EOL stock, plus a price
        # sort, means a 2023 end-of-life record beats the actual 2026
        # flagship for a price-anchored lookup.
        stmt = text(
            """
            SELECT id, sku, name, price_usd
              FROM catalog_items
             WHERE sku ~ :pattern
               AND "is_latest_SKU_for_product" = TRUE
             ORDER BY price_usd ASC
             LIMIT 16
            """
        )
        rows = (
            await session.execute(stmt, {"pattern": args.pattern})
        ).all()
        items = [
            ProductRef(
                id=r.id,
                sku=r.sku,
                name=r.name,
                price_usd=float(r.price_usd),
            )
            for r in rows[: args.limit]
        ]

        # ── Span attributes carry the punchline ──────────────────────────
        # Audience reads in Tempo: a pattern was built from the original
        # product.id, four near-identical SKUs came back, the first one was
        # picked (we weren't expecting an array), and its year doesn't match
        # the queried product's year. The `is_latest_SKU_for_product` flag
        # that's supposed to disambiguate is True — the data bug.
        span = trace.get_current_span()
        if span is not None:
            if args.queried_product_id:
                span.set_attribute(
                    "retrieval.queried_product_id", args.queried_product_id
                )
            span.set_attribute("retrieval.pattern_used", args.pattern)
            # Up to 4 candidate SKUs surfaced as a flat column so the audience
            # can eye-scan them. We always set up to 4 slots (1-indexed for
            # readability) and only emit ones that exist.
            for idx, item in enumerate(items[:4], start=1):
                span.set_attribute(f"retrieval.candidate.{idx}", item.sku)
            span.set_attribute("retrieval.candidate_count", len(items))
            # Index 0 is always the "selected" row — the bug is that we
            # weren't expecting an array at all, but here we are picking the
            # head off the top.
            span.set_attribute("retrieval.selected_index", 0)
            if items:
                selected = items[0]
                span.set_attribute("retrieval.selected_sku", selected.sku)
                span.set_attribute(
                    "retrieval.selected_price_usd", float(selected.price_usd)
                )
                selected_year = _extract_year(selected.sku)
                queried_year = _extract_year(args.queried_product_id)
                if selected_year is not None:
                    span.set_attribute("retrieval.selected_year", selected_year)
                if queried_year is not None:
                    span.set_attribute("retrieval.queried_year", queried_year)
                if selected_year is not None and queried_year is not None:
                    span.set_attribute(
                        "retrieval.year_mismatch",
                        selected_year != queried_year,
                    )
            # The flag the migration was *supposed* to gate on. We hard-
            # code True here because every row that came back already had
            # it set — that's the planted data bug.
            span.set_attribute("retrieval.is_latest_SKU_for_product", True)

        return QuerySkusLatestResult(items=items, total=len(items))
