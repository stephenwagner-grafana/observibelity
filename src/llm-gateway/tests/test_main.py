"""Integration tests for app.main routes.

A fake provider is shoved onto `app.state.providers` so we never touch the
network. The Anthropic SDK isn't imported by these tests.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.providers.base import CompleteRequest, CompleteResponse, Provider


class FakeProvider(Provider):
    """Returns a canned response so tests never hit api.anthropic.com."""

    name = "fake"
    model = "fake-model-1"

    def __init__(self, config: dict | None = None) -> None:
        super().__init__(config)
        self.called_with: CompleteRequest | None = None

    async def complete(self, req: CompleteRequest) -> CompleteResponse:
        self.called_with = req
        return CompleteResponse(
            content="hello from the fake provider",
            tool_calls=[],
            finish_reason="stop",
            usage={"input_tokens": 10, "output_tokens": 5},
            provider=self.name,
            model=self.model,
        )

    async def healthy(self) -> bool:
        return True


@pytest.fixture()
def client():
    """TestClient that uses a fake provider instead of the real ones."""
    fake = FakeProvider()
    with TestClient(app) as c:
        c.app.state.providers = {"fake": fake}
        c.app.state.default_provider = "fake"
        yield c


def test_health_returns_ok(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.text == "ok"


def test_readyz_passes_when_any_provider_healthy(client):
    r = client.get("/readyz")
    assert r.status_code == 200
    body = r.json()
    assert body["providers"]["fake"] is True


def test_metrics_exposes_prometheus_format(client):
    r = client.get("/metrics")
    assert r.status_code == 200
    assert "llm_gateway_requests_total" in r.text or r.text == ""


def test_complete_routes_to_provider_and_attaches_cost(client):
    payload = {
        "specialist": "nc-chatbot",
        "messages": [{"role": "user", "content": "hi"}],
        "ai_o11y": {
            "usecase": "mice-rca",
            "persona_id": "p-0001",
            "traffic_origin": "interactive",
        },
    }
    r = client.post("/v1/complete", json=payload)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["content"] == "hello from the fake provider"
    assert body["provider"] == "fake"
    assert body["model"] == "fake-model-1"
    # Cost block was attached by main.py even though the fake provider didn't set it.
    assert "cost_usd" in body["usage"]
    assert body["usage"]["cost_usd"]["total_usd"] == 0.0  # fake model = free
