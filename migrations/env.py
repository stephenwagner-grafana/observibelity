"""Alembic environment for ObserVIBElity.

Reads DATABASE_URL from the environment so the same migrations work in:
  * local dev (DATABASE_URL=postgresql+psycopg2://...)
  * Helm post-install Job (DATABASE_URL pulled from Secret)
  * CI

Migrations are schema-only; seed data is loaded by tools/seed-loader.py
in a separate Helm Job after `alembic upgrade head` completes.
"""

from __future__ import annotations

import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

# Alembic Config object; provides access to values within the .ini file.
config = context.config

# Honour the logging config in alembic.ini if present.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Pull the database URL from the environment (overrides whatever is in the .ini).
_db_url = os.environ.get("DATABASE_URL", "")
if not _db_url:
    raise RuntimeError(
        "DATABASE_URL is not set. Alembic needs a connection string, e.g. "
        "postgresql+psycopg2://user:pass@host:5432/dbname"
    )
config.set_main_option("sqlalchemy.url", _db_url)

# We declare schema directly via op.* calls in each version file, so there's
# no global metadata to autogenerate from.
target_metadata = None


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode (no live DB connection)."""
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode (real DB connection)."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
