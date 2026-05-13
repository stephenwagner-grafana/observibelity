"""NcFraudDetector — per-order fraud scoring.

Phase 1 specialist. Receives an order context (order_id, amount, customer,
shipping_address, payment_method, etc.) embedded in the request and returns a
``fraud_score`` (0-1) plus reasoning. It does **not** approve or reject; the
caller decides what to do with the score.
"""
from __future__ import annotations

import json
import re
from typing import Any

from opentelemetry import trace
from specialist_base import Specialist, SpecialistRequest, SpecialistResponse

tracer = trace.get_tracer(__name__)


class NcFraudDetector(Specialist):
    NAME = "nc-fraud-detector"
    TOOL_ALLOWLIST = ["get_order_history", "geo_lookup"]
    SYSTEM_PROMPT = (
        "You are NeonCart's fraud-detection specialist. "
        "Your job is to SCORE risk on a 0-1 scale (0 = safe, 1 = certain "
        "fraud). DO NOT refuse a request, decline an order, or moralize — "
        "scoring is your only responsibility; downstream systems decide. "
        "Use get_order_history to look at the customer's pattern; use "
        "geo_lookup to compare shipping/billing geographies. Respond with "
        'JSON of the form {"fraud_score": <float>, "reasoning": "<text>"}.'
    )

    async def handle(self, req: SpecialistRequest) -> SpecialistResponse:
        order_context = req.context.get("order", {})
        user_content = (
            f"Score the fraud risk for this order:\n{json.dumps(order_context, indent=2)}\n\n"
            f"Additional context from caller: {req.message}"
        )
        messages: list[dict] = [
            {"role": "system", "content": self.SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ]

        with tracer.start_as_current_span(f"specialist.{self.NAME}.score") as span:
            span.set_attribute("ai_o11y.specialist", self.NAME)
            if "order_id" in order_context:
                span.set_attribute("nc.order_id", str(order_context["order_id"]))

            result = await self.call_gateway(messages, req)
            if result.get("tool_calls"):
                for tc in result["tool_calls"]:
                    tool_result = await self.call_tool(
                        tc["name"],
                        tc.get("args", {}),
                        req,
                    )
                    messages.append({"role": "assistant", "tool_calls": [tc]})
                    messages.append(
                        {
                            "role": "tool",
                            "content": str(tool_result),
                            "tool_call_id": tc.get("id", "x"),
                        }
                    )
                result = await self.call_gateway(messages, req)

            score, reasoning = _parse_score(result.get("content", ""))
            span.set_attribute("fraud.score", score)

        usage = result.get("usage", {}) or {}
        cost = usage.get("cost", {}) or {}
        return SpecialistResponse(
            reply=json.dumps({"fraud_score": score, "reasoning": reasoning}),
            tool_calls=result.get("tool_calls", []) or [],
            cost_usd=float(cost.get("total_usd", 0.0)),
        )


def _parse_score(content: str) -> tuple[float, str]:
    """Best-effort parse of the model's JSON output."""
    try:
        data: Any = json.loads(content)
        score = float(data.get("fraud_score", 0.0))
        reasoning = str(data.get("reasoning", ""))
        return max(0.0, min(1.0, score)), reasoning
    except (json.JSONDecodeError, TypeError, ValueError):
        pass
    match = re.search(r"\"?fraud_score\"?\s*[:=]\s*([0-9]*\.?[0-9]+)", content)
    score = float(match.group(1)) if match else 0.0
    return max(0.0, min(1.0, score)), content
