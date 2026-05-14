"""Persona → email-shaped user identity mapper.

Production demos read better when the `user.id` label on metrics is an actual
email address rather than the internal `u-*` slug. This module owns that
translation so we keep one canonical persona_id everywhere internally
(seed data, FK joins, tests, chat UI cookies) but stamp emails on the
outbound OTel attrs / sigil events.

Mapping rules:
- SupportBot personas (Acme employees) → ``first.last@acme.com``.
- NeonCart personas (external shoppers) → ``first.last@{gmail,hotmail,yahoo}.com``,
  chosen deterministically by hashing the persona_id so a given persona always
  resolves to the same domain.
- Unknown personas fall back to a synthesized "first.last" derived from the
  slug, with the domain picked from ``specialist`` ("nc-*" → consumer domains,
  anything else → ``@acme.com``).
"""

from __future__ import annotations

import hashlib

# Static map — wins over the heuristic so Priya (employee who also shops on
# NeonCart) and Eric (employee who probes NeonCart) keep a single identity
# across both apps. Edit here when adding new personas to baseline.js.
_PERSONA_EMAIL_MAP: dict[str, str] = {
    # ── SupportBot internal employees (@acme.com) ──────────────────────
    "u-emp-norm-1": "norman.adams@acme.com",
    "u-emp-norm-2": "norah.brooks@acme.com",
    "u-emp-norm-3": "noah.carter@acme.com",
    "u-emp-norm-4": "nina.davis@acme.com",
    "u-emp-norm-5": "nick.evans@acme.com",
    "u-emp-norm-6": "nora.flynn@acme.com",
    "u-emp-norm-7": "neel.gupta@acme.com",
    "u-emp-norm-8": "noah.hill@acme.com",
    "u-emp-norm-9": "naomi.iyer@acme.com",
    "u-emp-bypass": "blake.pascal@acme.com",
    "u-emp-loopy": "laura.olds@acme.com",
    "u-emp-rude": "rudy.dean@acme.com",
    "u-emp-test-echo": "echo.ellis@acme.com",
    "u-emp-test-pii": "peter.parsons@acme.com",
    "u-emp-toxic": "trent.oakley@acme.com",
    "u-eric-bad": "eric.bader@acme.com",
    "u-hr-recruiter": "reese.hartmann@acme.com",
    "u-jordan-finance": "jordan.finn@acme.com",
    "u-mara-chen": "mara.chen@acme.com",
    "u-priya-research": "priya.singh@acme.com",
    "u-tim-l": "tim.lin@acme.com",
    "u-waster-1": "wendy.tridge@acme.com",
    "u-waster-2": "patrick.planski@acme.com",
    "u-waster-3": "jenna.kowal@acme.com",
    # ── NeonCart external customers (gmail/hotmail/yahoo) ──────────────
    "u-alice-eng": "alice.engle@gmail.com",
    "u-bob-sales": "bob.salisbury@hotmail.com",
    "u-carol-mktg": "carol.markey@yahoo.com",
    "u-customer-mice": "mick.merritt@gmail.com",
    "u-frustrated": "fran.fume@hotmail.com",
    "u-norm-1": "nora.miles@gmail.com",
    "u-norm-2": "nate.malone@yahoo.com",
    "u-shopper-deal": "derek.dealey@hotmail.com",
    "u-shopper-gift": "grace.gifford@yahoo.com",
    "u-shopper-injector": "ivan.jenkins@yahoo.com",
    "u-shopper-loopy": "liam.loomis@gmail.com",
    "u-shopper-pii": "paula.pyles@hotmail.com",
    "u-shopper-refund": "ruby.refind@gmail.com",
    "u-shopper-toxic": "tom.taggart@yahoo.com",
    "u-waster-4": "wendy.fiver@gmail.com",
    "u-waster-5": "ron.vibes@hotmail.com",
}

_NC_DOMAINS: tuple[str, ...] = ("gmail.com", "hotmail.com", "yahoo.com")


def persona_to_email(persona_id: str | None, specialist: str = "") -> str:
    """Return an email-shaped identifier for a demo persona.

    Empty / falsy ``persona_id`` returns ``""`` so callers don't have to
    pre-check. Unknown personas synthesize a best-effort email from the
    slug + the specialist hint (``nc-*`` → consumer domain, else acme.com).
    """
    if not persona_id:
        return ""
    if persona_id in _PERSONA_EMAIL_MAP:
        return _PERSONA_EMAIL_MAP[persona_id]
    local = persona_id[2:] if persona_id.startswith("u-") else persona_id
    parts = [p for p in local.split("-") if p]
    if len(parts) >= 2:
        local = f"{parts[0]}.{'.'.join(parts[1:])}"
    if specialist.startswith("nc-"):
        idx = int(hashlib.md5(persona_id.encode()).hexdigest(), 16) % len(_NC_DOMAINS)
        return f"{local}@{_NC_DOMAINS[idx]}"
    return f"{local}@acme.com"
