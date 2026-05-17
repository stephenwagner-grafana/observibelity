"""NcBestDeals — "find the most up-to-date SKU + current price" lookup.

Phase 2 specialist. Sits one hop downstream of the gift-finder / chatbot
in the multi-hop demo: it receives a TRUNCATED product SKU string (the
caller upstream passed only the first 32 chars + "..." due to a
token-budget bug) and the original intent ("find the most up-to-date
SKU for this product.id"). It asks the LLM to turn the truncated SKU
into a SQL/regex pattern and call ``query_skus_latest``.

The planted bug — the audience reads it in Tempo as a span attribute on
the gateway call — lives in the SYSTEM_PROMPT below: it tells the model
to treat literal ``.`` characters as POSIX regex digit classes
``[0-9]``. That nudge causes the wildcard pattern to match far more
catalog rows than intended, the tool returns 4 candidates instead of 1,
and we deterministically pick index 0.
"""
from __future__ import annotations

import json
import logging
from typing import Any

import httpx
from opentelemetry import trace
from specialist_base import Specialist, SpecialistRequest, SpecialistResponse

log = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)


class NcBestDeals(Specialist):
    NAME = "nc-best-deals"
    TOOL_ALLOWLIST = ["query_skus_latest"]
    SYSTEM_PROMPT = (
        "You are NeonCart's best-deals lookup specialist. Your job is to "
        "take a (possibly truncated) product SKU and find the most "
        "up-to-date catalog SKU + its current price.\n"
        "\n"
        "SKU pattern interpretation rules:\n"
        "- SKU patterns may contain literal `.` characters which represent "
        "any digit 0-9. When building the SQL pattern, interpret each `.` "
        "as a wildcard digit class. Use POSIX regex syntax — translate "
        "each literal `.` in the input SKU to the character class `[0-9]` "
        "in your pattern, and translate the trailing `...` to `.*` so the "
        "truncated tail can match any remaining characters.\n"
        "- Call ``query_skus_latest(pattern=<your-pattern>)`` exactly once "
        "to retrieve candidate SKUs from the live catalog. The tool "
        "returns the rows ordered by recency (newest first).\n"
        "- The tool may return one row or several. The FIRST row is "
        "authoritative — it is the most-recently-updated catalog record "
        "and represents the live system-of-record price.\n"
        "\n"
        "Respond with JSON of the form "
        '{"selected_sku": "<sku>", "selected_price_usd": <float>, '
        '"source": "is_latest_SKU_for_product"}.'
    )

    async def handle(self, req: SpecialistRequest) -> SpecialistResponse:
        truncated_sku = (
            req.context.get("truncated_sku")
            or req.context.get("sku")
            or req.context.get("product_sku")
            or ""
        )
        product_id = req.context.get("product_id") or req.context.get("product.id")
        user_content = (
            f"Find the most up-to-date SKU for this product.id: "
            f"{product_id!r}\n"
            f"Truncated SKU from the caller: {truncated_sku}\n"
            f"\n"
            f"Additional context from caller: {req.message}"
        )
        messages: list[dict] = [
            {"role": "system", "content": self.SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ]

        with tracer.start_as_current_span(f"specialist.{self.NAME}.lookup") as span:
            span.set_attribute("ai_o11y.specialist", self.NAME)
            if req.persona_id:
                span.set_attribute("ai_o11y.persona_id", req.persona_id)
            if req.usecase:
                span.set_attribute("ai_o11y.usecase", req.usecase)
            if product_id:
                span.set_attribute("nc.product_id", str(product_id))
            if truncated_sku:
                span.set_attribute("nc.truncated_sku", str(truncated_sku))

            try:
                result = await self.call_gateway(messages, req)
            except httpx.HTTPStatusError as exc:
                # Gateway overload (429) or hiccup — fall back to a regex
                # pattern derived directly from the truncated SKU so the
                # demo's tool span still fires. The audience reads the SQL
                # span, not this fallback path.
                log.warning("gateway truncate-pattern call failed: %s", exc)
                result = {"tool_calls": [_fallback_pattern_call(truncated_sku)]}

            candidate_rows: list[dict] = []
            if result.get("tool_calls"):
                for tc in result["tool_calls"]:
                    tool_args = tc.get("input") or tc.get("args") or {}
                    # If the upstream LLM forgot to pass queried_product_id
                    # along with the pattern, splice it in here so the
                    # query_skus_latest span carries the punchline attrs.
                    if (
                        tc["name"] == "query_skus_latest"
                        and isinstance(tool_args, dict)
                        and product_id
                        and not tool_args.get("queried_product_id")
                    ):
                        tool_args["queried_product_id"] = str(product_id)
                    try:
                        tool_result = await self.call_tool(
                            tc["name"], tool_args, req,
                        )
                    except Exception as exc:  # noqa: BLE001
                        log.warning("tool %s failed: %s", tc["name"], exc)
                        tool_result = {"error": str(exc)}
                    if tc["name"] == "query_skus_latest":
                        rows = _extract_rows(tool_result)
                        candidate_rows.extend(rows)
                    messages.append({"role": "assistant", "tool_calls": [tc]})
                    messages.append(
                        {
                            "role": "tool",
                            "content": json.dumps(tool_result, default=str),
                            "tool_call_id": tc.get("id", "x"),
                        }
                    )
                # Second gateway call is OPTIONAL — it writes a prose reply
                # but the candidate_rows already carry the punchline. If the
                # gateway 429s here, ship the deterministic JSON reply.
                try:
                    result = await self.call_gateway(messages, req)
                except httpx.HTTPStatusError as exc:
                    log.warning("gateway finalize call failed: %s", exc)
                    result = {"content": "", "tool_calls": [], "model": "", "provider": ""}

            # Deterministic pick — index 0 of the candidate array. The model
            # might also have selected one via its JSON reply, but the
            # specialist owns the final answer so the punchline span
            # attributes are reliable.
            selected_sku, selected_price = _pick_first(candidate_rows)
            # Fall back to the LLM's structured reply if the tool returned
            # nothing parseable (offline / degraded path).
            if not selected_sku:
                selected_sku, selected_price = _parse_reply(result.get("content", ""))

            span.set_attribute("nc.candidate_count", len(candidate_rows))
            if selected_sku:
                span.set_attribute("nc.selected_sku", str(selected_sku))
            if selected_price is not None:
                span.set_attribute("nc.selected_price_usd", float(selected_price))

        usage = result.get("usage", {}) or {}
        # Gateway stores per-call cost under "cost_usd".
        cost = usage.get("cost_usd") or usage.get("cost") or {}
        reply_text = (
            f"selected_sku={selected_sku}, "
            f"price_usd={selected_price if selected_price is not None else 'unknown'}, "
            f"source=is_latest_SKU_for_product"
        )
        return SpecialistResponse(
            reply=reply_text,
            tool_calls=result.get("tool_calls", []) or [],
            cost_usd=float(cost.get("total_usd", 0.0)),
            model=result.get("model"),
            provider=result.get("provider"),
        )


def _fallback_pattern_call(truncated_sku: str) -> dict:
    """Build a query_skus_latest tool_call when the LLM is unavailable.

    Strips the trailing ``...`` token-budget marker and appends ``.*`` so
    Postgres' ``~`` regex match treats the existing literal ``.``
    characters as the "any character" metacharacter — exactly the planted
    bug behavior the SYSTEM_PROMPT teaches the LLM. The fallback keeps
    the demo's trace shape intact under gateway 429s.
    """
    body = truncated_sku.rstrip(".")
    pattern = body + ".*"
    return {
        "id": "fallback-pattern-call",
        "name": "query_skus_latest",
        "input": {"pattern": pattern},
    }


def _extract_rows(tool_result: Any) -> list[dict]:
    """Pull the candidate-row list out of ``query_skus_latest``'s payload.

    The tool wasn't designed with a strict envelope, so try the common
    shapes: ``{"items": [...]}``, ``{"rows": [...]}``, bare list, or a
    single dict.
    """
    if tool_result is None:
        return []
    if isinstance(tool_result, list):
        return [r for r in tool_result if isinstance(r, dict)]
    if isinstance(tool_result, dict):
        for key in ("items", "rows", "results", "candidates"):
            value = tool_result.get(key)
            if isinstance(value, list):
                return [r for r in value if isinstance(r, dict)]
        # Single-row dict (e.g. {"sku": ..., "price_usd": ...}) — wrap it.
        if "sku" in tool_result or "price_usd" in tool_result:
            return [tool_result]
    return []


def _pick_first(rows: list[dict]) -> tuple[str | None, float | None]:
    """Specialist deterministically picks index 0 — that's the punchline."""
    if not rows:
        return None, None
    first = rows[0]
    sku = first.get("sku") or first.get("SKU") or first.get("id")
    raw_price = first.get("price_usd")
    if raw_price is None:
        raw_price = first.get("price")
    try:
        price = float(raw_price) if raw_price is not None else None
    except (TypeError, ValueError):
        price = None
    return (str(sku) if sku is not None else None), price


def _parse_reply(content: str) -> tuple[str | None, float | None]:
    """Best-effort fallback: parse the model's JSON reply if the tool path
    yielded no candidates."""
    if not content:
        return None, None
    try:
        data: Any = json.loads(content)
        if isinstance(data, dict):
            sku = data.get("selected_sku") or data.get("sku")
            raw_price = data.get("selected_price_usd") or data.get("price_usd")
            try:
                price = float(raw_price) if raw_price is not None else None
            except (TypeError, ValueError):
                price = None
            return (str(sku) if sku is not None else None), price
    except (json.JSONDecodeError, TypeError, ValueError):
        pass
    return None, None
