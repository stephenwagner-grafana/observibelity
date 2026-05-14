"""add_to_cart — record an agent's intent to add an item to a customer's cart.

This tool is the AGENT-VISIBLE side of the add-to-cart action — the actual
cookie / cart-state update happens in the neoncart frontend when the user
clicks an Add button. We model it as a tool so:

  * Sigil sees `gen_ai.tool.name="add_to_cart"` for every agent-initiated
    add, which lets dashboards track "how often did the gift-finder
    actually convert" without joining HTTP logs.
  * Loadgen can drive end-to-end "search → add → place_order" sequences
    against a single LLM specialist.
  * The cart-add count emits as a Prometheus counter for use cases like
    "conversion rate by model" or "cart-add rate by agent".

The tool intentionally doesn't touch postgres — the demo's cart lives in a
HTTP cookie (one less migration). If a future cart_items table lands, swap
this implementation for a real INSERT without changing the agent surface.
"""
from __future__ import annotations

import logging
from typing import ClassVar

from pydantic import BaseModel, Field
from prometheus_client import Counter

from tool_base import Tool

log = logging.getLogger(__name__)


ADD_COUNTER = Counter(
    "nc_cart_add_total",
    "Cart-add events initiated by an agent via the add_to_cart tool.",
    ["caller", "sku"],
)


class AddToCartArgs(BaseModel):
    """Inputs for ``add_to_cart``."""

    product_id: int = Field(..., gt=0, description="catalog_items.id of the product to add.")
    sku: str | None = Field(default=None, max_length=64, description="Optional SKU echo for log readability.")
    qty: int = Field(default=1, ge=1, le=20)
    persona_id: str | None = Field(default=None, description="Shopper persona (echoed back, not validated).")
    note: str | None = Field(default=None, max_length=200, description="Optional short reason the agent chose this item.")


class AddToCartResult(BaseModel):
    """Result echo. Always status=queued — the frontend confirms the cookie write."""

    product_id: int
    sku: str | None = None
    qty: int
    status: str = "queued"


class AddToCart(Tool):
    NAME: ClassVar[str] = "add_to_cart"
    SIDE_EFFECT: ClassVar[bool] = True
    IDEMPOTENT: ClassVar[bool] = False
    TIMEOUT_SEC: ClassVar[int] = 3
    MAX_CONCURRENCY: ClassVar[int] = 50
    CACHE_TTL_SEC: ClassVar[int] = 0
    RETRIES: ClassVar[int] = 0
    BACKING_TABLES: ClassVar[list[str]] = []
    REPLICAS: ClassVar[int] = 1

    Args = AddToCartArgs
    Result = AddToCartResult

    async def execute(self, args: AddToCartArgs, session=None) -> AddToCartResult:
        caller = "unknown"
        # ALLOWED_CALLERS is empty so we don't need to enforce; we only
        # record it for Prometheus.  X-Caller is captured in the FastAPI
        # wrapper and surfaces via OTel attributes, not here.
        ADD_COUNTER.labels(caller=caller, sku=args.sku or "").inc(args.qty)
        log.info(
            "add_to_cart agent intent product_id=%s sku=%s qty=%s persona=%s note=%s",
            args.product_id, args.sku, args.qty, args.persona_id, args.note,
        )
        return AddToCartResult(
            product_id=args.product_id,
            sku=args.sku,
            qty=args.qty,
            status="queued",
        )
