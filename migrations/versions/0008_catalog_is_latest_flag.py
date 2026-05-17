"""catalog_is_latest_flag: add is_latest_SKU_for_product to catalog_items

Revision ID: 0008
Revises: 0007
Create Date: 2026-05-16

Adds a boolean flag indicating whether a catalog row is the current/latest
SKU for its underlying product. Defaults to FALSE so legacy rows are
non-disruptive; the seed CSV explicitly flips the flag for current-gen rows.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "catalog_items",
        sa.Column(
            "is_latest_SKU_for_product",
            sa.Boolean,
            server_default=sa.false(),
            nullable=True,
        ),
    )
    # Long SKU formats (e.g. the cross-gen-retrieval-drift demo's
    # "0012.CORSAIR.0249.CMK64GX0x101100026.107.BS38_TT28_69HB_33BU.82200.DDR5.01.2026"
    # variants) exceed the original VARCHAR(64). Widen to 128 — plenty
    # for any catalog SKU shape we've planned for.
    op.alter_column(
        "catalog_items",
        "sku",
        existing_type=sa.String(64),
        type_=sa.String(128),
        existing_nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "catalog_items",
        "sku",
        existing_type=sa.String(128),
        type_=sa.String(64),
        existing_nullable=False,
    )
    op.drop_column("catalog_items", "is_latest_SKU_for_product")
