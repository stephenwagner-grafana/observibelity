"""Mocked-gateway tests for the nc-fraud-detector specialist."""
from __future__ import annotations

import json
from unittest.mock import AsyncMock

import pytest

from app.specialist import NcFraudDetector, _parse_score
from specialist_base import SpecialistRequest


def test_metadata() -> None:
    spec = NcFraudDetector()
    assert spec.NAME == "nc-fraud-detector"
    assert set(spec.TOOL_ALLOWLIST) == {"get_order_history", "geo_lookup"}


def test_parse_score_json() -> None:
    score, reasoning = _parse_score(
        '{"fraud_score": 0.83, "reasoning": "Mismatched geos."}'
    )
    assert score == pytest.approx(0.83)
    assert "geos" in reasoning


def test_parse_score_fallback() -> None:
    score, _ = _parse_score("fraud_score: 0.42 lots of prose around it")
    assert score == pytest.approx(0.42)


def test_parse_score_clamped() -> None:
    score, _ = _parse_score('{"fraud_score": 9.9, "reasoning": "x"}')
    assert score == 1.0


@pytest.mark.asyncio
async def test_handle_scores_order() -> None:
    spec = NcFraudDetector()
    spec.call_gateway = AsyncMock(  # type: ignore[method-assign]
        return_value={
            "content": '{"fraud_score": 0.72, "reasoning": "High-value first order."}',
            "tool_calls": [],
            "usage": {"cost": {"total_usd": 0.0021}},
        }
    )
    req = SpecialistRequest(
        message="please score",
        context={"order": {"order_id": "ord-1", "amount_usd": 4500}},
    )
    resp = await spec.handle(req)
    payload = json.loads(resp.reply)
    assert payload["fraud_score"] == pytest.approx(0.72)
    assert "first order" in payload["reasoning"]
    assert resp.cost_usd == pytest.approx(0.0021)
