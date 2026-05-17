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
import logging
import os
import re
from typing import Any

import httpx
from prometheus_client import Counter

from specialist_base import Specialist, SpecialistRequest, SpecialistResponse

# Root logger defaults to WARNING — bootstrap INFO so nc_gift_finder_quality
# log lines reach Loki for the demo's quality-rate panel.
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
log = logging.getLogger(__name__)
log.setLevel(os.getenv("LOG_LEVEL", "INFO"))


# Built-in heuristic quality eval — emitted on every gift-finder turn so
# the demo's "quality of response" panel has a steady pulse without
# needing Sigil's UI-only LLM-judge evaluators wired up.
#
# Pass criteria:
#   1. agent returned >= 3 product candidates (cards), AND
#   2. at least one of them is <= the budget the user stated (if any), AND
#   3. the reply text mentions at least one returned product's name.
# Anything else fails. Labels are model + reason so the dashboard can
# break down "which model produces good gift-finder turns".
QUALITY_COUNTER = Counter(
    "nc_gift_finder_quality_total",
    "Heuristic quality eval result emitted on every gift-finder turn.",
    ["result", "reason", "model"],
)


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
        "navigate",
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
        "- Use navigate when the user says \"show me X\", \"take me to X\", \"open X\", "
        "or otherwise asks to be SENT to a page. Call it ALONGSIDE search_products "
        "on the same turn — search returns the cards, navigate redirects the "
        "browser to the matching catalog page. The navigate tool takes EXACTLY "
        "two arguments: target (string) and value (string). Pick "
        "target=\"category\" with value=<category-slug> (peripherals|displays|"
        "audio|mobile|wearables|computers|gaming|cables|storage|smart-home) "
        "when the request maps to one cleanly; otherwise target=\"search\" "
        "with value=<singular-noun>. Examples: "
        "navigate(target=\"category\", value=\"audio\"); "
        "navigate(target=\"search\", value=\"headphone\").\n"
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

    # Per-usecase addendum: when the chat widget pins
    # usecase=cross-gen-retrieval-drift (the "PC gaming nephew" chip), tell
    # the agent to do a SKU-verify call after the broad search. Together
    # with search_products' demo mode this produces the two-span trace the
    # audience is meant to read.
    CROSS_GEN_ADDENDUM = (
        "\n\nDEMO FLOW — premium PC hardware:\n"
        "This shopper wants a hardware upgrade gift for a PC gamer. The "
        "catalog runs promotional pricing on enthusiast memory kits through "
        "linked SKU records, so SKU-verification is required:\n"
        "1. Call search_products(query=\"corsair dominator\") FIRST to find "
        "candidates. Pick the highest-spec 64GB DDR5 2026 candidate as the "
        "primary recommendation.\n"
        "2. Then call search_products A SECOND TIME, passing that candidate's "
        "FULL SKU string verbatim as the query — the long "
        "\"1004-corsair-0072-…\" identifier. This verifies the current best "
        "price; promotional updates land on alternate catalog records and "
        "are not visible via name search.\n"
        "3. The second call's top result is authoritative for pricing. Quote "
        "its price in your reply and call out the gap from sticker as a "
        "\"trending deal\". Don't second-guess the verified price — it's the "
        "live system-of-record value.\n"
        "Issue both tool calls in your first response so the customer sees a "
        "verified recommendation in one round-trip."
    )

    async def handle(self, req: SpecialistRequest) -> SpecialistResponse:
        system_prompt = self.SYSTEM_PROMPT
        if req.usecase == "cross-gen-retrieval-drift":
            system_prompt = system_prompt + self.CROSS_GEN_ADDENDUM
        messages: list[dict] = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": req.message},
        ]
        result = await self.call_gateway(messages, req)
        all_tool_calls: list[dict] = []
        products: list[dict] = []
        explicit_nav: dict | None = None
        fallback_nav: tuple[str, str] | None = None
        cart_added: list[dict] = []

        # The concrete model the gateway routed to. Stamped on every
        # add_to_cart so the model-winner dashboard can attribute the ATC
        # back to the model that produced the recommendation.
        chosen_model = result.get("model") or ""

        if result.get("tool_calls"):
            for tc in result["tool_calls"]:
                tool_args = tc.get("input") or tc.get("args") or {}
                # When the agent calls add_to_cart, decorate its args with
                # the model+agent labels so the tool's counter and log line
                # carry full provenance.
                if tc["name"] == "add_to_cart":
                    if isinstance(tool_args, dict):
                        tool_args.setdefault("agent_name", self.NAME)
                        tool_args.setdefault("model", chosen_model)
                        tool_args.setdefault("source", "agent")
                tool_error: str | None = None
                try:
                    tool_result = await self.call_tool(
                        tc["name"], tool_args, req,
                    )
                except httpx.HTTPStatusError as exc:
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

                decorated_tc = dict(tc)
                decorated_tc["status"] = "error" if tool_error else "ok"
                if tool_error:
                    decorated_tc["error"] = tool_error
                all_tool_calls.append(decorated_tc)

                if not tool_error:
                    if tc["name"] == "search_products":
                        items = (tool_result or {}).get("items") or []
                        products.extend(items)
                        q = (tool_args or {}).get("query", "") or req.message
                        slug = _category_for(q) or _category_for(req.message)
                        if slug:
                            fallback_nav = ("category", slug)
                    elif tc["name"] == "get_product":
                        item = (tool_result or {}).get("item") or tool_result
                        if isinstance(item, dict) and item.get("id"):
                            products.append(item)
                            fallback_nav = ("product", str(item["id"]))
                    elif tc["name"] == "add_to_cart":
                        cart_added.append({"input": tool_args, "result": tool_result})
                    elif tc["name"] == "navigate":
                        if isinstance(tool_result, dict) and tool_result.get("url"):
                            explicit_nav = {
                                "type": "navigate",
                                "target": tool_result.get("target") or tool_args.get("target") or "search",
                                "value": tool_result.get("value") or tool_args.get("value") or "",
                                "url": tool_result["url"],
                                "label": tool_result.get("label") or "Open",
                                "auto": True,
                            }
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
        if not (explicit_nav or fallback_nav):
            slug = _category_for(req.message)
            if slug:
                fallback_nav = ("category", slug)

        actions: list[dict] = []
        if explicit_nav:
            actions.append(explicit_nav)
        elif fallback_nav:
            actions.append(
                {
                    "type": "navigate",
                    "target": fallback_nav[0],
                    "value": fallback_nav[1],
                    "auto": False,
                }
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

        # Built-in quality eval — fire on every turn so the demo panel has
        # a steady signal. See QUALITY_COUNTER comment above for criteria.
        reply_text = result.get("content", "") or ""
        self._emit_quality_eval(req, products, reply_text, chosen_model, budget)

        return SpecialistResponse(
            reply=reply_text,
            tool_calls=all_tool_calls,
            cost_usd=float(cost.get("total_usd", 0.0)),
            model=chosen_model,
            provider=result.get("provider"),
            actions=actions,
            products=products[:6],
        )

    def _emit_quality_eval(
        self,
        req: SpecialistRequest,
        products: list[dict],
        reply_text: str,
        model: str,
        budget: float | None,
    ) -> None:
        """Score the turn against three lightweight criteria + emit a counter.

        Reasons (sticky single-label on the counter for legend clarity):
          ok                       — all three pass.
          missing_products         — fewer than 3 product candidates.
          over_budget              — products returned, but none under budget.
          reply_no_product_mention — products returned but reply doesn't name any.
        """
        reason = "ok"
        result = "pass"
        if len(products) < 3:
            reason = "missing_products"
            result = "fail"
        elif budget is not None:
            within = [
                p for p in products
                if p.get("price_usd") is None
                or float(p["price_usd"]) <= budget
            ]
            if not within:
                reason = "over_budget"
                result = "fail"
        if result == "pass":
            names = [
                (p.get("name") or "").split()
                for p in products
            ]
            tokens = {w.lower() for parts in names for w in parts if len(w) > 3}
            mentioned = any(t in reply_text.lower() for t in tokens) if tokens else False
            if not mentioned:
                reason = "reply_no_product_mention"
                result = "fail"
        QUALITY_COUNTER.labels(result=result, reason=reason, model=model or "").inc()
        log.info(
            "nc_gift_finder_quality result=%s reason=%s model=%s "
            "products=%d budget=%s session=%s",
            result, reason, model, len(products), budget, req.session_id,
        )
