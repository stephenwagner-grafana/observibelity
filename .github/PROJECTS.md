# Recommended GitHub Project board

ObserVIBElity uses a **GitHub Projects (v2)** board to track Phase 1 + Phase 2 work in the open. This file documents the recommended structure; create the board via the GH UI at:

  https://github.com/stephenwagner-grafana/observibelity/projects

## Board structure

**Type:** Board view, grouped by Status

**Statuses:**
- 📋 Backlog
- 🔍 Refining
- 🎯 Ready (next-up, well-defined)
- 🏗️ In progress
- 🧪 In review
- ✅ Done

**Custom fields:**
- `Phase` (single select): Phase 0 / Phase 1 / Phase 2
- `Component` (single select): Chart / Install / Wizard / Preflight / Deploy-doctor / Postgres / LLM-gateway / NeonCart / Support-Bot / OTel / Dashboards / Alerts / k6 / Docs / Tests / GHA / Wiki
- `Priority` (single select): P0 (blocker) / P1 (high) / P2 (normal) / P3 (low)
- `Size` (single select): XS (< 1 hour) / S (< 1 day) / M (1-3 days) / L (1 week) / XL (multi-week)

**Automation rules** (GH Projects native):
- New issues with label `phase:1` → auto-add, Status = Backlog, Phase = Phase 1
- PRs that close issues → auto-move issue to In review, then Done on merge
- Issues open for 14 days with no activity → comment + flag for refinement

## Recommended labels

Create these on the repo (Settings → Labels):
- `phase:0` `phase:1` `phase:2` — phase tags
- `component:install` `component:wizard` `component:preflight` … — one per component
- `priority:p0` `priority:p1` `priority:p2` `priority:p3` — priority
- `good-first-issue` — easy entry point for new contributors
- `help-wanted` — needs a hand
- `blocked` `wontfix` `duplicate` — meta

## Phase 1 backlog seed
Create issues for each Phase 1 deliverable from [Phase-Status.md](https://github.com/stephenwagner-grafana/observibelity/wiki/Phase-Status):

- [ ] #N — Postgres pod + PVC + Alembic migrations
- [ ] #N — Seed Job: catalog + personas
- [ ] #N — llm-gateway Deployment with AnthropicProvider
- [ ] #N — neoncart Deployment + chatbot widget
- [ ] #N — Specialists: nc-chatbot, nc-fraud-detector, nc-fulfillment-orchestrator
- [ ] #N — Tools: search_products + 5 others
- [ ] #N — UseCase: mice-rca + 2 evaluators
- [ ] #N — OTel collector → Grafana Cloud
- [ ] #N — Dashboard: ai-obs-app-neoncart

## Project board automation script
A future helper `tools/sync-issues.sh` will read `wiki/Phase-Status.md` and ensure one issue exists per [ ] item. Not implemented in Phase 0.
