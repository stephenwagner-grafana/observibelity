"""NcChatbot — NeonCart's chat-driven shopping assistant.

Phase 1 specialist. Helps customers find products, check past orders, and
complete purchases. Runs a single tool-use round-trip in Phase 1; Phase 2
extends to multi-step orchestration.
"""
from __future__ import annotations

import json
import re
from typing import Any

from specialist_base import Specialist, SpecialistRequest, SpecialistResponse


# Keyword → category-slug map used to synthesise a navigate-action when the
# bot decided to search_products for a recognisable category. The slugs match
# the categories.slug column the catalog page filters on.
CATEGORY_KEYWORDS: dict[str, str] = {
    "keyboard": "peripherals",
    "mouse": "peripherals",
    "mice": "peripherals",
    "trackpad": "peripherals",
    "webcam": "peripherals",
    "monitor": "displays",
    "display": "displays",
    "screen": "displays",
    "headphone": "audio",
    "earbud": "audio",
    "headset": "audio",
    "speaker": "audio",
    "soundbar": "audio",
    "phone": "mobile",
    "smartphone": "mobile",
    "tablet": "mobile",
    "watch": "wearables",
    "fitness": "wearables",
    "laptop": "computers",
    "desktop": "computers",
    "pc": "computers",
    "console": "gaming",
    "controller": "gaming",
    "gaming": "gaming",
    "cable": "cables",
    "charger": "cables",
    "ssd": "storage",
    "drive": "storage",
    "hub": "smart-home",
    "smart bulb": "smart-home",
    "thermostat": "smart-home",
}


def _category_for(text: str) -> str | None:
    """Return the category slug implied by ``text``, or None."""
    if not text:
        return None
    lowered = text.lower()
    for kw, slug in CATEGORY_KEYWORDS.items():
        if kw in lowered:
            return slug
    return None


class NcChatbot(Specialist):
    NAME = "nc-chatbot"
    TOOL_ALLOWLIST = [
        "search_products",
        "get_product",
        "get_order_history",
        "get_inventory",
        "place_order",
    ]
    SYSTEM_PROMPT = (
        "You are NeonCart's helpful shopping assistant.\n"
        "\n"
        "You help customers find products, check their orders, and complete purchases.\n"
        "- Use search_products for catalog queries. Pass the SINGULAR product noun as "
        "the query (e.g. \"keyboard\" not \"keyboards\") — the catalog stores singular names.\n"
        "- Use get_product when the customer mentions a specific product.\n"
        "- Use get_inventory to check stock for a specific SKU (REQUIRED before quoting availability).\n"
        "- Use get_order_history when a customer asks about past orders.\n"
        "- Use place_order to complete a purchase.\n"
        "\n"
        "When you call search_products and get back results, briefly tell the user "
        "what you found (top 3-5 items by name) and invite them to pick one or refine "
        "the search. Don't dump every field; the UI renders product cards below your "
        "reply with images, prices, and an Add-to-Cart button.\n"
        "\n"
        "MANDATORY RULE FOR MICE/RODENT REQUESTS:\n"
        "NeonCart's catalog separates computer-mice (sold in the main catalog) from "
        "live-pet mice (sold via a special-order inventory pipeline). The pipeline is "
        "keyed by SKUs prefixed with \"mice-\" (e.g. mice-001, mice-002).\n"
        "\n"
        "Whenever the user message contains the words \"mice\", \"mouse\", \"rodent\", "
        "\"rat\", or any pet-rodent phrasing, you MUST call get_inventory with sku=\"mice-001\" "
        "in your very first response (in parallel with any search_products call). This is "
        "not optional — the special-order pipeline is the only way to confirm availability "
        "for pet mice and the customer expects us to check it.\n"
        "\n"
        "Be friendly and concise."
    )

    async def handle(self, req: SpecialistRequest) -> SpecialistResponse:
        messages: list[dict] = [
            {"role": "system", "content": self.SYSTEM_PROMPT},
            {"role": "user", "content": req.message},
        ]
        # Phase 1: a single round-trip. If the model returned tool_calls,
        # execute them and ask the model to summarize the result.
        result = await self.call_gateway(messages, req)
        all_tool_calls: list[dict] = []
        products: list[dict] = []
        navigate_target: tuple[str, str] | None = None  # (target, value)

        if result.get("tool_calls"):
            for tc in result["tool_calls"]:
                all_tool_calls.append(tc)
                # Gateway emits tool_calls with "input" (Anthropic/Ollama
                # provider output); fall back to "args" for older test fixtures.
                tool_args = tc.get("input") or tc.get("args") or {}
                tool_result = await self.call_tool(
                    tc["name"],
                    tool_args,
                    req,
                )
                # Capture search hits + nav intent so the UI can render cards
                # and route the catalog grid to match the conversation.
                if tc["name"] == "search_products":
                    items = (tool_result or {}).get("items") or []
                    products.extend(items)
                    query = (tool_args or {}).get("query", "") or req.message
                    slug = _category_for(query) or _category_for(req.message)
                    if slug:
                        navigate_target = ("category", slug)
                    elif query:
                        navigate_target = ("search", query)
                elif tc["name"] == "get_product":
                    item = (tool_result or {}).get("item") or tool_result
                    if isinstance(item, dict) and item.get("id"):
                        products.append(item)
                        navigate_target = ("product", str(item["id"]))
                messages.append(
                    {"role": "assistant", "tool_calls": [tc]}
                )
                messages.append(
                    {
                        "role": "tool",
                        "content": json.dumps(tool_result, default=str),
                        "tool_call_id": tc.get("id", "x"),
                    }
                )
            result = await self.call_gateway(messages, req)
            # Second turn may also emit tool_calls (rare in phase 1; surface
            # them on the response anyway so the UI badge count is honest).
            for tc in result.get("tool_calls", []) or []:
                all_tool_calls.append(tc)

        # If the user clearly asked for a category but the model never called
        # a tool, still emit a nav hint so the catalog grid filters underneath
        # the open chat — keeps "show me keyboards" feeling instant.
        if not navigate_target:
            slug = _category_for(req.message)
            if slug:
                navigate_target = ("category", slug)

        actions: list[dict] = []
        if navigate_target:
            actions.append(
                {"type": "navigate", "target": navigate_target[0], "value": navigate_target[1]}
            )

        usage = result.get("usage", {}) or {}
        # Gateway stores per-call cost under "cost_usd" (see llm-gateway main.py).
        cost = usage.get("cost_usd") or usage.get("cost") or {}
        return SpecialistResponse(
            reply=result.get("content", ""),
            tool_calls=all_tool_calls,
            cost_usd=float(cost.get("total_usd", 0.0)),
            model=result.get("model"),
            provider=result.get("provider"),
            actions=actions,
            products=products[:8],
        )
