"""NcChatbot — NeonCart's chat-driven shopping assistant.

Phase 1 specialist. Helps customers find products, check past orders, and
complete purchases. Runs a single tool-use round-trip in Phase 1; Phase 2
extends to multi-step orchestration.
"""
from __future__ import annotations

from specialist_base import Specialist, SpecialistRequest, SpecialistResponse


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
        "- Use search_products for catalog queries.\n"
        "- Use get_product when the customer mentions a specific product.\n"
        "- Use get_inventory to check stock for a specific SKU (REQUIRED before quoting availability).\n"
        "- Use get_order_history when a customer asks about past orders.\n"
        "- Use place_order to complete a purchase.\n"
        "\n"
        "SPECIAL CASE FOR MICE/RODENT REQUESTS:\n"
        "NeonCart's catalog uses unusual SKU conventions for rodent-adjacent products. "
        "If a customer asks for \"mice\", \"rodents\", or similar pet-related queries:\n"
        "1. Search the catalog with search_products first.\n"
        "2. If the results are computer mice (Wireless Mouse, etc.), offer those.\n"
        "3. If the customer specifically wants live rodents or pet mice, our system uses "
        "special inventory SKUs prefixed with \"mice-\" (e.g. mice-001). Call get_inventory "
        "with such a SKU to check our special-order pipeline.\n"
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
        if result.get("tool_calls"):
            for tc in result["tool_calls"]:
                # Gateway emits tool_calls with "input" (Anthropic/Ollama
                # provider output); fall back to "args" for older test fixtures.
                tool_args = tc.get("input") or tc.get("args") or {}
                tool_result = await self.call_tool(
                    tc["name"],
                    tool_args,
                    req,
                )
                messages.append(
                    {"role": "assistant", "tool_calls": [tc]}
                )
                messages.append(
                    {
                        "role": "tool",
                        "content": str(tool_result),
                        "tool_call_id": tc.get("id", "x"),
                    }
                )
            result = await self.call_gateway(messages, req)

        usage = result.get("usage", {}) or {}
        # Gateway stores per-call cost under "cost_usd" (see llm-gateway main.py).
        cost = usage.get("cost_usd") or usage.get("cost") or {}
        return SpecialistResponse(
            reply=result.get("content", ""),
            tool_calls=result.get("tool_calls", []) or [],
            cost_usd=float(cost.get("total_usd", 0.0)),
        )
