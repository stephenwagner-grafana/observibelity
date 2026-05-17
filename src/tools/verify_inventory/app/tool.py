"""verify_inventory — LLM-using SKU shim with a bit-budgeted forwarding prompt.

Sits between search_products and nc-best-deals in the cross-gen-retrieval-
drift demo. The agent passes the full long product SKU (the user's
intended product.id). This tool asks the gateway to "summarize the SKU
for downstream forwarding to best-deals", with a system prompt that
deliberately constrains the LLM to <=32 characters + literal "..." — the
planted bit-budget bug. The truncated SKU is then HTTP-posted to
nc-best-deals/v1/run, which builds a regex pattern (treating `.` as a
digit class, the next bug in the chain) and queries the catalog.

The audience reads two side-by-side spans:
  - tool.verify_inventory.gateway_call    (truncation bug)
  - specialist.nc-best-deals.lookup       (dot-as-digit-class bug)
"""
from __future__ import annotations

import logging
import os
import re
from typing import Any, ClassVar

import httpx
from opentelemetry import trace
from pydantic import BaseModel, Field

from tool_base import Tool

log = logging.getLogger(__name__)
log.setLevel(os.getenv("LOG_LEVEL", "INFO"))
tracer = trace.get_tracer(__name__)


# How aggressively to truncate the SKU before forwarding to nc-best-deals.
# The literal value lives here so the planted bug is one constant the
# audience can point to in code review. 32 chars + "..." == 35 chars on
# the wire — the "best-deals tier" "doesn't accept anything longer".
_BUDGET_CHARS = 32
_TRUNCATION_SUFFIX = "..."

# Regex extracting just the truncated head if the LLM wandered off the
# spec and wrote something verbose. Used as the deterministic fallback.
_TRUNCATED_FALLBACK_RE = re.compile(r"^([\w\-.]{1," + str(_BUDGET_CHARS) + r"})")


SYSTEM_PROMPT_TRUNCATE = (
    "You are a SKU-forwarding proxy for an inventory verification step. "
    "The downstream best-deals service has a strict 32-character input "
    "budget on the SKU it accepts. Your job is to TRUNCATE the SKU the "
    "caller passes you to the first 32 characters and append the literal "
    "three-character suffix \"...\" to indicate truncation.\n"
    "\n"
    "Examples:\n"
    "  Input:  ABC123-EXAMPLE-LONG-SKU-1234567890abcdef\n"
    "  Output: ABC123-EXAMPLE-LONG-SKU-12345678...\n"
    "\n"
    "  Input:  0012.FOO.0249.BARBAZQUUX.999.HELLO-WORLD\n"
    "  Output: 0012.FOO.0249.BARBAZQUUX.999.HEL...\n"
    "\n"
    "Return ONLY the truncated SKU. No commentary, no JSON envelope, no "
    "explanation. Just the 35-character string (32 chars + \"...\")."
)


LLM_GATEWAY_URL = os.environ.get("LLM_GATEWAY_URL", "http://llm-gateway:80")
NC_BEST_DEALS_URL = os.environ.get(
    "NC_BEST_DEALS_URL", "http://nc-best-deals/v1/run"
)


class VerifyInventoryArgs(BaseModel):
    """Inputs for ``verify_inventory``."""

    product_id: str = Field(
        ..., min_length=1, max_length=200,
        description="Full product.id (long SKU string) to verify.",
    )
    product_name: str | None = Field(
        default=None, max_length=200,
        description="Optional human-readable product name for log readability.",
    )


class VerifyInventoryResult(BaseModel):
    """Outcome of the inventory-verify hop."""

    product_id: str
    truncated_sku: str
    selected_sku: str | None = None
    selected_price_usd: float | None = None
    best_deals_reply: str | None = None
    source: str = "is_latest_SKU_for_product"


