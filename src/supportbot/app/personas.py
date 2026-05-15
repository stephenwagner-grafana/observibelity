"""Persona helpers for Support Bot — mirrors src/neoncart/app/personas.py.

Both apps read the same ``personas`` table (the alembic migration in
migrations/versions/0001_initial.py extends the original NeonCart schema
rather than forking). The "view as" picker, X-Persona-Id header behavior,
and ``ai_o11y.persona_id`` span attribute all match the NeonCart contract.

Resolution order for the active persona on a request:

  1. ``X-Persona-Id`` header (loadgen / curl / specialist-to-specialist)
  2. ``supportbot_persona_id`` cookie (set by POST /api/persona/select)
  3. ``guest@acme.com`` fallback (no persona chosen)

NOTE: The Support Bot main.py already wires its own `_persona_id` helper
and persona endpoints. This module exists so future refactors share the
NeonCart shape — if Support Bot moves to a `Depends(get_persona_id)`
pattern, the wire-up is a one-line import swap.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Cookie, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import Persona

#: Cookie name — DIFFERENT from NeonCart's "persona" so both apps can run
#: on the same domain without colliding. The picker JS uses this name too.
PERSONA_COOKIE = "supportbot_persona_id"

#: Returned when no header/cookie has been set. Spans still get a value so
#: dashboards can distinguish "no picker chosen" from "no attribute emitted".
GUEST_PERSONA_ID = "guest@acme.com"


async def get_persona_id(
    request: Request,
    supportbot_persona_id: Annotated[str | None, Cookie()] = None,
) -> str:
    """Resolve the active persona_id for this request.

    Precedence: ``X-Persona-Id`` header > ``supportbot_persona_id`` cookie
    > ``guest@acme.com``. Also stashes the resolved id on ``request.state``.
    """
    pid = (
        request.headers.get("X-Persona-Id")
        or supportbot_persona_id
        or GUEST_PERSONA_ID
    )
    request.state.persona_id = pid
    return pid


async def list_personas(session: AsyncSession) -> list[Persona]:
    """Fetch all personas from Postgres, ordered by name for stable dropdowns."""
    result = await session.execute(select(Persona).order_by(Persona.name))
    return list(result.scalars().all())


def set_persona_span_attr(persona_id: str | None) -> None:
    """Attach ``ai_o11y.persona_id`` to the current span if tracing is active."""
    if not persona_id:
        return
    try:
        from opentelemetry import trace

        span = trace.get_current_span()
        if span and span.is_recording():
            span.set_attribute("ai_o11y.persona_id", persona_id)
    except Exception:  # noqa: BLE001 — never break a request on telemetry
        pass
