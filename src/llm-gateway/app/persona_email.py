"""Persona → email-shaped user identity mapper.

Historically this module translated internal `u-*` slugs into email addresses
for OTel emission. As of the 2026-05-15 migration the entire stack stores
emails as the canonical persona_id (seed DB, k6 payloads, frontend cookies,
specialist calls), so this function is mostly a pass-through.

It still does three things:

1. Returns an empty string for falsy input so callers don't have to pre-check.
2. Passes email-shaped input straight through.
3. Best-effort synthesizes an email for any stray non-email persona that
   slips in (defensive — should never happen in steady state, but keeps the
   metric label well-formed if a legacy slug ever shows up). The domain
   comes from ``SUPPORTBOT_EMAIL_DOMAIN`` (env, populated by helm from
   ``supportbot.branding.emailDomain``), defaulting to ``acme.com``. NeonCart
   specialists (``nc-*``) get a deterministic consumer domain instead.
"""

from __future__ import annotations

import hashlib
import os

#: SupportBot email domain. Resolved at import time from the env var so a
#: helm rebrand (``supportbot.branding.emailDomain``) only needs a pod
#: restart, not a code change.
_SB_DOMAIN: str = os.environ.get("SUPPORTBOT_EMAIL_DOMAIN", "acme.com").strip() or "acme.com"

#: NeonCart consumer domains. Used for ``nc-*`` specialists when an
#: unrecognized persona_id slips through; deterministic by hash so the
#: same persona always resolves to the same domain.
_NC_DOMAINS: tuple[str, ...] = ("gmail.com", "hotmail.com", "yahoo.com", "aim.com")


def persona_to_email(persona_id: str | None, specialist: str = "") -> str:
    """Return an email-shaped identifier for a demo persona.

    Steady-state callers send emails and get them back unchanged. The
    fallback branch only triggers on stray legacy slugs (e.g., a test fixture
    that hard-codes a non-email persona_id).
    """
    if not persona_id:
        return ""
    if "@" in persona_id:
        return persona_id
    # Defensive synthesis — strip leading "u-" if present, split on hyphens,
    # join as "first.last", append a domain.
    local = persona_id[2:] if persona_id.startswith("u-") else persona_id
    parts = [p for p in local.split("-") if p]
    if len(parts) >= 2:
        local = f"{parts[0]}.{'.'.join(parts[1:])}"
    if specialist.startswith("nc-"):
        idx = int(hashlib.md5(persona_id.encode()).hexdigest(), 16) % len(_NC_DOMAINS)
        return f"{local}@{_NC_DOMAINS[idx]}"
    return f"{local}@{_SB_DOMAIN}"
