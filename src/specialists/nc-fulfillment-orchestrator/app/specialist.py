"""NcFulfillmentOrchestrator — drives order fulfillment workflow.

Phase 1 specialist. Calls get_inventory / place_order / geo_lookup.

**Mice-RCA demo hook**: when asked about ``mice`` or any rodent-named SKU
(hamster, gerbil, rat, mouse, etc.), the orchestrator tries to call
``get_inventory`` which fails because the underlying SQL references column
``rodent_qty`` that doesn't exist on the products table. The orchestrator's
job is to surface the structured error properly and emit a span with
``ai_o11y.error.kind=database_schema`` so the RCA dashboard can pick it up.
"""
from __future__ import annotations

import re
from typing import Any

import httpx
from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode

from specialist_base import Specialist, SpecialistRequest, SpecialistResponse

tracer = trace.get_tracer(__name__)

# Anything matching these is "rodent-shaped" and will trip the bug.
_RODENT_PATTERN = re.compile(
    r"\b(mice|mouse|rat|rats|rodent|hamster|gerbil|guinea[- ]?pig|chinchilla)\b",
    re.IGNORECASE,
)


class NcFulfillmentOrchestrator(Specialist):
    NAME = "nc-fulfillment-orchestrator"
    TOOL_ALLOWLIST = ["get_inventory", "place_order", "geo_lookup"]
    SYSTEM_PROMPT = (
        "You are NeonCart's fulfillment orchestrator. You coordinate "
        "stock checks, shipping geo lookups, and order placement. Use "
        "get_inventory before promising availability. Use geo_lookup to "
        "estimate shipping. Use place_order when ready. If a tool call "
        "returns a structured error, summarize what happened — do not "
        "invent inventory or order IDs."
    )

    async def handle(self, req: SpecialistRequest) -> SpecialistResponse:
        sku = (req.context.get("sku") or "").strip()
        looks_rodenty = bool(
            _RODENT_PATTERN.search(req.message)
            or (sku and _RODENT_PATTERN.search(sku))
        )

        messages: list[dict] = [
            {"role": "system", "content": self.SYSTEM_PROMPT},
            {"role": "user", "content": req.message},
        ]

        with tracer.start_as_current_span(
            f"specialist.{self.NAME}.fulfill"
        ) as span:
            span.set_attribute("ai_o11y.specialist", self.NAME)
            if req.persona_id:
                span.set_attribute("ai_o11y.persona_id", req.persona_id)
            if req.usecase:
                span.set_attribute("ai_o11y.usecase", req.usecase)
            if sku:
                span.set_attribute("nc.sku", sku)

            # If the request is rodent-shaped, proactively probe inventory.
            # This is the canonical mice-RCA failure path.
            if looks_rodenty:
                span.set_attribute("nc.rodent_request", True)
                try:
                    inv = await self.call_tool(
                        "get_inventory",
                        {"sku": sku or "mice"},
                        req,
                    )
                    inventory_result: dict[str, Any] = {"ok": inv}
                except httpx.HTTPStatusError as exc:
                    inventory_result = _record_inventory_error(span, exc)
                except (httpx.HTTPError, PermissionError) as exc:
                    inventory_result = _record_inventory_error(span, exc)

                messages.append(
                    {
                        "role": "user",
                        "content": (
                            "Inventory probe result for this rodent SKU: "
                            f"{inventory_result}. Tell the caller what happened "
                            "and DO NOT invent stock counts."
                        ),
                    }
                )

            # Now the normal gateway round-trip.
            result = await self.call_gateway(messages, req)
            if result.get("tool_calls"):
                for tc in result["tool_calls"]:
                    try:
                        tool_result: Any = await self.call_tool(
                            tc["name"], tc.get("args", {}), req
                        )
                    except (httpx.HTTPError, PermissionError) as exc:
                        tool_result = {"error": str(exc), "tool": tc["name"]}
                        span.set_attribute("ai_o11y.tool_error", tc["name"])
                    messages.append({"role": "assistant", "tool_calls": [tc]})
                    messages.append(
                        {
                            "role": "tool",
                            "content": str(tool_result),
                            "tool_call_id": tc.get("id", "x"),
                        }
                    )
                result = await self.call_gateway(messages, req)

        usage = result.get("usage", {}) or {}
        cost = usage.get("cost", {}) or {}
        return SpecialistResponse(
            reply=result.get("content", ""),
            tool_calls=result.get("tool_calls", []) or [],
            cost_usd=float(cost.get("total_usd", 0.0)),
        )


def _record_inventory_error(span: trace.Span, exc: Exception) -> dict[str, Any]:
    """Record the rodent-column bug as a structured span event."""
    detail = str(exc)
    error: dict[str, Any] = {
        "error": "inventory_lookup_failed",
        "detail": detail,
    }
    # If the error mentions the rodent_qty column, classify it as a schema bug.
    if "rodent_qty" in detail or "column" in detail.lower():
        error["kind"] = "database_schema"
        span.set_attribute("ai_o11y.error.kind", "database_schema")
        span.set_attribute("ai_o11y.error.column", "rodent_qty")
    else:
        error["kind"] = "tool_unavailable"
        span.set_attribute("ai_o11y.error.kind", "tool_unavailable")
    span.set_status(Status(StatusCode.ERROR, detail))
    span.record_exception(exc)
    return error
