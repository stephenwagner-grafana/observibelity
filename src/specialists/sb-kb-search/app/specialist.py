"""sb-kb-search — surfaces supportbot KB articles for the user's question.

Thin specialist: it always calls the `kb_search` tool, then asks the model
to summarise. Used both as a direct target by sb-router (when the query
looks like a generic knowledge question) and as a building block by other
SB specialists that want a relevant article snippet.
"""
from __future__ import annotations

from specialist_base import Specialist, SpecialistRequest, SpecialistResponse


class SbKbSearch(Specialist):
    NAME = "sb-kb-search"
    TOOL_ALLOWLIST = ["kb_search"]
    SYSTEM_PROMPT = (
        "You answer questions by quoting from the Acme knowledge base. "
        "Call kb_search with the most specific query you can extract from "
        "the user's question. Quote the article title in your reply and "
        "summarise the relevant part in 2-3 sentences."
    )

    async def handle(self, req: SpecialistRequest) -> SpecialistResponse:
        # Always probe the KB first.
        try:
            kb = await self.call_tool("kb_search", {"query": req.message, "limit": 5}, req)
        except Exception as exc:  # noqa: BLE001
            kb = {"error": str(exc), "items": []}

        messages = [
            {"role": "system", "content": self.SYSTEM_PROMPT},
            {"role": "user", "content": req.message},
            {
                "role": "user",
                "content": f"KB search result for context: {kb}. Summarise honestly.",
            },
        ]
        result = await self.call_gateway(messages, req)
        usage = result.get("usage", {}) or {}
        cost = usage.get("cost", {}) or {}
        tool_calls = [{"name": "kb_search", "args": {"query": req.message, "limit": 5}, "result": kb}]
        return SpecialistResponse(
            reply=result.get("content", ""),
            tool_calls=tool_calls,
            cost_usd=float(cost.get("total_usd", 0.0)),
        )
