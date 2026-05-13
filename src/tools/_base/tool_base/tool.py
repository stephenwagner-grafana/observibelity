"""Base class for ObserVIBElity tool microservices.

Each tool subclasses :class:`Tool`, sets the 13 customization knobs (class
attributes), declares ``Args`` + ``Result`` Pydantic models, and implements
:meth:`execute`. The base class wraps execution with OpenTelemetry spans,
authorization, a TTL cache, a concurrency semaphore, a timeout, and
configurable retries.
"""
from __future__ import annotations

import asyncio
import os
from abc import ABC, abstractmethod
from typing import ClassVar

from cachetools import TTLCache
from opentelemetry import trace
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

tracer = trace.get_tracer(__name__)


class Tool(ABC):
    """Base class for a single tool microservice.

    Subclasses set the class-level knobs below and implement
    :meth:`execute`. The orchestrating :meth:`invoke` entry point handles
    cross-cutting concerns (tracing, auth, cache, concurrency, timeout,
    retries) so subclasses only contain business logic.
    """

    # ── 13 customization knobs ───────────────────────────────────────────
    NAME: ClassVar[str] = "unknown-tool"
    SIDE_EFFECT: ClassVar[bool] = False         # mutates state?
    IDEMPOTENT: ClassVar[bool] = True           # safe to retry?
    TIMEOUT_SEC: ClassVar[int] = 5
    MAX_CONCURRENCY: ClassVar[int] = 50
    CACHE_TTL_SEC: ClassVar[int] = 0            # 0 = no cache
    RETRIES: ClassVar[int] = 0
    ALLOWED_CALLERS: ClassVar[list[str]] = []   # empty = anyone
    REQUIRES_ACL: ClassVar[bool] = False
    BACKING_TABLES: ClassVar[list[str]] = []
    REQUIRES_SECRETS: ClassVar[list[str]] = []
    REPLICAS: ClassVar[int] = 1

    # The two Pydantic schemas.
    Args: ClassVar[type[BaseModel]] = BaseModel
    Result: ClassVar[type[BaseModel]] = BaseModel

    # ── lifecycle ────────────────────────────────────────────────────────
    def __init__(self) -> None:
        self._sema = asyncio.Semaphore(self.MAX_CONCURRENCY)
        self._cache: TTLCache | None = (
            TTLCache(maxsize=10_000, ttl=self.CACHE_TTL_SEC)
            if self.CACHE_TTL_SEC > 0
            else None
        )
        self._db_engine = None
        self._sessionmaker: async_sessionmaker[AsyncSession] | None = None
        if self.BACKING_TABLES:
            url = os.environ.get(
                "DATABASE_URL",
                "postgresql+asyncpg://postgres:pass@postgres/observibelity",
            )
            self._db_engine = create_async_engine(url, pool_pre_ping=True)
            self._sessionmaker = async_sessionmaker(
                self._db_engine, expire_on_commit=False
            )

    # ── overridable hooks ────────────────────────────────────────────────
    def cache_key(self, args: BaseModel) -> str:
        """Return a cache key for ``args``. Override for partial-key schemes."""
        return args.model_dump_json()

    def authorize(self, caller: str | None) -> bool:
        """Return True if ``caller`` is allowed to invoke this tool."""
        if not self.ALLOWED_CALLERS:
            return True
        return caller in self.ALLOWED_CALLERS

    @abstractmethod
    async def execute(
        self,
        args: BaseModel,
        session: AsyncSession | None = None,
    ) -> BaseModel:
        """Subclass entrypoint. Performs the actual work."""

    # ── orchestration ────────────────────────────────────────────────────
    async def invoke(
        self,
        args: BaseModel,
        caller: str | None = None,
    ) -> BaseModel:
        """Public entrypoint — wraps :meth:`execute` with cross-cutting concerns."""
        with tracer.start_as_current_span(f"tool.{self.NAME}") as span:
            span.set_attribute("ai_o11y.tool", self.NAME)
            span.set_attribute("ai_o11y.tool.side_effect", self.SIDE_EFFECT)
            span.set_attribute("ai_o11y.tool.idempotent", self.IDEMPOTENT)
            if caller is not None:
                span.set_attribute("ai_o11y.tool.caller", caller)

            if not self.authorize(caller):
                span.set_attribute("error", True)
                span.set_attribute("ai_o11y.tool.error", "permission_denied")
                raise PermissionError(
                    f"{caller!r} not authorized for {self.NAME}"
                )

            # Cache check (only for non-side-effect tools)
            if self._cache is not None and not self.SIDE_EFFECT:
                key = self.cache_key(args)
                if key in self._cache:
                    span.set_attribute("ai_o11y.tool.cache_hit", True)
                    return self._cache[key]
                span.set_attribute("ai_o11y.tool.cache_hit", False)

            # Don't retry side-effect, non-idempotent tools.
            max_attempts = 1 if (self.SIDE_EFFECT and not self.IDEMPOTENT) else self.RETRIES + 1

            # Concurrency limit + timeout + retries
            last_exc: BaseException | None = None
            async with self._sema:
                for attempt in range(max_attempts):
                    try:
                        async with asyncio.timeout(self.TIMEOUT_SEC):
                            if self._sessionmaker is not None:
                                async with self._sessionmaker() as session:
                                    result = await self.execute(args, session)
                            else:
                                result = await self.execute(args, None)
                        if self._cache is not None and not self.SIDE_EFFECT:
                            self._cache[self.cache_key(args)] = result
                        span.set_attribute("ai_o11y.tool.attempts", attempt + 1)
                        return result
                    except Exception as exc:  # noqa: BLE001 — re-raised below
                        last_exc = exc
                        if attempt + 1 >= max_attempts:
                            span.record_exception(exc)
                            span.set_attribute("error", True)
                            span.set_attribute("ai_o11y.tool.attempts", attempt + 1)
                            raise
            # Defensive — unreachable, but satisfies type checkers.
            assert last_exc is not None
            raise last_exc
