"""supportbot_kb: missing table created by 0005 only as neoncart_kb

Revision ID: 0007
Revises: 0006
Create Date: 2026-05-13

0005 created ``neoncart_kb`` only; the SB app + kb_search tool both target
``supportbot_kb`` (and the seed CSV is ``kb/supportbot_kb.csv``). Without
this migration the seed-loader Job fails on the supportbot_kb INSERT and
``/api/kb`` / ``sb-kb-search`` 500 on every request.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "supportbot_kb",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("slug", sa.String(128), unique=True, nullable=False),
        sa.Column("title", sa.String(256), nullable=False),
        sa.Column("body", sa.Text, nullable=False),
        sa.Column("tags", sa.String(512)),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_supportbot_kb_slug", "supportbot_kb", ["slug"])


def downgrade() -> None:
    op.drop_index("ix_supportbot_kb_slug", table_name="supportbot_kb")
    op.drop_table("supportbot_kb")
