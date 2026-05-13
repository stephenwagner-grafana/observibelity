"""Tests for the geo_lookup tool."""
from __future__ import annotations

import pytest

from app.tool import GeoLookup, GeoLookupArgs, GeoLookupResult


class _Row:
    def __init__(self, **kw):
        self.__dict__.update(kw)


class _StubResult:
    def __init__(self, row):
        self._row = row

    def one_or_none(self):
        return self._row


class _StubSession:
    def __init__(self, row):
        self._row = row
        self.last_params: dict | None = None

    async def execute(self, stmt, params):
        self.last_params = params
        return _StubResult(self._row)


def test_one_of_required():
    with pytest.raises(ValueError):
        GeoLookupArgs()
    with pytest.raises(ValueError):
        GeoLookupArgs(ip_address="1.2.3.4", zip_code="94110")


def test_knobs():
    assert GeoLookup.NAME == "geo_lookup"
    assert GeoLookup.CACHE_TTL_SEC == 3600
    assert "ip_geo" in GeoLookup.BACKING_TABLES


@pytest.mark.asyncio
async def test_execute_ip_hit():
    row = _Row(country_code="US", country="United States", state="CA", city="San Francisco")
    session = _StubSession(row)
    tool = GeoLookup.__new__(GeoLookup)
    res = await tool.execute(GeoLookupArgs(ip_address="1.2.3.4"), session)
    assert isinstance(res, GeoLookupResult)
    assert res.country == "United States"
    assert res.state == "CA"
    assert res.city == "San Francisco"
    assert session.last_params == {"ip": "1.2.3.4"}


@pytest.mark.asyncio
async def test_execute_zip_miss_returns_unknown():
    session = _StubSession(None)
    tool = GeoLookup.__new__(GeoLookup)
    res = await tool.execute(GeoLookupArgs(zip_code="00000"), session)
    assert res.country == "UNKNOWN"
    assert res.state is None
    assert res.city is None
