"""Persona picker endpoint shape + resolution tests.

The real Postgres isn't running in unit tests; we mock the db.get_session
dependency to return a stub that yields zero personas, and respx the chat
proxy so we can assert the persona flows through to nc-chatbot.
"""

from __future__ import annotations

from typing import AsyncIterator

import httpx
import pytest
import respx
from fastapi.testclient import TestClient

from app import db
from app.main import CHATBOT_URL, app
from app.personas import GUEST_PERSONA_ID


class _StubResult:
    """Mimics SQLAlchemy's Result.scalars().all() for an empty table."""

    def scalars(self) -> "_StubResult":
        return self

    def all(self) -> list:
        return []


class _StubSession:
    async def execute(self, *_args, **_kwargs) -> _StubResult:
        return _StubResult()


async def _stub_get_session() -> AsyncIterator[_StubSession]:
    yield _StubSession()


@pytest.fixture(scope="module")
def client() -> TestClient:
    app.dependency_overrides[db.get_session] = _stub_get_session
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(db.get_session, None)


def test_api_personas_returns_json_list(client: TestClient) -> None:
    resp = client.get("/api/personas")
    assert resp.status_code == 200
    assert resp.json() == []


def test_api_persona_select_sets_cookie(client: TestClient) -> None:
    resp = client.post("/api/persona/select", json={"persona_id": "tim.lewis@acme.com"})
    assert resp.status_code == 200
    assert resp.json()["persona_id"] == "tim.lewis@acme.com"
    # Set-Cookie must include path=/ and SameSite=Lax for the demo to work
    set_cookie = resp.headers.get("set-cookie", "")
    assert "persona=tim.lewis@acme.com" in set_cookie
    assert "Path=/" in set_cookie
    assert "lax" in set_cookie.lower()


@respx.mock
def test_chat_propagates_header_persona(client: TestClient) -> None:
    """X-Persona-Id header must override any persona_id in the body."""
    route = respx.post(CHATBOT_URL).mock(
        return_value=httpx.Response(200, json={"reply": "ok", "tool_calls": []})
    )
    resp = client.post(
        "/chat",
        json={"message": "hi", "persona_id": "other@acme.com"},
        headers={"X-Persona-Id": "priya.singh@acme.com"},
    )
    assert resp.status_code == 200
    assert route.called
    forwarded = route.calls.last.request
    body = forwarded.read().decode()
    assert "priya.singh@acme.com" in body
    assert "other@acme.com" not in body


@respx.mock
def test_chat_propagates_cookie_persona(client: TestClient) -> None:
    """Without a header, the persona cookie should drive propagation."""
    route = respx.post(CHATBOT_URL).mock(
        return_value=httpx.Response(200, json={"reply": "ok", "tool_calls": []})
    )
    resp = client.post(
        "/chat",
        json={"message": "hi"},
        cookies={"persona": "mara.chen@acme.com"},
    )
    assert resp.status_code == 200
    forwarded = route.calls.last.request
    body = forwarded.read().decode()
    assert "mara.chen@acme.com" in body


@respx.mock
def test_chat_defaults_to_guest(client: TestClient) -> None:
    """No header, no cookie, no body → forward guest@acme.com downstream."""
    route = respx.post(CHATBOT_URL).mock(
        return_value=httpx.Response(200, json={"reply": "ok", "tool_calls": []})
    )
    resp = client.post("/chat", json={"message": "hi"})
    assert resp.status_code == 200
    forwarded = route.calls.last.request
    body = forwarded.read().decode()
    assert GUEST_PERSONA_ID in body
