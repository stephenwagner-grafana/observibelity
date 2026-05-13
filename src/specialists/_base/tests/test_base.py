"""Tests for the shared Specialist base class."""
from __future__ import annotations

import pytest

from specialist_base import Specialist, SpecialistRequest, SpecialistResponse


class _Dummy(Specialist):
    NAME = "dummy"
    TOOL_ALLOWLIST = ["search_products"]
    SYSTEM_PROMPT = "test"

    async def handle(self, req: SpecialistRequest) -> SpecialistResponse:
        return SpecialistResponse(reply="ok")


def test_request_defaults() -> None:
    req = SpecialistRequest(message="hi")
    assert req.context == {}
    assert req.persona_id is None
    assert req.usecase is None


def test_response_defaults() -> None:
    resp = SpecialistResponse(reply="hello")
    assert resp.tool_calls == []
    assert resp.cost_usd == 0.0


def test_tool_specs() -> None:
    spec = _Dummy()
    specs = spec._build_tool_specs()
    # OpenAI-shape function-tool spec; gateway translates to Anthropic
    # input_schema before calling the model.
    assert len(specs) == 1
    assert specs[0]["type"] == "function"
    assert specs[0]["function"]["name"] == "search_products"
    assert specs[0]["function"]["parameters"]["type"] == "object"


@pytest.mark.asyncio
async def test_call_tool_denied() -> None:
    spec = _Dummy()
    req = SpecialistRequest(message="x")
    with pytest.raises(PermissionError):
        await spec.call_tool("not_allowed_tool", {}, req)
