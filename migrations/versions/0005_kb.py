"""kb: neoncart_kb, payment_methods

Revision ID: 0005
Revises: 0004
Create Date: 2026-05-13
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "neoncart_kb",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("slug", sa.String(128), unique=True, nullable=False),
        sa.Column("title", sa.String(256), nullable=False),
        sa.Column("body", sa.Text, nullable=False),
        sa.Column("tags", sa.String(512)),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_neoncart_kb_slug", "neoncart_kb", ["slug"])

    op.create_table(
        "payment_methods",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.String(64), unique=True, nullable=False),
        sa.Column("supported_currencies", sa.JSON, nullable=False),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("payment_methods")
    op.drop_index("ix_neoncart_kb_slug", table_name="neoncart_kb")
    op.drop_table("neoncart_kb")
