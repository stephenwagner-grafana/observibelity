"""Mocked-gateway tests for the nc-fulfillment-orchestrator specialist."""
from __future__ import annotations

from unittest.mock import AsyncMock

import httpx
import pytest

from app.specialist import NcFulfillmentOrchestrator
from specialist_base import SpecialistRequest


def test_metadata() -> None:
    spec = NcFulfillmentOrchestrator()
    assert spec.NAME == "nc-fulfillment-orchestrator"
    assert set(spec.TOOL_ALLOWLIST) == {
        "get_inventory",
        "place_order",
        "geo_lookup",
    }


@pytest.mark.asyncio
async def test_happy_path_non_rodent() -> None:
    spec = NcFulfillmentOrchestrator()
    spec.call_gateway = AsyncMock(  # type: ignore[method-assign]
        return_value={
            "content": "Order placed.",
            "tool_calls": [],
            "usage": {"cost": {"total_usd": 0.003}},
        }
    )
    req = SpecialistRequest(
        message="please fulfill order for neon-lamp-7",
        context={"sku": "neon-lamp-7"},
    )
    resp = await spec.handle(req)
    assert resp.reply == "Order placed."
    assert resp.cost_usd == pytest.approx(0.003)


@pytest.mark.asyncio
async def test_rodent_request_handles_inventory_error() -> None:
    """The canonical mice-RCA path: rodent SKU -> get_inventory blows up
    on the missing rodent_qty column. The specialist must surface a
    structured error and NOT invent stock counts."""
    spec = NcFulfillmentOrchestrator()

    fake_request = httpx.Request("POST", "http://get-inventory/v1/invoke")
    fake_response = httpx.Response(
        500,
        request=fake_request,
        text='{"error":"column \\"rodent_qty\\" does not exist"}',
    )
    spec.call_tool = AsyncMock(  # type: ignore[method-assign]
        side_effect=httpx.HTTPStatusError(
            'column "rodent_qty" does not exist',
            request=fake_request,
            response=fake_response,
        )
    )
    spec.call_gateway = AsyncMock(  # type: ignore[method-assign]
        return_value={
            "content": "Inventory check failed: column rodent_qty does not exist.",
            "tool_calls": [],
            "usage": {"cost": {"total_usd": 0.001}},
        }
    )

    req = SpecialistRequest(
        message="how many mice do we have in stock?",
        context={"sku": "mice"},
    )
    resp = await spec.handle(req)

    # call_tool was attempted (the rodent probe)
    spec.call_tool.assert_awaited()
    # The reply must reflect the structured error, not invented inventory
    assert "rodent_qty" in resp.reply or "failed" in resp.reply.lower()
