#!/usr/bin/env python3
"""seed-loader: idempotently load CSVs into Postgres.

Run as a Helm post-install Job after `alembic upgrade head` succeeds.
Expects:
  - DATABASE_URL  e.g. postgresql+psycopg2://user:pass@host:5432/dbname
  - SEED_DIR      defaults to /seed_data (mounted via ConfigMap or PV)

Each CSV's basename (sans .csv) must match a Postgres table name.
The natural key per table is in TABLE_KEY_MAP; the loader does
INSERT … ON CONFLICT (<key>) DO UPDATE SET <other cols> = EXCLUDED.<col>
so this script is safe to re-run.

Empty CSV cells are treated as NULL (so nullable columns like
personas.offender_pattern get a real SQL NULL rather than '').
"""

from __future__ import annotations

import csv
import os
import sys
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

SEED_DIR = Path(os.environ.get("SEED_DIR", "/seed_data"))
DATABASE_URL = os.environ.get("DATABASE_URL", "")

# table name -> natural-key column for UPSERT
TABLE_KEY_MAP: dict[str, str] = {
    "categories": "id",
    "brands": "id",
    "catalog_items": "sku",
    "promotions": "code",
    "personas": "persona_id",
    "currencies": "code",
    "countries": "code",
    "ip_geo": "id",
    "store_locations": "id",
    "neoncart_kb": "slug",
}

# Load order matters because of FKs. Parents first, then children.
LOAD_ORDER: list[str] = [
    "currencies",
    "countries",
    "ip_geo",
    "store_locations",
    "categories",
    "brands",
    "catalog_items",
    "promotions",
    "personas",
    "neoncart_kb",
]


def _normalise_row(row: dict[str, str]) -> dict[str, object]:
    """Treat empty strings as SQL NULL so nullable columns behave correctly."""
    out: dict[str, object] = {}
    for k, v in row.items():
        if v is None or v == "":
            out[k] = None
        else:
            out[k] = v
    return out


def upsert_csv(engine: Engine, table: str, csv_path: Path, key: str) -> int:
    """UPSERT all rows from csv_path into table using key as the conflict target."""
    with csv_path.open(newline="") as f:
        reader = csv.DictReader(f)
        rows = [_normalise_row(r) for r in reader]
    if not rows:
        return 0

    columns = list(rows[0].keys())
    cols_sql = ", ".join(columns)
    placeholders = ", ".join(f":{c}" for c in columns)
    other_cols = [c for c in columns if c != key]
    if other_cols:
        updates = ", ".join(f"{c} = EXCLUDED.{c}" for c in other_cols)
        on_conflict = f"ON CONFLICT ({key}) DO UPDATE SET {updates}"
    else:
        # Only the key column; nothing to update on conflict.
        on_conflict = f"ON CONFLICT ({key}) DO NOTHING"

    stmt = text(
        f"INSERT INTO {table} ({cols_sql}) VALUES ({placeholders}) {on_conflict}"
    )

    with engine.begin() as conn:
        conn.execute(stmt, rows)
    return len(rows)


def find_csv(table: str) -> Path | None:
    """Find <table>.csv anywhere under SEED_DIR. Returns the first match or None."""
    matches = list(SEED_DIR.rglob(f"{table}.csv"))
    return matches[0] if matches else None


def main() -> int:
    if not DATABASE_URL:
        print("ERROR: DATABASE_URL is not set.", file=sys.stderr)
        return 2
    if not SEED_DIR.is_dir():
        print(f"ERROR: SEED_DIR {SEED_DIR} is not a directory.", file=sys.stderr)
        return 2

    engine = create_engine(DATABASE_URL)
    total = 0
    for table in LOAD_ORDER:
        key = TABLE_KEY_MAP[table]
        csv_path = find_csv(table)
        if csv_path is None:
            print(f"skip {table} (no CSV found under {SEED_DIR})")
            continue
        n = upsert_csv(engine, table, csv_path, key)
        total += n
        print(f"loaded {table}: {n} rows  ({csv_path.relative_to(SEED_DIR)})")
    print(f"DONE: {total} rows loaded across {len(LOAD_ORDER)} tables")
    return 0


if __name__ == "__main__":
    sys.exit(main())
