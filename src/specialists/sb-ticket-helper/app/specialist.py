"""sb-ticket-helper — files and updates internal support tickets.

Workflow:
  * If the user wants to file a ticket, call `create_ticket`.
  * If they ask "what's the status of #123", call `get_ticket`.
  * If they ask "show me my tickets", call `list_tickets`.
  * If they want to update one, call `update_ticket`.

Side-effect specialist: writes via create_ticket / update_ticket. The
LLM should never pretend a ticket has been filed if the tool call failed
— always surface the structured error.
"""
from __future__ import annotations

from specialist_base import Specialist, SpecialistRequest, SpecialistResponse


class SbTicketHelper(Specialist):
    NAME = "sb-ticket-helper"
    TOOL_ALLOWLIST = ["list_tickets", "get_ticket", "create_ticket", "update_ticket"]
    SYSTEM_PROMPT = (
        "You help Acme employees file and update support tickets. Use the "
        "tools to do the work — never fabricate ticket IDs. When a tool "
        "returns an error, tell the user honestly and offer to retry. Pick "
        "a sensible category (it, hr, expense, security, hiring, other) "
        "when creating a ticket."
    )

    async def handle(self, req: SpecialistRequest) -> SpecialistResponse:
        messages = [
            {"role": "system", "content": self.SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    f"Persona id: {req.persona_id}. Message: {req.message}"
                ),
            },
        ]
        result = await self.call_gateway(messages, req)
        if result.get("tool_calls"):
            for tc in result["tool_calls"]:
                try:
                    tool_result = await self.call_tool(tc["name"], tc.get("args", {}), req)
                except Exception as exc:  # noqa: BLE001
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
        cost = usage.get("cost", {}) or {}
        return SpecialistResponse(
            reply=result.get("content", ""),
            tool_calls=result.get("tool_calls", []) or [],
            cost_usd=float(cost.get("total_usd", 0.0)),
        )
