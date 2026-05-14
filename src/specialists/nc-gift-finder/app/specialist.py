"""NcGiftFinder — NeonCart's gift recommendation agent.

A dedicated specialist (not nc-chatbot) so the demo shows agent_name=
"nc-gift-finder" in Sigil, with its own model routing, eval coverage,
and Add-to-cart tool surface. Single tool-use round-trip:

  1. Read budget / occasion / recipient cues from the user message.
  2. Call search_products to find candidates within the budget.
  3. (Optionally) call add_to_cart when the user says "yes, add the X"
     in a follow-up turn — the front-end also exposes a per-card Add
     button so the agent never has to gate the buy on a free-text reply.
"""
from __future__ import annotations

import json
import re
from typing import Any

from specialist_base import Specialist, SpecialistRequest, SpecialistResponse


# Same keyword→category map as nc-chatbot so the catalog grid behind the
# chat reroutes if the user mentions an obvious category in their gift
# query ("looking for a gift, maybe a keyboard or headphones").
CATEGORY_KEYWORDS: dict[str, str] = {
    "keyboard": "peripherals", "mouse": "peripherals", "trackpad": "peripherals",
    "webcam": "peripherals",
    "monitor": "displays", "display": "displays", "screen": "displays",
    "headphone": "audio", "earbud": "audio", "headset": "audio",
    "speaker": "audio", "soundbar": "audio",
    "phone": "mobile", "smartphone": "mobile", "tablet": "mobile",
    "watch": "wearables", "fitness": "wearables",
    "laptop": "computers", "desktop": "computers",
    "console": "gaming", "controller": "gaming", "gaming": "gaming",
    "cable": "cables", "charger": "cables",
    "ssd": "storage", "drive": "storage",
    "hub": "smart-home", "thermostat": "smart-home",
}

# Pull a budget out of free text. Captures dollar amount in either "under
# $200" / "around 150" / "≤ $99.95" shapes. Returns the upper bound only;
# good enough for "anything under X" demos. Empty → no budget detected.
_BUDGET_RE = re.compile(
    r"(?:under|below|less than|≤|<=|<|around|about|~|up to)\s*\$?\s*"
    r"(\d{1,4}(?:\.\d{1,2})?)",
    re.IGNORECASE,
)


def _category_for(text: str) -> str | None:
    if not text:
        return None
    lowered = text.lower()
    for kw, slug in CATEGORY_KEYWORDS.items():
        if kw in lowered:
            return slug
    return None


def _budget_for(text: str) -> float | None:
    m = _BUDGET_RE.search(text or "")
    if not m:
        return None
    try:
        return float(m.group(1))
    except ValueError:
        return None


class NcGiftFinder(Specialist):
    NAME = "nc-gift-finder"
    TOOL_ALLOWLIST = [
        "search_products",
        "get_product",
        "add_to_cart",
    ]
    SYSTEM_PROMPT = (
        "You are NeonCart's Gift Finder — a concise, confident shopping assistant "
        "that helps a customer pick a gift in seconds.\n"
        "\n"
        "Operating principles:\n"
        "- Read budget, occasion, and recipient cues from the user's first message. "
        "If the budget is implicit (\"something nice for my dad\"), pick a sensible "
        "anchor (~$150) and say so. Don't ask 5 clarifying questions before searching.\n"
        "- Use search_products to find candidates. Pass the SINGULAR product noun as "
        "the query (e.g. \"headphone\" not \"headphones\") — the catalog stores singular names.\n"
        "- After the search, summarise the top 3-5 picks with ONE short line each "
        "explaining the fit (\"premium ANC for the daily commute\", \"compact, sturdy, "
        "kid-proof\"). Don't dump every spec; the UI renders product cards below.\n"
        "- Each card has its own Add button — don't pester the user to confirm; "
        "if they explicitly say \"add the X\" in a follow-up turn, then call "
        "add_to_cart with the matching product_id.\n"
        "- Keep responses short and warm. End with one nudge: \"Want me to narrow it "
        "down by price?\" or \"Looking for something more compact?\"\n"
        "\n"
        "Stay strictly on shopping; if the user asks about returns, order status, "
        "or company policy, say you'll hand them to support and stop."
    )

    async def handle(self, req: SpecialistRequest) -> SpecialistResponse:
        messages: list[dict] = [
            {"role": "system", "content": self.SYSTEM_PROMPT},
            {"role": "user", "content": req.message},
        ]
        result = await self.call_gateway(messages, req)
        all_tool_calls: list[dict] = []
        products: list[dict] = []
        navigate_target: tuple[str, str] | None = None
        cart_added: list[dict] = []

        if result.get("tool_calls"):
            for tc in result["tool_calls"]:
                all_tool_calls.append(tc)
                tool_args = tc.get("input") or tc.get("args") or {}
                tool_result = await self.call_tool(
                    tc["name"], tool_args, req,
                )
                if tc["name"] == "search_products":
                    items = (tool_result or {}).get("items") or []
                    products.extend(items)
                    q = (tool_args or {}).get("query", "") or req.message
                    slug = _category_for(q) or _category_for(req.message)
                    if slug:
                        navigate_target = ("category", slug)
                elif tc["name"] == "get_product":
                    item = (tool_result or {}).get("item") or tool_result
                    if isinstance(item, dict) and item.get("id"):
                        products.append(item)
                        navigate_target = ("product", str(item["id"]))
                elif tc["name"] == "add_to_cart":
                    cart_added.append({"input": tool_args, "result": tool_result})
                messages.append({"role": "assistant", "tool_calls": [tc]})
                messages.append(
                    {
                        "role": "tool",
                        "content": json.dumps(tool_result, default=str),
                        "tool_call_id": tc.get("id", "x"),
                    }
                )
            result = await self.call_gateway(messages, req)
            for tc in result.get("tool_calls", []) or []:
                all_tool_calls.append(tc)

        # Even if the model never called search_products (e.g. ran out of
        # tokens or refused), surface a category nav hint when the user
        # message clearly named one.
        if not navigate_target:
            slug = _category_for(req.message)
            if slug:
                navigate_target = ("category", slug)

        actions: list[dict] = []
        if navigate_target:
            actions.append(
                {"type": "navigate", "target": navigate_target[0], "value": navigate_target[1]}
            )

        # Budget filter — drop any product over the inferred ceiling so the
        # cards we surface match what the user actually asked for. Done in
        # the specialist (not the tool) so other tools/agents can still
        # query the unfiltered catalog when they need to.
        budget = _budget_for(req.message)
        if budget and products:
            products = [
                p for p in products
                if not p.get("price_usd") or float(p["price_usd"]) <= budget
            ]

        usage = result.get("usage", {}) or {}
        cost = usage.get("cost_usd") or usage.get("cost") or {}
        return SpecialistResponse(
            reply=result.get("content", ""),
            tool_calls=all_tool_calls,
            cost_usd=float(cost.get("total_usd", 0.0)),
            model=result.get("model"),
            provider=result.get("provider"),
            actions=actions,
            products=products[:6],
        )
