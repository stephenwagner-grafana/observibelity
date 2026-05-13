"""orders: orders, order_items, shipping_rates

Revision ID: 0003
Revises: 0002
Create Date: 2026-05-13
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "orders",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "persona_id",
            sa.String(64),
            sa.ForeignKey("personas.persona_id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("order_number", sa.String(64), unique=True, nullable=False),
        sa.Column("total_usd", sa.Numeric(12, 2), nullable=False),
        sa.Column("status", sa.String(32), server_default="pending", nullable=False),
        sa.Column("fraud_score", sa.Numeric(5, 4), nullable=True),
        sa.Column("shipping_zip", sa.String(16)),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_orders_persona_id", "orders", ["persona_id"])
    op.create_index("ix_orders_order_number", "orders", ["order_number"])
    op.create_index("ix_orders_status", "orders", ["status"])

    op.create_table(
        "order_items",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "order_id",
            sa.Integer,
            sa.ForeignKey("orders.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "catalog_item_id",
            sa.Integer,
            sa.ForeignKey("catalog_items.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("qty", sa.Integer, nullable=False),
        sa.Column("price_each", sa.Numeric(10, 2), nullable=False),
    )
    op.create_index("ix_order_items_order_id", "order_items", ["order_id"])
    op.create_index("ix_order_items_catalog_item_id", "order_items", ["catalog_item_id"])

    op.create_table(
        "shipping_rates",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("country", sa.String(2), nullable=False),
        sa.Column("base_usd", sa.Numeric(8, 2), nullable=False),
        sa.Column("per_kg_usd", sa.Numeric(8, 2), nullable=False),
    )
    op.create_index("ix_shipping_rates_country", "shipping_rates", ["country"])


def downgrade() -> None:
    op.drop_index("ix_shipping_rates_country", table_name="shipping_rates")
    op.drop_table("shipping_rates")
    op.drop_index("ix_order_items_catalog_item_id", table_name="order_items")
    op.drop_index("ix_order_items_order_id", table_name="order_items")
    op.drop_table("order_items")
    op.drop_index("ix_orders_status", table_name="orders")
    op.drop_index("ix_orders_order_number", table_name="orders")
    op.drop_index("ix_orders_persona_id", table_name="orders")
    op.drop_table("orders")
