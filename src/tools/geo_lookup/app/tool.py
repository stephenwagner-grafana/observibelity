"""geo_lookup — resolve an IP or ZIP to country / state / city."""
from __future__ import annotations

from typing import Self

from pydantic import BaseModel, Field, model_validator
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from tool_base import Tool


class GeoLookupArgs(BaseModel):
    """Inputs for ``geo_lookup``. Exactly one of ``ip_address`` or ``zip_code`` must be set."""

    ip_address: str | None = None
    zip_code: str | None = Field(None, min_length=3, max_length=10)

    @model_validator(mode="after")
    def _one_of(self) -> Self:
        if (self.ip_address is None) == (self.zip_code is None):
            raise ValueError("exactly one of ip_address or zip_code must be provided")
        return self


class GeoLookupResult(BaseModel):
    """Resolved geo coordinates."""

    country: str
    state: str | None
    city: str | None


class GeoLookup(Tool):
    NAME = "geo_lookup"
    SIDE_EFFECT = False
    IDEMPOTENT = True
    TIMEOUT_SEC = 3
    MAX_CONCURRENCY = 100
    CACHE_TTL_SEC = 3600
    RETRIES = 2
    BACKING_TABLES = ["ip_geo", "countries"]
    REPLICAS = 1

    Args = GeoLookupArgs
    Result = GeoLookupResult

    async def execute(
        self,
        args: GeoLookupArgs,
        session: AsyncSession | None = None,
    ) -> GeoLookupResult:
        assert session is not None, "geo_lookup requires a DB session"
        if args.ip_address is not None:
            stmt = text(
                """
                SELECT g.country_code, g.state, g.city, c.name AS country
                  FROM ip_geo g
                  LEFT JOIN countries c ON c.code = g.country_code
                 WHERE g.ip_address = :ip
                 LIMIT 1
                """
            )
            params: dict[str, object] = {"ip": args.ip_address}
        else:
            stmt = text(
                """
                SELECT g.country_code, g.state, g.city, c.name AS country
                  FROM ip_geo g
                  LEFT JOIN countries c ON c.code = g.country_code
                 WHERE g.zip_code = :zip
                 LIMIT 1
                """
            )
            params = {"zip": args.zip_code}
        row = (await session.execute(stmt, params)).one_or_none()
        if row is None:
            return GeoLookupResult(country="UNKNOWN", state=None, city=None)
        return GeoLookupResult(
            country=row.country or row.country_code or "UNKNOWN",
            state=row.state,
            city=row.city,
        )
