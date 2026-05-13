"""catalog: categories, brands, catalog_items, promotions

Revision ID: 0002
Revises: 0001
Create Date: 2026-05-13
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "categories",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("slug", sa.String(128), unique=True, nullable=False),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "brands",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("logo_url", sa.String(512)),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "catalog_items",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("sku", sa.String(64), unique=True, nullable=False),
        sa.Column("name", sa.String(256), nullable=False),
        sa.Column("description", sa.Text),
        sa.Column("price_usd", sa.Numeric(10, 2), nullable=False),
        sa.Column(
            "category_id",
            sa.Integer,
            sa.ForeignKey("categories.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "brand_id",
            sa.Integer,
            sa.ForeignKey("brands.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("image_url", sa.String(512)),
        sa.Column("stock_qty", sa.Integer, server_default="0", nullable=False),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_catalog_items_sku", "catalog_items", ["sku"])
    op.create_index("ix_catalog_items_category_id", "catalog_items", ["category_id"])
    op.create_index("ix_catalog_items_brand_id", "catalog_items", ["brand_id"])

    op.create_table(
        "promotions",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("code", sa.String(64), unique=True, nullable=False),
        sa.Column("percent_off", sa.Numeric(5, 2), nullable=False),
        sa.Column("valid_from", sa.DateTime, nullable=True),
        sa.Column("valid_to", sa.DateTime, nullable=True),
        sa.Column("active", sa.Boolean, server_default=sa.true(), nullable=False),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_promotions_code", "promotions", ["code"])


def downgrade() -> None:
    op.drop_index("ix_promotions_code", table_name="promotions")
    op.drop_table("promotions")
    op.drop_index("ix_catalog_items_brand_id", table_name="catalog_items")
    op.drop_index("ix_catalog_items_category_id", table_name="catalog_items")
    op.drop_index("ix_catalog_items_sku", table_name="catalog_items")
    op.drop_table("catalog_items")
    op.drop_table("brands")
    op.drop_table("categories")
