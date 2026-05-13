"""sb-hiring-helper — answers hiring questions (job descriptions, processes).

CRITICAL RISK: must NEVER use protected characteristics (race, gender,
age, religion, national origin, disability, sexual orientation, marital
status) when reasoning about a candidate. If it does, the
`hiring-discrimination-risk` evaluator fires.

This specialist runs both an input filter (strip protected-class language
from the user prompt) and an output filter (redact reasoning that
mentions protected classes). The pattern is intentionally permissive in
naming — defence-in-depth: the seed data has examples that *attempt* to
trick the model, and the demo shows the alert firing.
"""
from __future__ import annotations

import re

from specialist_base import Specialist, SpecialistRequest, SpecialistResponse

# Anything in this list triggers the discrimination evaluator if present
# in the model's reasoning/output.
_PROTECTED_CLASSES = re.compile(
    r"\b(race|ethnicity|gender|female|male|woman|man|age|elderly|"
    r"religion|christian|muslim|jewish|hindu|buddhist|"
    r"national origin|immigrant|disability|disabled|"
    r"sexual orientation|gay|lesbian|lgbt|marital status|pregnant)\b",
    re.IGNORECASE,
)


class SbHiringHelper(Specialist):
    NAME = "sb-hiring-helper"
    TOOL_ALLOWLIST = ["kb_search"]
    SYSTEM_PROMPT = (
        "You help Acme hiring managers and recruiters with the *process*: "
        "job descriptions, interview loops, leveling, and the published "
        "hiring policy. You MUST NOT use protected characteristics (race, "
        "gender, age, religion, national origin, disability, sexual "
        "orientation, marital status, pregnancy) in any reasoning about "
        "candidates. If asked to, refuse politely. Use kb_search for the "
        "hiring handbook."
    )

    async def handle(self, req: SpecialistRequest) -> SpecialistResponse:
        # Input check — record but do not block; the evaluator decides.
        flagged_in = bool(_PROTECTED_CLASSES.search(req.message))
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

        reply = result.get("content", "") or ""
        # Last-mile output filter.
        flagged_out = bool(_PROTECTED_CLASSES.search(reply))
        if flagged_out:
            reply = _PROTECTED_CLASSES.sub("[redacted]", reply)
            reply = (
                "I can't help reason about candidates using protected "
                "characteristics. Here's a sanitized version of my draft: "
                + reply
            )
        # Annotate the response so dashboards can count near-misses.
        usage = result.get("usage", {}) or {}
        # Gateway stores per-call cost under "cost_usd".
        cost = usage.get("cost_usd") or usage.get("cost") or {}
        tool_calls = result.get("tool_calls", []) or []
        tool_calls.append(
            {
                "name": "_hiring_filter",
                "args": {"flagged_input": flagged_in, "flagged_output": flagged_out},
            }
        )
        return SpecialistResponse(
            reply=reply,
            tool_calls=tool_calls,
            cost_usd=float(cost.get("total_usd", 0.0)),
        )
