"""initial: apps, personas, sessions, conversations

Revision ID: 0001
Revises:
Create Date: 2026-05-13
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "apps",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.String(64), unique=True, nullable=False),
        sa.Column("display_name", sa.String(128)),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "personas",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("persona_id", sa.String(64), unique=True, nullable=False),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("email", sa.String(256)),
        sa.Column("role", sa.String(64)),
        sa.Column("archetype", sa.String(64)),
        sa.Column("offender_pattern", sa.String(64), nullable=True),
        sa.Column("weight", sa.Float, server_default="1.0", nullable=False),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_personas_persona_id", "personas", ["persona_id"])
    op.create_index("ix_personas_archetype", "personas", ["archetype"])

    op.create_table(
        "sessions",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "persona_id",
            sa.String(64),
            sa.ForeignKey("personas.persona_id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("app", sa.String(64)),
        sa.Column("started_at", sa.DateTime, server_default=sa.func.now(), nullable=False),
        sa.Column("ended_at", sa.DateTime, nullable=True),
    )
    op.create_index("ix_sessions_persona_id", "sessions", ["persona_id"])
    op.create_index("ix_sessions_app", "sessions", ["app"])

    op.create_table(
        "conversations",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "session_id",
            sa.Integer,
            sa.ForeignKey("sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("content", sa.Text),
        sa.Column("tool_calls", sa.JSON),
        sa.Column("cost_usd", sa.Numeric(10, 6)),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_conversations_session_id", "conversations", ["session_id"])


def downgrade() -> None:
    op.drop_index("ix_conversations_session_id", table_name="conversations")
    op.drop_table("conversations")
    op.drop_index("ix_sessions_app", table_name="sessions")
    op.drop_index("ix_sessions_persona_id", table_name="sessions")
    op.drop_table("sessions")
    op.drop_index("ix_personas_archetype", table_name="personas")
    op.drop_index("ix_personas_persona_id", table_name="personas")
    op.drop_table("personas")
    op.drop_table("apps")
