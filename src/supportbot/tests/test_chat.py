"""/chat endpoint shape tests for Support Bot.

Mocks the sb-router specialist with respx — same pattern as NeonCart's tests.
"""

from __future__ import annotations

import httpx
import pytest
import respx
from fastapi.testclient import TestClient

from app.main import ROUTER_URL, app


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(app)


@respx.mock
def test_chat_html_fragment(client: TestClient) -> None:
    route = respx.post(ROUTER_URL).mock(
        return_value=httpx.Response(
            200, json={"reply": "Submit it via the expense portal.", "tool_calls": []}
        )
    )
    resp = client.post("/chat", json={"message": "how do I file an expense"})
    assert resp.status_code == 200
    assert route.called
    body = resp.text
    assert "how do I file an expense" in body
    assert "expense portal" in body


@respx.mock
def test_chat_json_path(client: TestClient) -> None:
    respx.post(ROUTER_URL).mock(
        return_value=httpx.Response(200, json={"reply": "hello", "tool_calls": []})
    )
    resp = client.post(
        "/chat",
        json={"message": "hi"},
        headers={"accept": "application/json"},
    )
    assert resp.status_code == 200
    assert resp.json()["reply"] == "hello"


def test_persona_select_sets_cookie(client: TestClient) -> None:
    resp = client.post("/api/persona/select", json={"persona_id": "42"})
    assert resp.status_code == 200
    assert "supportbot_persona_id" in resp.cookies
