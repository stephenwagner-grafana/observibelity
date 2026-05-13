"""Mocked-gateway tests for sb-router."""
from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from app.specialist import SbRouter, _classify_local
from specialist_base import SpecialistRequest


def test_metadata() -> None:
    spec = SbRouter()
    assert spec.NAME == "sb-router"
    assert spec.TOOL_ALLOWLIST == []


def test_local_classifier_buckets() -> None:
    assert _classify_local("how do I reset my VPN password") == "it"
    assert _classify_local("when is my vacation balance refreshed") == "hr"
    assert _classify_local("file an expense reimbursement") == "expense"
    assert _classify_local("can I share the secret confidential plan") == "security"
    assert _classify_local("screening a candidate for interview") == "hiring"
    assert _classify_local("read the policy on remote work") == "policy"


@pytest.mark.asyncio
async def test_handle_routes_via_local_fallback() -> None:
    spec = SbRouter()
    # Force the gateway call to raise so we fall back to local classifier
    spec.call_gateway = AsyncMock(side_effect=RuntimeError("boom"))  # type: ignore[method-assign]
    # Capture the forwarded URL via a mock client.post
    spec.client.post = AsyncMock(  # type: ignore[method-assign]
        return_value=_StubResp({"reply": "ok"})
    )
    req = SpecialistRequest(message="please reset my VPN password")
    resp = await spec.handle(req)
    assert resp.reply == "ok"
    # First positional arg is the URL
    call_url = spec.client.post.await_args.args[0]
    assert "sb-it-troubleshoot" in call_url


class _StubResp:
    def __init__(self, data: dict) -> None:
        self._d = data
        self.status_code = 200

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self._d
