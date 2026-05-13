# migrations/ — Alembic schema migrations

Postgres schema is managed by [Alembic](https://alembic.sqlalchemy.org/). Each migration is a Python file under `versions/`. The chart runs `alembic upgrade head` as a post-install Helm hook.

## Layout

```
migrations/
├── alembic.ini           Alembic config
├── env.py                Alembic env (reads DATABASE_URL from env)
├── versions/             individual migration files
└── README.md             this file
```

## Phase 1 migrations (17 tables)

- 0001_initial: apps, personas, sessions, conversations
- 0002_catalog: catalog_items, categories, brands, promotions
- 0003_orders: orders, order_items, shipping_rates
- 0004_geo: store_locations, countries, currencies, ip_geo
- 0005_kb: neoncart_kb, payment_methods

## Phase 2 adds 11 more tables (Support Bot KBs, ticket history, etc. — total 28)

## Workflow

```bash
# Create a new migration
make migration NAME=add_review_table

# Apply migrations (runs automatically on `make dev`)
make migrate

# Roll back one
make migrate-down

# Show current revision
make migrate-status
```

## Conventions

- File names: `NNNN_short_description.py` (4-digit zero-pad)
- Schema changes only — NO data inserts in Alembic migrations
- Seed data goes via `seed_data/` and a separate Job (see `seed_data/README.md`)

## Idempotency

Migrations must be idempotent (use `IF NOT EXISTS`, `op.execute(...)` with checks). `make dev` may run them on every deploy.

## See also
- [Live planner § 09 Postgres schema](https://claude.wombatwags.com/planner/ai-o11y/#postgres)
