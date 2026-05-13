"""Tests for the kb_search tool."""
from __future__ import annotations

import pytest

from app.tool import KbHit, KbSearch, KbSearchArgs, KbSearchResult


class _StubResult:
    def __init__(self, rows): self._rows = rows
    def all(self): return self._rows


class _StubRow:
    def __init__(self, **kw): self.__dict__.update(kw)


class _StubSession:
    def __init__(self, rows): self._rows = rows; self.last_params = None
    async def execute(self, stmt, params): self.last_params = params; return _StubResult(self._rows)


def test_args_validation():
    args = KbSearchArgs(query="vpn", limit=5)
    assert args.include_confidential is False
    assert args.limit == 5


def test_knobs():
    assert KbSearch.NAME == "kb_search"
    assert KbSearch.SIDE_EFFECT is False
    assert KbSearch.CACHE_TTL_SEC == 300
    assert KbSearch.BACKING_TABLES == ["supportbot_kb"]


@pytest.mark.asyncio
async def test_execute_returns_hits():
    # supportbot_kb schema (0007_supportbot_kb): no category column —
    # tags string is the canonical source; first tag is the category.
    rows = [
        _StubRow(
            id=1, slug="vpn", title="VPN reset",
            body="step 1...", tags="it;vpn;troubleshoot",
        )
    ]
    sess = _StubSession(rows)
    tool = KbSearch.__new__(KbSearch)
    res = await tool.execute(KbSearchArgs(query="vpn"), sess)
    assert isinstance(res, KbSearchResult)
    assert res.total == 1
    assert res.items[0] == KbHit(
        id=1, slug="vpn", title="VPN reset",
        snippet="step 1...", category="it",
    )
    assert sess.last_params["q"] == "%vpn%"
