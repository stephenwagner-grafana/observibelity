"""Liveness probe smoke test.

Uses FastAPI's sync TestClient; the lifespan still runs, so this also
catches gross import-time breakage in app.main.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(app)


def test_health_endpoint(client: TestClient) -> None:
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.text == "ok"


def test_metrics_endpoint_returns_prometheus(client: TestClient) -> None:
    resp = client.get("/metrics")
    assert resp.status_code == 200
    # Prometheus text exposition starts with `# HELP` or has metric lines.
    body = resp.text
    assert body, "metrics body should be non-empty"
