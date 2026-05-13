# Changelog

All notable changes to ObserVIBElity will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.3.0] - 2026-05-13

The Phase 2 release. Support Bot ships alongside NeonCart, 11 more dashboards, persona-based demo UX, k6 continuous traffic, automated image builds and Grafana Cloud sync.

### Added

#### Apps + workloads
- **Support Bot** (`src/supportbot/`) — internal HR/IT support FastAPI app with persona picker UI, ticket views, KB browser
- **11 Support Bot specialists**: sb-router, sb-policy-finder, sb-kb-search, sb-ticket-helper, sb-employee-info, sb-it-troubleshoot, sb-hr-info, sb-expense-helper, sb-security-handler, sb-hiring-helper, sb-escalator
- **10 Support Bot tools**: kb_search, list_tickets, get_ticket, create_ticket, update_ticket, get_employee, get_employee_history, reset_password, request_access, create_expense
- **Persona picker UI** in both apps — "View as: Tim Lewis" dropdown propagates persona_id to every specialist call; every span gets `ai_o11y.persona_id`
- **k6 continuous-traffic engine** (`templates/k6/`) — Deployment + ConfigMap, runs all use case scenarios on a 10-second loop
- **baseline.js** scenario — always-on heartbeat traffic across all 200 personas

#### Data
- **200 personas** (up from 50) with 30 offenders distributed across 6 patterns (exfil, cascade, leak, verbose, bad_faith, injection)
- **500 catalog items** (up from 200)
- **~1000 historical orders** + ~2500 order_items, distributed over 90 days
- **~5000 conversation turns** across ~2000 sessions, with realistic per-persona content (including offender patterns)
- **30 Support Bot KB articles**: policies, IT, HR, security, expense, hiring, etc.
- **~500 tickets** seed data for the Support Bot ticket views
- **`seed_data/_generate.py`** — deterministic CSV regeneration script (fixed seed)

#### Dashboards (12 total now, was 1)
- ai-obs-best-models — Model winner leaderboard
- ai-obs-cascade-spike — Email cascade detection
- ai-obs-data-theft — Tim exfil leaderboard
- ai-obs-app-supportbot — Support Bot health
- ai-obs-pii — PII detection cross-app
- ai-obs-ground — Hallucination/groundedness
- ai-obs-conv — Conversational metrics
- ai-obs-compliance — Compliance signals
- ai-obs-tools — Tool call analytics
- ai-obs-cost — Cost tracking + per-user anomalies
- ai-obs-evals — Evaluator overview

#### Alerting + SLOs
- **`templates/alerts/_loop.yaml`** — emits PrometheusRule CRDs or ConfigMaps from `registry/_generated/alerts/`
- **`templates/slos/_loop.yaml`** — emits OpenSLO ConfigMaps from `registry/_generated/slos/`
- **`tools/alerts-sync.sh`** — push Mimir alerts via Grafana Cloud API

#### Automation
- **`release.yml` image builds** — docker buildx + multi-arch (linux/amd64 + linux/arm64), pushes 24 images to ghcr.io on tag
- **`build-images.yml`** — same image builds triggered on push to main with `:latest` tags only
- **`sync.yml`** — auto-pushes dashboards + evaluators + alerts to Grafana Cloud on push to main
- **`tools/dashboards-sync.sh`** — real implementation (gcx + REST fallback) replacing the Phase 0 stub
- **`tools/evaluators-sync.sh`** — real Grafana AI Observability plugin REST API integration
- **`tools/alerts-sync.sh`** — Mimir rules API integration

#### Deployment
- **`make deploy-k3s-local`** — builds images locally, imports into k3s containerd, deploys
- **`tools/k3s-import-images.sh`** — supports local + remote (`--remote HOST`) k3s nodes
- **`docs/K3S-LOCAL.md`** — full local-k3s deploy guide

#### Tests
- **k6 helm-unittest** for the traffic engine templates

### Changed
- `values.yaml` adds: k6 (full config), alerts, slos, supportbot enabled, expanded specialists + tools registry lists (now 14 specialists + 16 tools)
- `release.yml` actually builds images now (Phase 1 had a TODO)
- Both Dockerfiles for specialists + tools accept `SPECIALIST_BASE` / `TOOL_BASE` build args

### Notes
- 24 container images on first tag push: 2 base + 2 apps + 14 specialists + 16 tools (matching the matrix in release.yml/build-images.yml)
- The k6 engine runs continuously when phase>=2; in phase 1 it stays off (gate in template)
- For users without Grafana Cloud, alerts target=configmap-only emits raw ConfigMaps for inspection
- For users with Grafana Cloud, sync.yml auto-pushes dashboards/alerts/evaluators on push to main when secrets are set

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

[Unreleased]: https://github.com/stephenwagner-grafana/observibelity/compare/v0.3.0...HEAD
[0.3.0]: https://github.com/stephenwagner-grafana/observibelity/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/stephenwagner-grafana/observibelity/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/stephenwagner-grafana/observibelity/releases/tag/v0.1.0
