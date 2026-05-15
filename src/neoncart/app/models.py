"""SQLAlchemy models for the read-side of NeonCart.

Only the tables that the storefront actually reads are defined here. The
write-side schema (orders, inventory ledger, audit logs, etc.) lives in the
fulfillment-orchestrator + alembic migrations; NeonCart is intentionally a
thin read-mostly UI.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Optional

from sqlalchemy import ForeignKey, Numeric, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Shared declarative base."""


class Brand(Base):
    __tablename__ = "brands"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    logo_url: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)


class Category(Base):
    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    slug: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)


class CatalogItem(Base):
    __tablename__ = "catalog_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    sku: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    price_usd: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    category_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("categories.id"), nullable=True
    )
    brand_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("brands.id"), nullable=True
    )
    image_url: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    # NOTE: stock_qty is intentionally a denormalised mirror; authoritative
    # inventory lives in the inventory table queried by get_inventory tool.
    stock_qty: Mapped[int] = mapped_column(default=0, nullable=False)

    category: Mapped[Optional[Category]] = relationship(lazy="joined")
    brand: Mapped[Optional[Brand]] = relationship(lazy="joined")


class Persona(Base):
    """Synthetic shopper for chat session attribution.

    Loadgen picks one of these per session; the chosen persona id flows into
    span attributes as `ai_o11y.persona_id` for cardinality-bounded slicing.

    Schema mirrors migrations/versions/0001_initial.py — the canonical
    persona_id is the string slug (e.g. ``tim.lewis@acme.com``), and ``id`` is just the
    surrogate PK for FK joins.
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
