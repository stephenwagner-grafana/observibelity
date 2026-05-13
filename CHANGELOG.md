# Changelog

All notable changes to ObserVIBElity will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.2.0] - 2026-05-13

The Phase 1 release. NeonCart end-to-end with mice-rca centerpiece. All 22 planner use cases authored.

### Added
- **Phase 1 deployment**: real Helm templates for Postgres (StatefulSet), otel-collector, llm-gateway, neoncart, jobs (migrate + seed), specialists+tools loops over registry
- **NeonCart FastAPI app** (`src/neoncart/`) — full UI with Jinja templates, HTMX chat widget, Postgres-backed catalog, branding via ConfigMap
- **llm-gateway FastAPI** (`src/llm-gateway/`) — POST /v1/complete with AnthropicProvider wired; emits Sigil generation events with canonical gen_ai.* OTel attributes; cost tracking via pricing tables
- **Specialist base class** (`src/specialists/_base/`) — Pydantic SpecialistRequest/Response; call_gateway() + call_tool() helpers; OTel auto-instrumentation; tool allowlist enforcement
- **3 Phase 1 specialists**: `nc-chatbot` (search/order assistant), `nc-fraud-detector` (per-order risk scoring), `nc-fulfillment-orchestrator` (order fulfillment with mice-rca error trigger)
- **Tool base class** (`src/tools/_base/`) — 13 customization knobs (side_effect, idempotent, timeout_sec, max_concurrency, cache_ttl_sec, retries, allowed_callers, requires_acl, backing_tables, requires_secrets, replicas, plus cache_key() and authorize() overrides)
- **6 Phase 1 tools**: `search_products`, `get_product`, `get_order_history`, `geo_lookup`, `get_inventory` (with rodent_qty artificial error path), `place_order`
- **Alembic migrations** (`migrations/versions/`) — 5 migrations creating 17 tables for Phase 1 (apps, personas, sessions, conversations, catalog_items, categories, brands, promotions, orders, order_items, shipping_rates, store_locations, countries, currencies, ip_geo, neoncart_kb, payment_methods)
- **Seed data** (`seed_data/`) — ~200 catalog items, 50 personas (5 offenders: Tim, Mara, Jordan, Priya, Eric), 30 brands, 12 categories, geo reference, 20 KB articles
- **Seed loader** (`tools/seed-loader.py`) — idempotent CSV upsert; runs as Helm hook after migrations
- **All 22 use case YAMLs** (`registry/use_cases/`) — substantive Sigil expressions + PromQL alert conditions per the planner Group A + B (dropped coworker-termination per planner)
- **Phase 1 dashboard** (`dashboards/ai-obs-app-neoncart.json`) — mice-rca trace pivot, gen_ai usage, cost over time, Sigil events, ~15 panels
- **Makefile Phase 1 targets**: `migrate`, `migrate-down`, `migrate-status`, `seed`, `logs`, `pf-neoncart`, `pf-llm-gateway`, `pf-postgres`, `trigger-mice`, `usecases`, `usecases-status`, `phase`
- **Phase 1 integration tests** (`tests/integration/test_phase1.py`) — verifies pods Ready, mice-rca query path

### Changed
- `install.sh deploy` now does a real `helm upgrade --install --atomic --wait` (was a stub in 0.1.0)
- `values.yaml` adds `specialists` + `tools` registry lists for template loops

### Notes
- Phase 1 needs working images. Build with `make images` (Phase 1 wires up the Dockerfiles that landed in 0.1.0).
- Phase 2 will add: Support Bot, remaining 22 use cases at runtime (live evaluators in Grafana Sigil), 6 SLOs + ~14 alerts, k6 traffic engine, 11 more dashboards, all 6 .claude/skills.

## [0.1.0] - 2026-05-13

The Phase 0 scaffold release. No application pods are deployed yet — those land in Phase 1.

### Added

