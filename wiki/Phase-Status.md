# Phase Status

A live-ish dashboard of where ObserVIBElity is in its rollout. Items below
track GitHub issues/PRs labeled by phase; this page is auto-rendered from the
repo every push to `main`.

## Current phase: Phase 2 — Full demo

Phase 2 **shipped 2026-05-13** in v0.3.0. Both apps (NeonCart + Support
Bot) are live with realistic data volume (200 personas, 500 products,
1k orders, 5k convs, 30 KB articles, 500 tickets). The persona-picker
"View as: <name>" dropdown in both navbars makes SE demos one-click;
every span propagates `ai_o11y.persona_id`. The k6 continuous-traffic
engine runs all use-case scenarios on a 10-second loop. 24 container
images now build automatically (release.yml on tag, build-images.yml
on push to main). Grafana Cloud sync is fully automated (dashboards +
evaluators + alerts via sync.yml).

12 dashboards now ship (was 1): best-models, cascade-spike, data-theft,
app-supportbot, pii, ground, conv, compliance, tools, cost, evals,
plus the Phase 1 app-neoncart.

Phase 1 (shipped 2026-05-13 in v0.2.0) gave the first end-to-end demo
loop. Phase 2 makes the whole spec real.

## Phase 0 deliverables

- [x] Helm chart skeleton (`Chart.yaml`, `values.yaml`, `values-docker-desktop.yaml`)
- [x] `install.sh` with 6 subcommands (`preflight | wizard | deploy | verify | doctor | reset`)
- [x] Preflight: OS detect, binary check + auto-install to `./tools/bin/`, cluster + admin perms check, live credential validation
- [x] Wizard: 6-prompt interactive flow; non-interactive via `.env + --auto`
- [x] Cluster bootstrap: `./tools/bootstrap-cluster.sh` creates a k3d cluster
- [x] Deploy-doctor: bash wrapper + Python collector; Phase 1 wires LLM call
- [x] Verify + evaluators-sync stubs
- [x] State file `.observibelity-state` (JSON, resumable)
- [x] Tests: bats + helm-unittest + pytest + golden snapshot + k3d-in-GHA smoke
- [x] GHA workflows: lint, helm-test, pytest, bats, e2e-smoke, wiki-sync
- [x] Docs: INSTALL, TROUBLESHOOTING, ARCHITECTURE, PROVIDERS
- [x] Claude Code skill: `diagnose-deploy`
- [x] Makefile with `dev / verify / test / smoke / doctor / snapshot / watch / help` (4-loop iteration)
- [x] Skaffold config (stub for Phase 0; artifacts arrive in Phase 1)
- [x] `helm test` pod (templates/tests/test-connection.yaml)
- [x] install.sh `deploy` phase unstubbed: `helm upgrade --install --atomic --wait`
- [x] Integration tests (helm upgrade / rollback / idempotency / helm test)
- [x] Pre-commit hooks (shellcheck, yamllint, ruff, helm lint, snapshot diff)
- [x] Release workflow (.github/workflows/release.yml) — tag-driven, builds chart + GH release
- [x] GitHub hygiene: ISSUE_TEMPLATE (bug + feature + config), PR template, CODEOWNERS, dependabot, SECURITY
- [x] CHANGELOG.md (Keep-a-Changelog) + tools/bump-version.sh (atomic version bump)
- [x] Production-leaning values defaults: resource limits + securityContext per component
- [x] tools/backup.sh + tools/restore.sh (Phase 0 stubs; Phase 1 wires up Postgres)
- [x] docs/DEVELOPMENT.md (4-loop guide), docs/GITOPS.md (Argo CD optional path), CONTRIBUTING.md
- [x] .envrc.example for direnv users
- [x] Phase 1 stub dirs: `src/`, `registry/`, `migrations/`, `seed_data/` with READMEs
- [x] Phase 1 image build infra: Dockerfiles per app + shared base images + tools/build-images.sh
- [x] docs/CLAUDE-CODE.md — Claude Code integration guide (skills + MCP)
- [x] `make init` + `make verify-repo` + tools/check-scaffold.sh
- [x] .vscode/ quality-of-life config
- [x] CONSISTENCY_REPORT.md — initial scaffold audit baseline
- [x] Regenerated golden snapshot for new templates
- [x] Deploy web wizard (static HTML on GitHub Pages) — wizard/deploy.html + GHA workflow pages.yml
- [x] Use-case authoring system: bundled YAML schema + Pydantic compiler + 5 archetype template packs
- [x] Use-case authoring surfaces: bash wizard, Claude Code skill, web wizard
- [x] Migration importer from /workspace/ai-o11y-demo-pack/
- [x] docs/USE-CASES.md + tests/pytest/test_usecase_build.py + make build/test-usecases targets

## Phase 1 — Mice end-to-end ✓ shipped 2026-05-13