class VerifyInventory(Tool):
    NAME: ClassVar[str] = "verify_inventory"
    SIDE_EFFECT: ClassVar[bool] = False
    IDEMPOTENT: ClassVar[bool] = True
    TIMEOUT_SEC: ClassVar[int] = 30
    MAX_CONCURRENCY: ClassVar[int] = 20
    CACHE_TTL_SEC: ClassVar[int] = 0
    RETRIES: ClassVar[int] = 0
    BACKING_TABLES: ClassVar[list[str]] = []
    REPLICAS: ClassVar[int] = 1

    Args = VerifyInventoryArgs
    Result = VerifyInventoryResult

    def __init__(self) -> None:
        super().__init__()
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(connect=5.0, read=25.0, write=5.0, pool=5.0),
            limits=httpx.Limits(max_connections=50, max_keepalive_connections=10),
        )

    async def execute(
        self,
        args: VerifyInventoryArgs,
        session=None,
        usecase: str | None = None,
    ) -> VerifyInventoryResult:
        """Two-step: (1) buggy LLM truncates SKU, (2) HTTP POST to nc-best-deals."""
        span = trace.get_current_span()
        if span is not None:
            span.set_attribute("verify.original_sku", args.product_id)
            span.set_attribute("verify.budget_chars", _BUDGET_CHARS)

        # Step 1: gateway call with the truncating system prompt.
        truncated = await self._truncate_via_llm(args.product_id, usecase)
        if span is not None:
            span.set_attribute("verify.truncated_sku", truncated)
            span.set_attribute(
                "verify.truncation_ratio",
                round(len(truncated) / max(len(args.product_id), 1), 3),
            )

        # Step 2: forward the truncated SKU to nc-best-deals.
        bd_reply, selected_sku, selected_price = await self._call_best_deals(
            truncated_sku=truncated,
            full_product_id=args.product_id,
            usecase=usecase,
        )
        if span is not None:
            if selected_sku:
                span.set_attribute("verify.selected_sku", selected_sku)
            if selected_price is not None:
                span.set_attribute("verify.selected_price_usd", float(selected_price))

        return VerifyInventoryResult(
            product_id=args.product_id,
            truncated_sku=truncated,
            selected_sku=selected_sku,
            selected_price_usd=selected_price,
            best_deals_reply=bd_reply,
        )

    async def _truncate_via_llm(
        self, product_id: str, usecase: str | None
    ) -> str:
        """Ask the gateway for a 32-char + "..." truncation of the SKU.

        The system prompt is the audience-readable bug — token budgets
        like this happen in real systems, and asking an LLM to mechanically
        cut a string is a textbook "smells fine, fails subtly" pattern.
        """
        payload: dict[str, Any] = {
            "specialist": "verify_inventory",
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT_TRUNCATE},
                {"role": "user", "content": product_id},
            ],
            "max_tokens": 80,
            "ai_o11y": {
                "usecase": usecase,
                "traffic_origin": "interactive" if usecase else None,
            },
        }
        try:
            with tracer.start_as_current_span("verify_inventory.gateway_truncate") as s:
                s.set_attribute("ai_o11y.specialist", "verify_inventory")
                if usecase:
                    s.set_attribute("ai_o11y.usecase", usecase)
                resp = await self._client.post(
                    f"{LLM_GATEWAY_URL}/v1/complete",
                    json=payload,
                )
                resp.raise_for_status()
                data = resp.json()
                content = (data.get("content") or "").strip()
                # Strip backticks / quotes the LLM sometimes wraps around.
                content = content.strip("`").strip('"').strip("'").strip()
        except Exception as exc:  # noqa: BLE001 — fall back deterministically
            log.warning("gateway truncate call failed (%s); using fallback", exc)
            content = ""

        # Deterministic fallback if the LLM gave us something that doesn't
        # match the spec — this is the part that keeps the demo stable
        # under provider hiccups. The PROMPT is the bug, the FALLBACK is
        # the safety net.
        if not content or len(content) > _BUDGET_CHARS + len(_TRUNCATION_SUFFIX) + 4:
            content = product_id[:_BUDGET_CHARS] + _TRUNCATION_SUFFIX
        elif not content.endswith(_TRUNCATION_SUFFIX):
            # LLM forgot the ellipsis — append it so the downstream pattern
            # builder sees the truncation marker.
            head = content[:_BUDGET_CHARS]
            content = head + _TRUNCATION_SUFFIX
        return content

    async def _call_best_deals(
        self,
        truncated_sku: str,
        full_product_id: str,
        usecase: str | None,
    ) -> tuple[str | None, str | None, float | None]:
        """POST to nc-best-deals and pull out the selected SKU + price."""
        payload: dict[str, Any] = {
            "message": (
                "Verify the most up-to-date SKU for this product.id "
                "(truncated for the 32-char input budget)."
            ),
            "usecase": usecase,
            "context": {
                "product_id": full_product_id,
                "truncated_sku": truncated_sku,
                "source": "verify_inventory",
            },
        }
        try:
            with tracer.start_as_current_span("verify_inventory.call_best_deals") as s:
                s.set_attribute("ai_o11y.tool", "verify_inventory")
                s.set_attribute("verify.downstream", "nc-best-deals")
                if usecase:
                    s.set_attribute("ai_o11y.usecase", usecase)
                resp = await self._client.post(
                    NC_BEST_DEALS_URL,
                    json=payload,
                    headers={
                        "X-Caller": "verify_inventory",
                    },
                )
                resp.raise_for_status()
                bd = resp.json() or {}
        except Exception as exc:  # noqa: BLE001
            log.warning("best-deals call failed: %s", exc)
            return None, None, None

        reply = bd.get("reply")
        selected_sku, selected_price = _parse_best_deals_reply(reply)
        return reply, selected_sku, selected_price


_REPLY_SKU_RE = re.compile(r"selected_sku\s*=\s*([^,\s]+)")
_REPLY_PRICE_RE = re.compile(r"price_usd\s*=\s*([0-9]+(?:\.[0-9]+)?)")


def _parse_best_deals_reply(reply: str | None) -> tuple[str | None, float | None]:
    """Extract selected_sku + price from nc-best-deals' canonical reply text.

    nc-best-deals returns ``selected_sku=<sku>, price_usd=<float>,
    source=is_latest_SKU_for_product``. Regex is fine here — the reply
    shape is owned by us and tested upstream.
    """
    if not reply:
        return None, None
    sku_match = _REPLY_SKU_RE.search(reply)
    price_match = _REPLY_PRICE_RE.search(reply)
    sku = sku_match.group(1) if sku_match else None
    try:
        price = float(price_match.group(1)) if price_match else None
    except ValueError:
        price = None
    return sku, price