#### Chart + install
- Helm chart skeleton (`Chart.yaml`, `values.yaml`, `values-docker-desktop.yaml`)
- `install.sh` with 6 subcommands: `preflight | wizard | deploy | verify | doctor | reset`
- `deploy` subcommand runs `helm upgrade --install --atomic --wait` (idempotent — same command for first install and every redeploy)
- Preflight: OS detect, binary check + auto-install to `./tools/bin/`, cluster + admin perms check, live credential validation (Anthropic, Grafana Cloud, GitHub, Ollama)
- Wizard: 6-prompt interactive flow with `.env` writeback
- Cluster bootstrap: `./tools/bootstrap-cluster.sh` creates a local k3d cluster
- State file `.observibelity-state` (JSON) tracks pass/fail per step for resumable installs
- `--auto` / `--no-install` / `--no-fork` / `--no-atomic` / `--reset` / `--skip` flags
- `uninstall.sh` with `--destroy-cluster` / `--keep-pvc` / `--keep-namespace` / `--force`
- Shared bash libs (logging / prompt / colors / os / state)

#### Iteration tooling
- Top-level `Makefile` with `dev / verify / test / smoke / doctor / snapshot / watch / images / lint / help` targets
- `skaffold.yaml` stub for Phase 1+ app code hot-reload
- `templates/tests/test-connection.yaml` for `helm test`
- `.envrc.example` for direnv users
- 4-loop iteration design documented in `docs/DEVELOPMENT.md`

#### Provider abstraction
- `tools/deploy_doctor/` Python package with `Provider` base class + Anthropic + Ollama stubs
- Python entry points registered in `tools/pyproject.toml` for plugin discovery
- `tools/deploy-doctor.sh` bash wrapper auto-creates venv + runs collector

#### Testing
- bats tests for `install.sh` + state.sh + preflight
- helm-unittest tests for chart templates
- pytest for Python code
- golden snapshot of `helm template` output at `tests/snapshots/default.golden.yaml`
- Integration tests for upgrade/rollback/idempotency at `tests/integration/`
- End-to-end k3d smoke test at `tests/e2e/smoke-k3d.sh`

#### GHA workflows
- `lint`, `helm-test`, `pytest`, `bats` run on every PR
- `e2e-smoke` runs on PR merge + nightly
- `integration` runs on PR merge + nightly
- `wiki-sync` auto-syncs `docs/` → GitHub Wiki on push to main
- `release` builds chart + creates GH release on `v*` tag

#### Documentation
- `README.md` quick start
- `docs/INSTALL.md` — installation reference
- `docs/TROUBLESHOOTING.md` — common failures
- `docs/ARCHITECTURE.md` — system topology
- `docs/PROVIDERS.md` — Provider plugin system
- `docs/DEVELOPMENT.md` — 4-loop iteration guide
- `docs/GITOPS.md` — optional Argo CD path
- `CONTRIBUTING.md` — how to contribute
- `SECURITY.md` — security policy
- `wiki/` — Home / Topology / Deployment-Scenarios / Phase-Status / FAQ / sidebar / footer (auto-synced)

#### GitHub repo hygiene
- `.github/ISSUE_TEMPLATE/{bug,feature,config}.yml`
- `.github/PULL_REQUEST_TEMPLATE.md`
- `.github/CODEOWNERS`
- `.github/dependabot.yml` for pip + GHA + Docker
- `.github/PROJECTS.md` documents recommended Project board structure

#### Tooling
- `.pre-commit-config.yaml` (shellcheck, yamllint, ruff, helm lint, snapshot check)
- `tools/bump-version.sh` for atomic version bumps
- `tools/backup.sh` + `tools/restore.sh` Postgres stubs

#### Claude Code integration
- `.claude/skills/diagnose-deploy/SKILL.md` for richer-than-tarball diagnosis

### Notes
- Phase 1 (target: +3 days) adds Postgres + llm-gateway + NeonCart + 3 specialists + 6 tools + mice-rca use case + 1 dashboard.
- Phase 2 (target: +1-2 weeks after Phase 1) adds Support Bot + remaining specialists/tools + 10 use cases + 26 evaluators + 6 SLOs + ~14 alerts + k6 + 11 dashboards.

[Unreleased]: https://github.com/stephenwagner-grafana/observibelity/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/stephenwagner-grafana/observibelity/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/stephenwagner-grafana/observibelity/releases/tag/v0.1.0
