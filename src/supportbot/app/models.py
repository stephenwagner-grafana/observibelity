"""SQLAlchemy models for the Support Bot read-side.

Only tables the bot actually reads are declared here. The write-side (ticket
inserts/updates, expense rows, etc.) is performed by the tool microservices,
which own their own DDL via the alembic migrations.

`personas` is shared with NeonCart — both apps read the same row set; only
the supportbot-specific tables (tickets, supportbot_kb) are unique to SB.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Shared declarative base for SB."""


class Persona(Base):
    """Synthetic employee for session attribution.

    Shared schema with NeonCart's persona table (migrations/versions/0001).
    Columns mirror the migration exactly — older drafts of this model had a
    ``department`` column that does not exist in the DB, which 500'd the
    ``/api/personas`` endpoint on every call.
    """

    __tablename__ = "personas"

    id: Mapped[int] = mapped_column(primary_key=True)
    persona_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    email: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    role: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    archetype: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    offender_pattern: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    weight: Mapped[float] = mapped_column(default=1.0, nullable=False)


class Ticket(Base):
    """Internal support ticket — filed by an employee, resolved by IT/HR/etc.

    Schema mirrors migrations/versions/0006_tickets.py exactly: persona_id is
    a STRING FK to ``personas.persona_id`` (the slug like ``tim.lewis@acme.com``), and
    the side-channel field is ``priority`` (open/medium/high), not
    ``category``. Older drafts of this model had ``category``/``updated_at``
    columns the DB doesn't expose — every SELECT or INSERT against the real
    table would 500 with UndefinedColumn.
    """

    __tablename__ = "tickets"

    id: Mapped[int] = mapped_column(primary_key=True)
    ticket_number: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    persona_id: Mapped[Optional[str]] = mapped_column(
        String(64), ForeignKey("personas.persona_id"), nullable=True, index=True
    )
    subject: Mapped[str] = mapped_column(String(255), nullable=False)
    body: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="open")
    priority: Mapped[str] = mapped_column(String(16), nullable=False, default="medium")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    persona: Mapped[Optional[Persona]] = relationship(lazy="joined")


class SupportbotKb(Base):
    """Knowledge-base article surfaced by sb-kb-search / kb_search tool.

    Schema mirrors migrations/versions/0007_supportbot_kb.py. Older drafts
    of this model declared ``category`` + ``is_confidential`` columns the
    DB doesn't have — those flags are now derived from ``tags`` (e.g. a
    "confidential" tag) rather than stored as separate columns.
    """

    __tablename__ = "supportbot_kb"

    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    tags: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)

    @property
    def is_confidential(self) -> bool:
        """Derived: any KB row with a 'confidential' tag is treated as restricted."""
        return bool(self.tags and "confidential" in (self.tags or "").lower())

    @property
    def category(self) -> Optional[str]:
        """Derived: pick the first tag as a coarse-grained category."""
        if not self.tags:
            return None
        parts = [p.strip() for p in self.tags.split(";") if p.strip()]
        return parts[0] if parts else None
