"""NcChatbot — NeonCart's chat-driven shopping assistant.

Phase 1 specialist. Helps customers find products, check past orders, and
complete purchases. Runs a single tool-use round-trip in Phase 1; Phase 2
extends to multi-step orchestration.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any

import httpx

from specialist_base import Specialist, SpecialistRequest, SpecialistResponse

log = logging.getLogger(__name__)


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
        "navigate",
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
        "- Use navigate when the user says \"show me X\", \"take me to X\", \"open X\", "
        "\"browse X\", \"go to X\", or otherwise asks to be SENT to a page. Call it "
        "ALONGSIDE search_products on the same turn — search returns the cards, "
        "navigate redirects the browser to the matching catalog page so the user "
        "lands directly on the results. The navigate tool takes EXACTLY two "
        "arguments: target (string) and value (string). Pick target=\"category\" "
        "with value=<category-slug> (peripherals|displays|audio|mobile|"
        "wearables|computers|gaming|cables|storage|smart-home) when the "
        "request maps to one cleanly; otherwise target=\"search\" with "
        "value=<singular-noun-the-shopper-used>. Examples: "
        "navigate(target=\"category\", value=\"peripherals\"); "
        "navigate(target=\"search\", value=\"mouse\").\n"
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
        # Nav intent the model emitted via the navigate tool (auto=True, the
        # widget will redirect the browser). Distinct from the keyword
        # fallback below, which renders as a click-to-go button (auto=False).
        explicit_nav: dict | None = None
        fallback_nav: tuple[str, str] | None = None

        if result.get("tool_calls"):
            for tc in result["tool_calls"]:
                # Gateway emits tool_calls with "input" (Anthropic/Ollama
                # provider output); fall back to "args" for older test fixtures.
                tool_args = tc.get("input") or tc.get("args") or {}
                tool_error: str | None = None
                try:
                    tool_result = await self.call_tool(
                        tc["name"],
                        tool_args,
                        req,
                    )
                except httpx.HTTPStatusError as exc:
                    # The mice-rca demo intentionally crashes get_inventory
                    # for sku=mice-001. Catch it (and any other tool 5xx)
                    # so the turn still produces a reply + the widget can
                    # render the failure as a tool row instead of the whole
                    # chat 500'ing with no context.
                    try:
                        body = exc.response.json()
                        detail = body.get("detail") if isinstance(body, dict) else str(body)
                    except Exception:
                        detail = (exc.response.text or "")[:200]
                    tool_error = f"HTTP {exc.response.status_code}" + (
                        f": {detail}" if detail else ""
                    )
                    tool_result = {
                        "error": tool_error,
                        "status": "failed",
                        "tool": tc["name"],
                    }
                    log.warning("tool %s failed: %s", tc["name"], tool_error)
                except Exception as exc:  # noqa: BLE001
                    tool_error = str(exc) or exc.__class__.__name__
                    tool_result = {
                        "error": tool_error,
                        "status": "failed",
                        "tool": tc["name"],
                    }
                    log.warning("tool %s raised: %s", tc["name"], tool_error)

                # Decorate the tool_call we hand back to the widget with a
                # status pill — green check on success, red x + error text
                # on failure. The bubble's "Tools" list reads these.
                decorated_tc = dict(tc)
                decorated_tc["status"] = "error" if tool_error else "ok"
                if tool_error:
                    decorated_tc["error"] = tool_error
                all_tool_calls.append(decorated_tc)

                # Capture search hits + nav intent so the UI can render cards
                # and route the catalog grid to match the conversation.
                # Skip on failure — there's no result to inspect.
                if not tool_error:
                    if tc["name"] == "search_products":
                        items = (tool_result or {}).get("items") or []
                        products.extend(items)
                        query = (tool_args or {}).get("query", "") or req.message
                        slug = _category_for(query) or _category_for(req.message)
                        if slug:
                            fallback_nav = ("category", slug)
                        elif query:
                            fallback_nav = ("search", query)
                    elif tc["name"] == "get_product":
                        item = (tool_result or {}).get("item") or tool_result
                        if isinstance(item, dict) and item.get("id"):
                            products.append(item)
                            fallback_nav = ("product", str(item["id"]))
                    elif tc["name"] == "navigate":
                        # The agent explicitly asked to send the user somewhere.
                        # Tool returned the URL+label we'll auto-fire in the widget.
                        if isinstance(tool_result, dict) and tool_result.get("url"):
                            explicit_nav = {
                                "type": "navigate",
                                "target": tool_result.get("target") or tool_args.get("target") or "search",
                                "value": tool_result.get("value") or tool_args.get("value") or "",
                                "url": tool_result["url"],
                                "label": tool_result.get("label") or "Open",
                                "auto": True,
                            }
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
        if not (explicit_nav or fallback_nav):
            slug = _category_for(req.message)
            if slug:
                fallback_nav = ("category", slug)

        # If any tool failed on this turn, demote the auto-redirect so the
        # user can read the error bubble before the page swaps out from
        # under them (e.g. mice-rca: search succeeded, navigate succeeded,
        # but get_inventory blew up — don't auto-jump away from the err).
        had_tool_error = any(tc.get("status") == "error" for tc in all_tool_calls)
        if explicit_nav and had_tool_error:
            explicit_nav["auto"] = False

        actions: list[dict] = []
        if explicit_nav:
            # Auto-redirect: the agent picked navigate as a verb on this turn.
            actions.append(explicit_nav)
        elif fallback_nav:
            # Render-a-button: a side-effect of search/get_product without an
            # explicit nav verb. User clicks to follow through.
            actions.append(
                {
                    "type": "navigate",
                    "target": fallback_nav[0],
                    "value": fallback_nav[1],
                    "auto": False,
                }
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
