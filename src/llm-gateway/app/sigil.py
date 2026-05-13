"""Sigil generation-event emitter.

Phase 1: builds the canonical event payload and logs it to stdout as a single
JSON line so OTel/Loki/Promtail can scoop it up regardless of where the
gateway runs. Phase 2 adds an OTLP-logs exporter that ships the same payload
straight to the Sigil ingest endpoint.

Keep the field names aligned with `docs/PROVIDERS.md` and the dashboard
queries on `ai-obs-app-neoncart` — renaming a field here means renaming it
everywhere it's used.
"""
from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from typing import Any

from .providers.base import CompleteRequest, CompleteResponse

log = logging.getLogger(__name__)


def build_event(
    req: CompleteRequest,
    resp: CompleteResponse,
    span_id: str = "",
    trace_id: str = "",
) -> dict[str, Any]:
    """Build the canonical Sigil generation-event payload."""
    cost = resp.usage.get("cost_usd") or {}
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "trace_id": trace_id,
        "span_id": span_id,
        # gen_ai.* — OTel GenAI semantic conventions
        "gen_ai.system": resp.provider,
        "gen_ai.request.model": req.model_override or resp.model,
        "gen_ai.response.model": resp.model,
        "gen_ai.usage.input_tokens": resp.usage.get("input_tokens", 0),
        "gen_ai.usage.output_tokens": resp.usage.get("output_tokens", 0),
        "gen_ai.usage.cost.input_usd": cost.get("input_usd", 0.0),
        "gen_ai.usage.cost.output_usd": cost.get("output_usd", 0.0),
        "gen_ai.usage.cost.total_usd": cost.get("total_usd", 0.0),
        "gen_ai.response.finish_reason": resp.finish_reason,
        # ai_o11y.* — demo-specific labels for use-case + persona drilldown
        "ai_o11y.usecase": req.ai_o11y.get("usecase"),
        "ai_o11y.persona_id": req.ai_o11y.get("persona_id"),
        "ai_o11y.specialist": req.specialist,
        "traffic_origin": req.ai_o11y.get("traffic_origin", "continuous"),
        # Content — last user message + the completion. Keeps payload small and
        # avoids logging full chat history (which can contain PII in the demo).
        "messages": req.messages[-1:],
        "completion": resp.content,
        "tool_calls": resp.tool_calls,
    }


async def emit_generation_event(
    req: CompleteRequest,
    resp: CompleteResponse,
    span_id: str = "",
    trace_id: str = "",
) -> None:
    """Phase 1: write the event as one JSON line to stdout.

    Phase 2 will replace the print with an OTLP-logs export to Sigil — the
    payload shape stays identical so the dashboards don't have to change.
    """
    event = build_event(req, resp, span_id=span_id, trace_id=trace_id)
    try:
        sys.stdout.write(json.dumps(event, default=str) + "\n")
        sys.stdout.flush()
    except Exception as exc:  # noqa: BLE001 — never let logging break the request.
        log.warning("failed to emit Sigil event: %s", exc)
