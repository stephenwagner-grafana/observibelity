"""reset_password — STUB: pretends to call Active Directory.

Phase 2 ships a stub; Phase 3 wires real AD. We still mark it as a
side-effect tool with IDEMPOTENT=True (resetting twice in quick
succession is fine — the user gets a fresh token both times). No
backing tables — the real implementation would talk to AD via LDAP/Graph.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from tool_base import Tool

log = logging.getLogger("reset_password")


class ResetPasswordArgs(BaseModel):
    persona_id: str = Field(..., min_length=1, max_length=64)
    method: str = Field("email", description="email | sms | totp")


class ResetPasswordResult(BaseModel):
    persona_id: str
    method: str
    requested_at: datetime
    status: str  # "queued" — the real AD call lands in Phase 3


class ResetPassword(Tool):
    NAME = "reset_password"
    SIDE_EFFECT = True
    IDEMPOTENT = True
    TIMEOUT_SEC = 5
    MAX_CONCURRENCY = 10
    CACHE_TTL_SEC = 0
    RETRIES = 0  # idempotent BUT stub — avoid spamming the future real AD
    BACKING_TABLES = []  # no DB
    REQUIRES_SECRETS = ["AD_BIND_PASSWORD"]  # for future real impl
    ALLOWED_CALLERS = ["sb-it-troubleshoot", "sb-escalator"]
    REPLICAS = 1

    Args = ResetPasswordArgs
    Result = ResetPasswordResult

    async def execute(
        self,
        args: ResetPasswordArgs,
        session: AsyncSession | None = None,
    ) -> ResetPasswordResult:
        log.info(
            "reset_password STUB invoked for persona=%s method=%s",
            args.persona_id,
            args.method,
        )
        return ResetPasswordResult(
            persona_id=args.persona_id,
            method=args.method,
            requested_at=datetime.now(tz=timezone.utc),
            status="queued",
        )
