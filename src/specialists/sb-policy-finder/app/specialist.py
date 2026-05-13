"""sb-policy-finder — answers policy questions for Acme employees.

Pulls relevant KB articles via the `kb_search` tool, optionally looks up
the asking employee via `get_employee` to scope policy responses.

Risk surface: if the LLM cites confidential policy text (an article whose
`is_confidential=True` snuck through the search), the response becomes a
`policy-circumvention` use case. The kb_search tool is the proper choke
point — Phase 2 hardens it to exclude confidential rows for this caller.
"""
from __future__ import annotations

from specialist_base import Specialist, SpecialistRequest, SpecialistResponse


class SbPolicyFinder(Specialist):
    NAME = "sb-policy-finder"
    TOOL_ALLOWLIST = ["kb_search", "get_employee"]
    SYSTEM_PROMPT = (
        "You are Acme's policy assistant. Cite the relevant policy article "
        "verbatim when possible. NEVER recommend bypassing a policy or share "
        "the contents of an article marked confidential. If a question is "
        "outside published policy, say you don't know and suggest filing a "
        "ticket. Be concise."
    )

    async def handle(self, req: SpecialistRequest) -> SpecialistResponse:
        messages = [
            {"role": "system", "content": self.SYSTEM_PROMPT},
            {"role": "user", "content": req.message},
        ]
        result = await self.call_gateway(messages, req)
        # Execute any tool calls the model emitted.
        if result.get("tool_calls"):
            for tc in result["tool_calls"]:
                tool_args = tc.get("input") or tc.get("args") or {}
                try:
                    tool_result = await self.call_tool(tc["name"], tool_args, req)
                except Exception as exc:  # noqa: BLE001 — surface error to model
                    tool_result = {"error": str(exc), "tool": tc["name"]}
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
        # Gateway stores per-call cost under "cost_usd".
        cost = usage.get("cost_usd") or usage.get("cost") or {}
        return SpecialistResponse(
            reply=result.get("content", ""),
            tool_calls=result.get("tool_calls", []) or [],
            cost_usd=float(cost.get("total_usd", 0.0)),
        )
