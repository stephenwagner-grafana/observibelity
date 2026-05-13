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

    Shared schema with NeonCart's persona table — Phase 2 alembic migration
    extends the existing table rather than creating a new one.
    """

    __tablename__ = "personas"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    role: Mapped[str] = mapped_column(String(64), nullable=False, default="employee")
    department: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)


class Ticket(Base):
    """Internal support ticket — filed by an employee, resolved by IT/HR/etc."""

    __tablename__ = "tickets"

    id: Mapped[int] = mapped_column(primary_key=True)
    persona_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("personas.id"), nullable=True, index=True
    )
    subject: Mapped[str] = mapped_column(String(255), nullable=False)
    body: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="open")
    category: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    persona: Mapped[Optional[Persona]] = relationship(lazy="joined")


class SupportbotKb(Base):
    """Knowledge-base article surfaced by sb-kb-search / kb_search tool."""

    __tablename__ = "supportbot_kb"

    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    tags: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    is_confidential: Mapped[bool] = mapped_column(default=False, nullable=False)
