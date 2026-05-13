# Phase Status

A live-ish dashboard of where ObserVIBElity is in its rollout. Items below
track GitHub issues/PRs labeled by phase; this page is auto-rendered from the
repo every push to `main`.

## Current phase: Phase 1 — Mice-rca centerpiece

Phase 1 **shipped 2026-05-13** in v0.2.0. NeonCart is real, the chatbot is
real, three specialists and six tools call a real `llm-gateway` (Anthropic
provider wired), Postgres runs with 17 seeded tables, and OTel data flows
to the user's Grafana Cloud stack. The famous "show me mice" prompt
produces a trace in the user's Tempo and pivots through the
`ai-obs-app-neoncart` dashboard.

All 22 planner use case YAMLs are authored on the repo; Phase 2 activates
the remaining 21 at runtime when live evaluators + traffic engine land.

The point of Phase 1 is the **first end-to-end demo loop**: a user runs
`./install.sh`, types "show me mice", and gets one trace ID → one fix.

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

## Phase 2 — Full set (target: +1-2 weeks after Phase 1)

Phase 2 is the whole spec. Support Bot, full specialist + tool inventory, full
provider matrix, full UC catalog, full evaluator suite, full SLO+alert set,
full traffic engine, full dashboard library, full vibe-editing surface.

- [ ] Support Bot + all 11 SB specialists + all 10 SB tools
- [ ] Remaining NeonCart specialists (10 more)
- [ ] `OllamaProvider` wired; lockstep model rotation
- [ ] All 10 use cases (with email-cascade and data-theft-tim as centerpieces)
- [ ] All 26 evaluators (manual UI today; `tools/evaluators-sync.sh` stub waiting on gcx)
- [ ] 6 SLOs + ~14 alerts
- [ ] k6 in-cluster, 10 traffic scenarios
- [ ] 11 more dashboards (gcx git-sync)
- [ ] All 6 `.claude/skills/`

## Update mechanism

This page is auto-rendered from the repo on every push to `main` (see
[`.github/workflows/wiki-sync.yml`](https://github.com/stephenwagner-grafana/observibelity/blob/main/.github/workflows/wiki-sync.yml)).
Items track GitHub issues/PRs labeled by phase.

To request a change, open an issue labeled `phase:0`, `phase:1`, or `phase:2`
on the [issue tracker](https://github.com/stephenwagner-grafana/observibelity/issues).