Phase 1 lands the **mice-rca** use case end-to-end. A user running `./install.sh`
gets a real NeonCart, a real chatbot, real specialists, real tools, real
Postgres, real OTel data flowing to their Grafana Cloud — and the famous
"show me mice" prompt produces a trace they can find in their Tempo.

- [x] Postgres pod + PVC + Alembic migrations (17 tables for Phase 1)
- [x] Seed Job: NeonCart catalog + 150 personas from CSV
- [x] `llm-gateway` Deployment with `AnthropicProvider` wired up
- [x] `neoncart` Deployment: FastAPI + Jinja + HTMX, chatbot widget, branding from values.yaml
- [x] Specialists: `nc-chatbot`, `nc-fraud-detector`, `nc-fulfillment-orchestrator`
- [x] Tools: `search_products`, `get_product`, `get_order_history`, `geo_lookup`, `get_inventory`, `place_order`
- [x] UseCase: `mice-rca` with 2 evaluators
- [x] OTel collector → Grafana Cloud
- [x] Dashboard: `ai-obs-app-neoncart` (gcx-synced)
- [x] Verification: "show me mice" produces a trace visible in user's Tempo

## Phase 1 status

Shipped in v0.2.0 (2026-05-13). The parallel-agent build round landed:

- [x] Postgres StatefulSet + PVC + Alembic migrations (17 tables)
- [x] Seed Job + CSVs (catalog + 50 personas + geo + KB)
- [x] llm-gateway with AnthropicProvider wired
- [x] NeonCart FastAPI app with chatbot widget
- [x] 3 specialists: nc-chatbot, nc-fraud-detector, nc-fulfillment-orchestrator
- [x] 6 tools: search_products, get_product, get_order_history, geo_lookup, get_inventory (with mice-rca error trigger), place_order
- [x] mice-rca use case + 2 evaluators
- [x] OTel collector → Grafana Cloud
- [x] ai-obs-app-neoncart dashboard
- [x] All 22 use case YAMLs authored (Phase 2 components fire when live traffic + evaluators land)

## Phase 2 — Full demo ✓ shipped 2026-05-13 (v0.3.0)

Phase 2 lands the whole spec. Both apps live with realistic data volume,
persona-based "View as" demo UX, continuous traffic, real Grafana Cloud
sync, automated image builds. Image inventory expanded from 13 to 24
(2 base + 2 apps + 14 specialists + 16 tools).

- [x] Support Bot + all 11 SB specialists + all 10 SB tools
- [x] Persona picker UI ("View as: Tim Lewis") in both NeonCart + SupportBot
- [x] Expanded seed data: 200 personas, 500 products, ~1k orders, ~5k conversation turns, 30 KB articles, ~500 tickets
- [x] 11 more dashboards (best-models, cascade-spike, data-theft, app-supportbot, pii, ground, conv, compliance, tools, cost, evals)
- [x] k6 in-cluster traffic engine (Deployment + ConfigMap + scenarios, 10-second loop)
- [x] SLO + alert chart templates (`templates/alerts/`, `templates/slos/`) emitting from `registry/_generated/`
- [x] `tools/alerts-sync.sh` — Mimir rules API integration
- [x] Real `tools/dashboards-sync.sh` + `tools/evaluators-sync.sh` (was Phase 0 stub)
- [x] `release.yml` wired to docker buildx + multi-arch + ghcr.io push (24 images)
- [x] `build-images.yml` for `:latest` push on main
- [x] `sync.yml` — auto-push dashboards + evaluators + alerts on push to main
- [x] `make deploy-k3s-local` + `tools/k3s-import-images.sh`
- [x] `docs/K3S-LOCAL.md` — full local-k3s deploy guide
- [x] k6 helm-unittest

## Phase 3 — Polish (future)

Deferred items remaining after Phase 2 ship:

- [ ] `OllamaProvider` wired; lockstep model rotation across providers
- [ ] In-cluster LGTM option (Loki + Grafana + Tempo + Mimir on the user's cluster, optional alternative to Grafana Cloud)
- [ ] Full vibe-edit Claude Code skill suite (all 6 `.claude/skills/` complete)
- [ ] Dashboard panel queries rewritten to use `traces_spanmetrics_*` (today many panels query `http_requests_total` which isn't emitted; see `docs/audits/LIVE_VALIDATION.md`)
- [ ] Native OTel `gen_ai_client_*` metrics from llm-gateway (currently only logs + trace attrs)

## Update mechanism

This page is auto-rendered from the repo on every push to `main` (see
[`.github/workflows/wiki-sync.yml`](https://github.com/stephenwagner-grafana/observibelity/blob/main/.github/workflows/wiki-sync.yml)).
Items track GitHub issues/PRs labeled by phase.

To request a change, open an issue labeled `phase:0`, `phase:1`, or `phase:2`
on the [issue tracker](https://github.com/stephenwagner-grafana/observibelity/issues).
