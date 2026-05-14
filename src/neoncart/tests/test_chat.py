"""/chat endpoint shape tests.

The real nc-chatbot specialist isn't running in unit tests, so we mock its
HTTP endpoint with respx and verify:
  * /chat forwards the user message and returns a JSON ChatResponse
  * the new model/provider/actions/products/sigil_url fields are surfaced
    on the wire (the widget renders these client-side)
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
def test_chat_returns_json_with_reply(client: TestClient) -> None:
    route = respx.post(CHATBOT_URL).mock(
        return_value=httpx.Response(
            200, json={"reply": "We don't carry mice yet.", "tool_calls": []}
        )
    )

    resp = client.post("/chat", json={"message": "show me mice"})
    assert resp.status_code == 200
    assert route.called
    data = resp.json()
    assert data["reply"] == "We don't carry mice yet."
    assert data["tool_calls"] == []
    # New fields default to empty/None but must be present on the wire so the
    # widget can read them without optional-chaining everywhere.
    assert data["model"] is None
    assert data["provider"] is None
    assert data["actions"] == []
    assert data["products"] == []


@respx.mock
def test_chat_surfaces_model_actions_products(client: TestClient) -> None:
    """The new specialist fields flow through /chat unchanged into the JSON."""
    respx.post(CHATBOT_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "reply": "Here are some keyboards.",
                "tool_calls": [{"name": "search_products"}],
                "model": "claude-sonnet-4-6",
                "provider": "anthropic",
                "actions": [{"type": "navigate", "target": "category", "value": "peripherals"}],
                "products": [
                    {"id": 1, "sku": "KB-001", "name": "Neon Keyboard", "price_usd": 99.99}
                ],
                "cost_usd": 0.0012,
                "span_id": "abc123",
            },
        )
    )
    resp = client.post(
        "/chat",
        json={"message": "show me keyboards", "session_id": "sess-1"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["model"] == "claude-sonnet-4-6"
    assert data["provider"] == "anthropic"
    assert data["actions"][0]["target"] == "category"
    assert data["actions"][0]["value"] == "peripherals"
    assert data["products"][0]["sku"] == "KB-001"
    assert data["products"][0]["price_usd"] == 99.99
    assert data["session_id"] == "sess-1"
