"""Persona helpers — reads from Postgres, provides FastAPI dependencies.

The "view as" picker lets a demo SE act as any of the 50 personas seeded by
migration 0001 (CSV at seed_data/personas/personas.csv). Five of those are
"offender" archetypes that trigger specific use-case patterns:

  * tim.lewis@acme.com         — data-theft-tim (exfil)
  * mara.chen@acme.com     — email-cascade (cascade)
  * jordan.reyes@acme.com — data leak
  * priya.singh@acme.com — cost-anomaly-per-user (verbose)
  * eric.marsh@acme.com      — bad-faith requests

Resolution order for the active persona on a request:

  1. ``X-Persona-Id`` header (loadgen / curl / specialist-to-specialist)
  2. ``persona`` cookie (set by POST /api/persona/select from the navbar)
  3. None (caller decides — HTML routes randomize, chat uses request body)

The resolved id is exposed at ``request.state.persona_id`` AND via the
``get_persona_id`` dependency. Every endpoint should set
``ai_o11y.persona_id`` on its active span so traces, logs and metrics agree.
"""

from __future__ import annotations

import random
from typing import Annotated

from fastapi import Cookie, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import Persona

#: Sentinel for "no persona chosen". Spans still get this so dashboards can
#: distinguish "picker showed guest" from "no attribute emitted".
GUEST_PERSONA_ID = "guest@acme.com"


async def get_persona_id(
    request: Request,
    persona: Annotated[str | None, Cookie()] = None,
) -> str | None:
    """Resolve the active persona_id from header or cookie, or None.

    Precedence: ``X-Persona-Id`` header > ``persona`` cookie > None.
    Returning None lets HTML routes pick a random persona on first visit
    while preserving manual dropdown selections via the cookie.
    """
    pid = request.headers.get("X-Persona-Id") or persona
    if pid:
        request.state.persona_id = pid
    return pid


def pick_random_persona_id(personas: list[Persona]) -> str:
    """Pick a random non-guest persona_id, or GUEST_PERSONA_ID if the list
    is empty / only contains guest. Used by HTML routes on first visit so
    the navbar dropdown shows a real user instead of defaulting to guest.
    """
    pool = [p for p in personas if p.persona_id != GUEST_PERSONA_ID]
    if not pool:
        return GUEST_PERSONA_ID
    return random.choice(pool).persona_id


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
