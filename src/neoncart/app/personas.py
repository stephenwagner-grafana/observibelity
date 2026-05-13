"""Persona helpers — reads from Postgres, provides FastAPI dependencies.

The "view as" picker lets a demo SE act as any of the 50 personas seeded by
migration 0001 (CSV at seed_data/personas/personas.csv). Five of those are
"offender" archetypes that trigger specific use-case patterns:

  * u-tim-l         — data-theft-tim (exfil)
  * u-mara-chen     — email-cascade (cascade)
  * u-jordan-finance — data leak
  * u-priya-research — cost-anomaly-per-user (verbose)
  * u-eric-bad      — bad-faith requests

Resolution order for the active persona on a request:

  1. ``X-Persona-Id`` header (loadgen / curl / specialist-to-specialist)
  2. ``persona`` cookie (set by POST /api/persona/select from the navbar)
  3. ``u-guest`` fallback (no persona chosen)

The resolved id is exposed at ``request.state.persona_id`` AND via the
``get_persona_id`` dependency. Every endpoint should set
``ai_o11y.persona_id`` on its active span so traces, logs and metrics agree.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Cookie, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import Persona

#: Returned when no header/cookie has been set. Spans still get a value so
#: dashboards can distinguish "no picker chosen" from "no attribute emitted".
GUEST_PERSONA_ID = "u-guest"


async def get_persona_id(
    request: Request,
    persona: Annotated[str | None, Cookie()] = None,
) -> str:
    """Resolve the active persona_id for this request.

    Precedence: ``X-Persona-Id`` header > ``persona`` cookie > ``u-guest``.
    Also stashes the resolved id on ``request.state`` so middleware /
    template globals can pick it up without re-resolving the dependency.
    """
    pid = request.headers.get("X-Persona-Id") or persona or GUEST_PERSONA_ID
    request.state.persona_id = pid
    return pid


async def list_personas(session: AsyncSession) -> list[Persona]:
    """Fetch all personas from Postgres, ordered by name for stable dropdowns.

    Returns an empty list if the table is empty or not yet migrated — the
    caller should fall back to a guest-only experience in that case.
    """
    result = await session.execute(select(Persona).order_by(Persona.name))
    return list(result.scalars().all())


def set_persona_span_attr(persona_id: str | None) -> None:
    """Attach ``ai_o11y.persona_id`` to the current span if tracing is active.

    Safe to call from any handler — silently no-ops if OTel isn't wired up.
    """
    if not persona_id:
        return
    try:
        from opentelemetry import trace

        span = trace.get_current_span()
        if span and span.is_recording():
            span.set_attribute("ai_o11y.persona_id", persona_id)
    except Exception:  # noqa: BLE001 — never break a request on telemetry
        pass
