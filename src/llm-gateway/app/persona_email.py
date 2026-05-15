"""Persona → email-shaped user identity mapper.

Production demos read better when the `user.id` label on metrics is an actual
email address rather than the internal `u-*` slug. This module owns that
translation so we keep one canonical persona_id everywhere internally
(seed data, FK joins, tests, chat UI cookies) but stamp emails on the
outbound OTel attrs / sigil events.

Mapping rules:
- SupportBot personas (Acme employees) → ``first.last@<SUPPORTBOT_EMAIL_DOMAIN>``
  where ``SUPPORTBOT_EMAIL_DOMAIN`` is read from the environment at import
  time (default ``acme.com``). Helm wires it to ``supportbot.branding.emailDomain``.
- NeonCart personas (external shoppers) → ``first.last@{gmail,hotmail,yahoo,aim}.com``,
  chosen deterministically by hashing the persona_id so a given persona always
  resolves to the same domain.
- Already-email-shaped inputs (containing ``@``) pass through unchanged so
  callers that opt into email-as-persona_id don't double-stamp.
- Unknown personas fall back to a synthesized "first.last" derived from the
  slug, with the domain picked from ``specialist`` ("nc-*" → consumer domains,
  anything else → the configured SupportBot domain).
"""

from __future__ import annotations

import hashlib
import os

#: SupportBot email domain. Resolved at import time from the env var so a
#: helm rebrand (``supportbot.branding.emailDomain``) only needs a pod
#: restart, not a code change.
_SB_DOMAIN: str = os.environ.get("SUPPORTBOT_EMAIL_DOMAIN", "acme.com").strip() or "acme.com"

#: NeonCart consumer domains. ``aim.com`` is intentional — the old AOL
#: instant-messenger domain reads "real consumer" without colliding with
#: real-world inboxes.
_NC_DOMAINS: tuple[str, ...] = ("gmail.com", "hotmail.com", "yahoo.com", "aim.com")

#: SupportBot persona slugs → email local-part. The domain comes from
#: ``_SB_DOMAIN`` so a values.yaml rebrand updates every emission.
_SB_LOCALS: dict[str, str] = {
    "u-emp-norm-1": "norman.adams",
    "u-emp-norm-2": "norah.brooks",
    "u-emp-norm-3": "noah.carter",
    "u-emp-norm-4": "nina.davis",
    "u-emp-norm-5": "nick.evans",
    "u-emp-norm-6": "nora.flynn",
    "u-emp-norm-7": "neel.gupta",
    "u-emp-norm-8": "noah.hill",
    "u-emp-norm-9": "naomi.iyer",
    "u-emp-bypass": "blake.pascal",
    "u-emp-loopy": "laura.olds",
    "u-emp-rude": "rudy.dean",
    "u-emp-test-echo": "echo.ellis",
    "u-emp-test-pii": "peter.parsons",
    "u-emp-toxic": "trent.oakley",
    "u-eric-bad": "eric.bader",
    "u-hr-recruiter": "reese.hartmann",
    "u-jordan-finance": "jordan.finn",
    "u-mara-chen": "mara.chen",
    "u-priya-research": "priya.singh",
    "u-tim-l": "tim.lin",
    "u-waster-1": "wendy.tridge",
    "u-waster-2": "patrick.planski",
    "u-waster-3": "jenna.kowal",
    "u-emp-trivia": "emp.trivia",
}

#: NeonCart persona slugs → full consumer email. Picked manually so each
#: shopper persona reads as a different domain (gmail/hotmail/yahoo/aim).
_NC_EMAILS: dict[str, str] = {
    "u-alice-eng": "alice.engle@gmail.com",
    "u-bob-sales": "bob.salisbury@hotmail.com",
    "u-carol-mktg": "carol.markey@yahoo.com",
    "u-customer-mice": "mick.merritt@gmail.com",
    "u-frustrated": "fran.fume@aim.com",
    "u-norm-1": "nora.miles@gmail.com",
    "u-norm-2": "nate.malone@yahoo.com",
    "u-shopper-deal": "derek.dealey@hotmail.com",
    "u-shopper-gift": "grace.gifford@yahoo.com",
    "u-shopper-injector": "ivan.jenkins@aim.com",
    "u-shopper-loopy": "liam.loomis@gmail.com",
    "u-shopper-pii": "paula.pyles@hotmail.com",
    "u-shopper-refund": "ruby.refind@gmail.com",
    "u-shopper-toxic": "tom.taggart@aim.com",
    "u-waster-4": "wendy.fiver@gmail.com",
    "u-waster-5": "ron.vibes@hotmail.com",
}


def persona_to_email(persona_id: str | None, specialist: str = "") -> str:
    """Return an email-shaped identifier for a demo persona.

    Empty / falsy ``persona_id`` returns ``""`` so callers don't have to
    pre-check. Inputs already containing ``@`` pass through unchanged.
    Unknown personas synthesize a best-effort email from the slug + the
    specialist hint (``nc-*`` → consumer domain, else SupportBot domain).
    """
    if not persona_id:
        return ""
    if "@" in persona_id:
        return persona_id
    if persona_id in _SB_LOCALS:
        return f"{_SB_LOCALS[persona_id]}@{_SB_DOMAIN}"
    if persona_id in _NC_EMAILS:
        return _NC_EMAILS[persona_id]
    local = persona_id[2:] if persona_id.startswith("u-") else persona_id
    parts = [p for p in local.split("-") if p]
    if len(parts) >= 2:
        local = f"{parts[0]}.{'.'.join(parts[1:])}"
    if specialist.startswith("nc-"):
        idx = int(hashlib.md5(persona_id.encode()).hexdigest(), 16) % len(_NC_DOMAINS)
        return f"{local}@{_NC_DOMAINS[idx]}"
    return f"{local}@{_SB_DOMAIN}"
