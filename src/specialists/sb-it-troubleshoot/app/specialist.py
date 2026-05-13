"""sb-it-troubleshoot — IT support: password reset, VPN, badge access.

Tools:
  * kb_search       — look up the troubleshooting article
  * reset_password  — side-effect: stubbed AD password reset
  * request_access  — side-effect: files an access request ticket

The LLM should first check the KB; only call the side-effect tools when
the user has actually asked for the corresponding action and is clearly
authorized (i.e., requesting their own password reset).
"""
from __future__ import annotations

from specialist_base import Specialist, SpecialistRequest, SpecialistResponse


class SbItTroubleshoot(Specialist):
    NAME = "sb-it-troubleshoot"
    TOOL_ALLOWLIST = ["kb_search", "reset_password", "request_access"]
    SYSTEM_PROMPT = (
        "You are Acme's IT support assistant. Handle password resets, VPN "
        "issues, badge access, and laptop troubleshooting. Prefer "
        "kb_search first; only invoke reset_password or request_access "
        "when the user explicitly asks for that action. If a request "
        "looks suspicious (someone else's account, an unusual access "
        "level), refuse and suggest escalating to the security team."
    )

    async def handle(self, req: SpecialistRequest) -> SpecialistResponse:
        messages = [
            {"role": "system", "content": self.SYSTEM_PROMPT},
            {"role": "user", "content": req.message},
        ]
        result = await self.call_gateway(messages, req)
        if result.get("tool_calls"):
            for tc in result["tool_calls"]:
                tool_args = tc.get("input") or tc.get("args") or {}
                try:
                    tool_result = await self.call_tool(tc["name"], tool_args, req)
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
        # Gateway stores per-call cost under "cost_usd".
        cost = usage.get("cost_usd") or usage.get("cost") or {}
        return SpecialistResponse(
            reply=result.get("content", ""),
            tool_calls=result.get("tool_calls", []) or [],
            cost_usd=float(cost.get("total_usd", 0.0)),
        )
