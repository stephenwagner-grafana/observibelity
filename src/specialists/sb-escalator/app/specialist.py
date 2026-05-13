"""sb-escalator — escalates difficult/refused queries to humans.

Used when:
  * Another specialist refused.
  * The user asked for a human ("escalate", "manager").
  * The bot can't classify the request confidently.

Tools:
  * page_oncall   — pages the on-call rotation (side-effect; STUBBED in Phase 2)
  * create_ticket — files a human-handled ticket

Note: `page_oncall` is intentionally NOT in the Phase 2 default tool set
yet (Phase 3 adds it). In Phase 2 we approximate paging by creating a
high-priority ticket via create_ticket.
"""
from __future__ import annotations

from specialist_base import Specialist, SpecialistRequest, SpecialistResponse


class SbEscalator(Specialist):
    NAME = "sb-escalator"
    # Phase 2: only create_ticket. Once page_oncall lands, add it here.
    TOOL_ALLOWLIST = ["create_ticket"]
    SYSTEM_PROMPT = (
        "You handle escalations. File a high-priority ticket via "
        "create_ticket with category='escalation' so a human can pick it "
        "up. Reply to the user with the ticket id and a polite "
        "acknowledgement. Do NOT attempt to resolve the underlying "
        "issue yourself."
    )

    async def handle(self, req: SpecialistRequest) -> SpecialistResponse:
        # Always file an escalation ticket — no LLM round-trip needed for
        # the action, but we ask the LLM to write the user-facing reply.
        subject = f"Escalation: {req.message[:80]}"
        try:
            ticket_result = await self.call_tool(
                "create_ticket",
                {
                    "subject": subject,
                    "body": req.message,
                    "category": "escalation",
                    "persona_id": req.persona_id,
                },
                req,
            )
        except Exception as exc:  # noqa: BLE001
            ticket_result = {"error": str(exc)}

        messages = [
            {"role": "system", "content": self.SYSTEM_PROMPT},
            {"role": "user", "content": req.message},
            {
                "role": "user",
                "content": f"Ticket has been filed: {ticket_result}. Acknowledge to the user.",
            },
        ]
        result = await self.call_gateway(messages, req)
        usage = result.get("usage", {}) or {}
        # Gateway stores per-call cost under "cost_usd".
        cost = usage.get("cost_usd") or usage.get("cost") or {}
        return SpecialistResponse(
            reply=result.get("content", ""),
            tool_calls=[
                {"name": "create_ticket", "args": {"subject": subject}, "result": ticket_result}
            ],
            cost_usd=float(cost.get("total_usd", 0.0)),
        )
