"""sb-hr-info — HR FAQs: vacation, leave, benefits.

Tools:
  * kb_search    — look up the relevant HR article
  * get_employee — pull the asking employee's role/department, so the
                   answer can be scoped (e.g., parental leave varies by
                   country, salaried vs hourly, etc).
"""
from __future__ import annotations

from specialist_base import Specialist, SpecialistRequest, SpecialistResponse


class SbHrInfo(Specialist):
    NAME = "sb-hr-info"
    TOOL_ALLOWLIST = ["kb_search", "get_employee"]
    SYSTEM_PROMPT = (
        "You answer HR questions for Acme employees (PTO, parental leave, "
        "benefits, payroll). Use kb_search to ground responses in the "
        "official handbook. Use get_employee when the answer depends on "
        "role/department/country. NEVER give legal/tax advice — defer to "
        "the HR team. Be friendly and accurate."
    )

    async def handle(self, req: SpecialistRequest) -> SpecialistResponse:
        messages = [
            {"role": "system", "content": self.SYSTEM_PROMPT},
            {"role": "user", "content": req.message},
        ]
        result = await self.call_gateway(messages, req)
        if result.get("tool_calls"):
            for tc in result["tool_calls"]:
                # Pin get_employee to the requester.
                args = tc.get("args", {})
                if tc.get("name") == "get_employee" and req.persona_id:
                    args["persona_id"] = req.persona_id
                try:
                    tool_result = await self.call_tool(tc["name"], args, req)
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
