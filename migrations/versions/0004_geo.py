"""geo: store_locations, countries, currencies, ip_geo

Revision ID: 0004
Revises: 0003
Create Date: 2026-05-13
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "currencies",
        sa.Column("code", sa.String(3), primary_key=True),
        sa.Column("symbol", sa.String(8)),
        sa.Column("name", sa.String(128)),
    )

    op.create_table(
        "countries",
        sa.Column("code", sa.String(2), primary_key=True),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column(
            "currency_code",
            sa.String(3),
            sa.ForeignKey("currencies.code", ondelete="SET NULL"),
            nullable=True,
        ),
    )

    op.create_table(
        "ip_geo",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("ip_range_start", sa.String(64), nullable=False),
        sa.Column("ip_range_end", sa.String(64), nullable=False),
        sa.Column(
            "country_code",
            sa.String(2),
            sa.ForeignKey("countries.code", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("state", sa.String(128)),
        sa.Column("city", sa.String(128)),
    )
    op.create_index("ix_ip_geo_country_code", "ip_geo", ["country_code"])

    op.create_table(
        "store_locations",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("country", sa.String(2)),
        sa.Column("state", sa.String(128)),
        sa.Column("city", sa.String(128)),
        sa.Column("zip", sa.String(16)),
    )


def downgrade() -> None:
    op.drop_table("store_locations")
    op.drop_index("ix_ip_geo_country_code", table_name="ip_geo")
    op.drop_table("ip_geo")
    op.drop_table("countries")
    op.drop_table("currencies")
