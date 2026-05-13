"""tickets: support tickets for Support Bot demos

Revision ID: 0006
Revises: 0005
Create Date: 2026-05-13
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tickets",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("ticket_number", sa.String(64), unique=True, nullable=False),
        sa.Column(
            "persona_id",
            sa.String(64),
            sa.ForeignKey("personas.persona_id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("subject", sa.String(256), nullable=False),
        sa.Column("body", sa.Text),
        sa.Column("status", sa.String(32), server_default="open", nullable=False),
        sa.Column("priority", sa.String(16), server_default="medium", nullable=False),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_tickets_ticket_number", "tickets", ["ticket_number"])
    op.create_index("ix_tickets_persona_id", "tickets", ["persona_id"])
    op.create_index("ix_tickets_status", "tickets", ["status"])


def downgrade() -> None:
    op.drop_index("ix_tickets_status", table_name="tickets")
    op.drop_index("ix_tickets_persona_id", table_name="tickets")
    op.drop_index("ix_tickets_ticket_number", table_name="tickets")
    op.drop_table("tickets")
