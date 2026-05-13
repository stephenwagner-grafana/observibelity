"""sb-router — dispatcher for Ask Acme.

Receives every chat turn from the supportbot frontend, asks the LLM to
classify the user's question into one of ~9 buckets, then forwards the
request to the matching downstream specialist (sb-kb-search,
sb-policy-finder, sb-it-troubleshoot, etc.).

The router never calls tools directly; its TOOL_ALLOWLIST is intentionally
empty. The downstream specialist is the one that holds the privileged
tool allowlist for its domain.
"""
from __future__ import annotations

import os

import httpx
from opentelemetry import trace

from specialist_base import Specialist, SpecialistRequest, SpecialistResponse

tracer = trace.get_tracer(__name__)

# Mapping of routing decisions to the k8s service that should handle them.
# Keys are lowercase categories the LLM is asked to emit.
_ROUTES: dict[str, str] = {
    "kb": "sb-kb-search",
    "policy": "sb-policy-finder",
    "ticket": "sb-ticket-helper",
    "employee": "sb-employee-info",
    "it": "sb-it-troubleshoot",
    "hr": "sb-hr-info",
    "expense": "sb-expense-helper",
    "security": "sb-security-handler",
    "hiring": "sb-hiring-helper",
    "escalate": "sb-escalator",
}

DEFAULT_TARGET = "sb-kb-search"


def _classify_local(message: str) -> str:
    """Cheap keyword classifier — used as a fallback if the LLM stalls.

    Phase 2's full router lets the model pick. This is the deterministic
    backup so tests + cold paths still produce a sensible route.
    """
    m = message.lower()
    if any(k in m for k in ("vpn", "password", "laptop", "badge", "wifi")):
        return "it"
    if any(k in m for k in ("vacation", "pto", "benefits", "leave", "parental")):
        return "hr"
    if "expense" in m or "reimburse" in m:
        return "expense"
    if any(k in m for k in ("secret", "confidential", "leak")):
        return "security"
    if any(k in m for k in ("candidate", "hire", "interview", "screening")):
        return "hiring"
    if any(k in m for k in ("policy", "code of conduct", "handbook")):
        return "policy"
    if any(k in m for k in ("ticket", "file a ticket", "issue")):
        return "ticket"
    if any(k in m for k in ("my profile", "my history", "my order")):
        return "employee"
    if any(k in m for k in ("escalate", "human", "manager")):
        return "escalate"
    return "kb"


class SbRouter(Specialist):
    NAME = "sb-router"
    TOOL_ALLOWLIST: list[str] = []
    SYSTEM_PROMPT = (
        "You are the dispatcher for Acme's internal support assistant. "
        "Classify the user's question into one of these categories: "
        "kb, policy, ticket, employee, it, hr, expense, security, hiring, "
        "escalate. Reply with a single lowercase word — the category — "
        "and nothing else."
    )

    async def handle(self, req: SpecialistRequest) -> SpecialistResponse:
        # Ask the LLM to pick a route; fall back to the keyword classifier.
        messages = [
            {"role": "system", "content": self.SYSTEM_PROMPT},
            {"role": "user", "content": req.message},
        ]
        try:
            result = await self.call_gateway(messages, req, max_tokens=12)
            content = (result.get("content") or "").strip().lower()
            route = content if content in _ROUTES else _classify_local(req.message)
        except Exception:  # noqa: BLE001 — never block on routing
            route = _classify_local(req.message)

        target = _ROUTES.get(route, DEFAULT_TARGET)
        with tracer.start_as_current_span(f"{self.NAME}.forward") as span:
            span.set_attribute("ai_o11y.specialist", self.NAME)
            span.set_attribute("ai_o11y.sb.route", route)
            span.set_attribute("ai_o11y.sb.target", target)
            url = f"http://{target}/v1/run"
            try:
                resp = await self.client.post(
                    url,
                    json={
                        "message": req.message,
                        "persona_id": req.persona_id,
                        "session_id": req.session_id,
                        "usecase": req.usecase,
                        "context": {**req.context, "router_route": route},
                    },
                    timeout=30.0,
                )
                resp.raise_for_status()
                data = resp.json()
            except httpx.HTTPError as exc:
                span.record_exception(exc)
                return SpecialistResponse(
                    reply=f"(Routing failed for {route!r}: {exc})",
                    tool_calls=[],
                )
        return SpecialistResponse(
            reply=data.get("reply", ""),
            tool_calls=data.get("tool_calls", []) or [],
            cost_usd=float(data.get("cost_usd", 0.0) or 0.0),
        )
