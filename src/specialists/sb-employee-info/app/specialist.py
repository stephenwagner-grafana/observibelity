"""sb-employee-info — answers an employee's questions about their *own* data.

Tool calls:
  * get_employee — name / role / department
  * get_employee_history — past orders + conversations

Risk surface: if the LLM is tricked into supplying another employee's
persona_id, this becomes the `data-theft-tim` flow. The downstream
`get_employee` tool enforces ALLOWED_CALLERS — the demo proves the
defence-in-depth pattern by also having this specialist's prompt refuse
to look up anyone other than the requester.

`get_employee_history` is the tool that triggers the mice-rca-style
schema error when called with persona_ids starting with `sensitive-`.
"""
from __future__ import annotations

from specialist_base import Specialist, SpecialistRequest, SpecialistResponse


class SbEmployeeInfo(Specialist):
    NAME = "sb-employee-info"
    TOOL_ALLOWLIST = ["get_employee", "get_employee_history"]
    SYSTEM_PROMPT = (
        "You answer employee questions about their OWN profile and order/"
        "support history. ONLY look up the persona_id from the request — "
        "NEVER another employee's. If the user asks about someone else's "
        "data, refuse politely and suggest filing a ticket with HR. "
        "Use get_employee for profile and get_employee_history for past "
        "activity. Be concise."
    )

    async def handle(self, req: SpecialistRequest) -> SpecialistResponse:
        # Pin the tool calls to the *requester's* persona_id so the model
        # can't be cajoled into looking up a different employee.
        messages = [
            {"role": "system", "content": self.SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    f"You are speaking to persona_id={req.persona_id}. "
                    f"Use ONLY that persona_id in tool calls. "
                    f"Question: {req.message}"
                ),
            },
        ]
        result = await self.call_gateway(messages, req)
        if result.get("tool_calls"):
            for tc in result["tool_calls"]:
                args = tc.get("args", {})
                # Defence-in-depth: rewrite persona_id arg to the requester's.
                if "persona_id" in args and req.persona_id:
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
