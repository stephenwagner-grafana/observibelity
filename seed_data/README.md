# seed_data/ — CSV seed data for Postgres

Once Alembic migrations create the schema, a separate "seed" Helm hook Job loads CSVs into the appropriate tables.

## Layout

```
seed_data/
├── catalog/
│   ├── catalog_items.csv     ~200 products
│   ├── categories.csv        ~12 categories
│   ├── brands.csv            ~30 brands
│   └── promotions.csv
├── personas/
│   ├── personas.csv          ~50 employees
│   └── persona_traits.csv    behavior tags per persona
├── geo/
│   ├── countries.csv
│   ├── currencies.csv
│   ├── ip_geo.csv            small sample for the demo
│   └── store_locations.csv
└── kb/
    └── neoncart_kb.csv       FAQ + help articles
```

## Loader

`tools/seed-loader.py` reads each CSV and INSERT…ON CONFLICT DO UPDATE into the matching table (idempotent UPSERT on natural keys). Runs as a Helm post-install hook after migrations finish.

## Adding a new dataset

1. Generate or hand-craft the CSV under the right subdirectory
2. Add a corresponding SQLAlchemy model under `src/<app>/db/models/`
3. Add an Alembic migration creating the table
4. The seed-loader auto-discovers CSVs by filename matching table names

## Persona generation

`tools/gen-personas.sh` generates a fresh `personas.csv` with N personas, M offenders. Use this to vary the demo (e.g., 200-employee deployment instead of 50).

## See also
- [Live planner § 09 Postgres schema](https://claude.wombatwags.com/planner/ai-o11y/#postgres)
- [Live planner § 12 Personas](https://claude.wombatwags.com/planner/ai-o11y/#personas)
