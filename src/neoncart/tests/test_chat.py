"""/chat endpoint shape tests.

The real nc-chatbot specialist isn't running in unit tests, so we mock its
HTTP endpoint with respx and verify:
  * /chat forwards the user message
  * a successful response renders an HTML fragment for HTMX
  * a JSON consumer (Accept: application/json) gets the raw JSON back
"""

from __future__ import annotations

import httpx
import pytest
import respx
from fastapi.testclient import TestClient

from app.main import CHATBOT_URL, app


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(app)


@respx.mock
def test_chat_html_fragment(client: TestClient) -> None:
    route = respx.post(CHATBOT_URL).mock(
        return_value=httpx.Response(
            200, json={"reply": "We don't carry mice yet.", "tool_calls": []}
        )
    )

    resp = client.post("/chat", json={"message": "show me mice"})
    assert resp.status_code == 200
    assert route.called
    body = resp.text
    assert "show me mice" in body
    assert "We don&#39;t carry mice yet." in body or "We don't carry mice yet." in body


@respx.mock
def test_chat_json_path(client: TestClient) -> None:
    respx.post(CHATBOT_URL).mock(
        return_value=httpx.Response(
            200, json={"reply": "hello", "tool_calls": []}
        )
    )
    resp = client.post(
        "/chat",
        json={"message": "hi"},
        headers={"accept": "application/json"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["reply"] == "hello"
