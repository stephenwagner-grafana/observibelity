"""Tests for the shared Tool base class."""
from __future__ import annotations

import asyncio

import pytest
from pydantic import BaseModel

from tool_base import Tool


class _Args(BaseModel):
    n: int


class _Result(BaseModel):
    n: int
    doubled: int


class _Doubler(Tool):
    NAME = "doubler"
    SIDE_EFFECT = False
    IDEMPOTENT = True
    TIMEOUT_SEC = 1
    MAX_CONCURRENCY = 4
    CACHE_TTL_SEC = 60

    Args = _Args
    Result = _Result

    def __init__(self) -> None:
        super().__init__()
        self.calls = 0

    async def execute(self, args, session=None):
        self.calls += 1
        return _Result(n=args.n, doubled=args.n * 2)


class _Flaky(Tool):
    NAME = "flaky"
    SIDE_EFFECT = False
    IDEMPOTENT = True
    TIMEOUT_SEC = 1
    RETRIES = 2

    Args = _Args
    Result = _Result

    def __init__(self) -> None:
        super().__init__()
        self.calls = 0

    async def execute(self, args, session=None):
        self.calls += 1
        if self.calls < 3:
            raise RuntimeError("flaky")
        return _Result(n=args.n, doubled=args.n * 2)


class _Guarded(Tool):
    NAME = "guarded"
    ALLOWED_CALLERS = ["nc-chatbot"]

    Args = _Args
    Result = _Result

    async def execute(self, args, session=None):
        return _Result(n=args.n, doubled=args.n * 2)


@pytest.mark.asyncio
async def test_invoke_returns_result():
    t = _Doubler()
    res = await t.invoke(_Args(n=3))
    assert res.doubled == 6


@pytest.mark.asyncio
async def test_cache_hits_skip_execute():
    t = _Doubler()
    await t.invoke(_Args(n=3))
    await t.invoke(_Args(n=3))
    assert t.calls == 1


@pytest.mark.asyncio
async def test_retries_until_success():
    t = _Flaky()
    res = await t.invoke(_Args(n=2))
    assert res.doubled == 4
    assert t.calls == 3


@pytest.mark.asyncio
async def test_authorize_blocks_unknown_caller():
    t = _Guarded()
    with pytest.raises(PermissionError):
        await t.invoke(_Args(n=1), caller="nc-fraud-detector")


@pytest.mark.asyncio
async def test_authorize_allows_listed_caller():
    t = _Guarded()
    res = await t.invoke(_Args(n=1), caller="nc-chatbot")
    assert res.doubled == 2


@pytest.mark.asyncio
async def test_concurrency_semaphore_caps_inflight():
    class _Slow(Tool):
        NAME = "slow"
        TIMEOUT_SEC = 2
        MAX_CONCURRENCY = 2
        Args = _Args
        Result = _Result

        def __init__(self) -> None:
            super().__init__()
            self.inflight = 0
            self.peak = 0

        async def execute(self, args, session=None):
            self.inflight += 1
            self.peak = max(self.peak, self.inflight)
            await asyncio.sleep(0.05)
            self.inflight -= 1
            return _Result(n=args.n, doubled=args.n * 2)

    t = _Slow()
    await asyncio.gather(*[t.invoke(_Args(n=i)) for i in range(10)])
    assert t.peak <= 2
