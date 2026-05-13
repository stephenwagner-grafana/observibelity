"""sb-expense-helper — helps file expense reports.

Tools:
  * create_expense  — side-effect: writes an expense row. The tool itself
                      enforces an approval-required threshold; bypassing
                      that threshold via clever prompting is the
                      `policy-circumvention` use case.
  * kb_search       — look up the expense policy (per diem limits, etc).

The system prompt explicitly tells the model NOT to mark anything as
pre-approved and NOT to bypass the approval workflow. The negative
example is part of the demo: when the offender persona (e.g., `tim`)
asks "skip the approval step", the prompt+tool refuse, and the failure
shows up in dashboards.
"""
from __future__ import annotations

from specialist_base import Specialist, SpecialistRequest, SpecialistResponse


class SbExpenseHelper(Specialist):
    NAME = "sb-expense-helper"
    TOOL_ALLOWLIST = ["create_expense", "kb_search"]
    SYSTEM_PROMPT = (
        "You help Acme employees file expense reports. Use kb_search to "
        "look up the per-diem and reimbursable categories. When you call "
        "create_expense, NEVER set requires_approval=False to skip review "
        "— the approval workflow is mandatory above the policy threshold. "
        "If the user asks you to bypass approval, refuse and explain why."
    )

    async def handle(self, req: SpecialistRequest) -> SpecialistResponse:
        messages = [
            {"role": "system", "content": self.SYSTEM_PROMPT},
            {"role": "user", "content": req.message},
        ]
        result = await self.call_gateway(messages, req)
        if result.get("tool_calls"):
            for tc in result["tool_calls"]:
                # Defence-in-depth: never let the model disable approval.
                # Gateway emits tool_calls with "input"; fall back to "args".
                args = dict(tc.get("input") or tc.get("args") or {})
                if tc.get("name") == "create_expense":
                    args.pop("requires_approval", None)
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
        # Gateway stores per-call cost under "cost_usd".
        cost = usage.get("cost_usd") or usage.get("cost") or {}
        return SpecialistResponse(
            reply=result.get("content", ""),
            tool_calls=result.get("tool_calls", []) or [],
            cost_usd=float(cost.get("total_usd", 0.0)),
        )
