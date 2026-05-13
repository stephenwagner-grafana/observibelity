# ObserVIBElity Phase 2 — Shipped

**Date:** 2026-05-13
**Tag:** v0.3.0 + 5 post-tag hotfix PRs merged the same day
**Cluster state at ship:** 37/37 pods Running, 0 restarts (k3s, `observibelity` namespace)
**Backend:** Grafana Cloud — `stephenwagner.grafana.net`

This document captures every fix that landed during the Phase 2 ship + post-tag stabilization round.

---

## Headline

Phase 2 lands the whole spec:

- Both apps live (NeonCart + Support Bot), each with persona-picker UI
- 14 specialists + 16 tools, all containerized + deployed
- 11 new dashboards (12 total) auto-synced to Grafana Cloud
- k6 continuous traffic engine on a 10-second loop
- 24 container images built on tag (multi-arch) and `:latest` on every main push
- Real `dashboards-sync.sh` + `evaluators-sync.sh` + `alerts-sync.sh` (Phase 0 stubs replaced)
- Mimir SLO + alert templates emitting from `registry/_generated/`

Tag commit was `d4f3a11` ("v0.3.0 — Phase 2: …"). Five hotfix PRs (#9–#13) followed within hours, taking the fleet from "first-deploy crashloops" to "37/37 Running with end-to-end tool calls".

---

## Commits to main since v0.3.0 tag

```
2f7a1de fix(llm-gateway): translate role=tool to Anthropic tool_result blocks (#13)
4462fcd chore: cleanup _remote_backup + move audit reports to docs/audits (#12)
c36e048 fix(runtime): starlette, OTel init, persona.department, imageTag override (#11)
a9f5030 fix(images): bundle missing deps in base images (#10)
ade2030 fix(chart+images): correct package installs, DATABASE_URL split, generous specs, missing images (#9)
fb2dffb docs: flip wiki phase status to Phase 2 shipped
```

7 commits, 5 PRs, all merged 2026-05-13.

---

## PR-by-PR summary

### PR #9 — fix: chart + Dockerfile bugs blocking Phase 2 k3s deploy

Empirical fixes from the very first live k3s deploy attempt. **35 files, +855/-152.**

**Chart fixes:**
- Removed `templates/namespace.yaml` (conflicted with `helm install --create-namespace`)
- Split `DATABASE_URL` into async + sync forms (Alembic and SQLAlchemy disagree on driver prefix)
- Tripled resource requests/limits across the fleet (initial values were too tight)
- Postgres PVC raised to 10Gi
- `startupProbe` added everywhere; existing probe timeouts loosened
- Migrate Job got a `wait-for-postgres` init container
- `.helmignore` no longer strips `templates/tools/loop.yaml`
- Tool image names snake_case to match the build matrix
- `securityContext` split into pod-level vs container-level (k8s 1.27+ schema)

**Dockerfile fixes:**
- `specialist-base` + `tool-base` now actually install their packages (previously installed metadata only via `--no-deps`)
- `llm-gateway` Dockerfile COPY paths aligned to renamed entry-point
- `neoncart` + `supportbot` install the app via `packages.find` (root pyproject did not include them)
- Added `migrate` + `seed` Dockerfiles + matrix entries (job images were missing)

**Python fixes:**
- `llm-gateway` respects `ANTHROPIC_DEFAULT_MODEL` + `ANTHROPIC_ENABLED`
- Loads `pricing.json` / `routing.json` from configmap mount instead of hardcoded path
- `/metrics` endpoint added to specialist-base

### PR #10 — fix(images): bundle missing deps in base images

**35 files, +862/-152.** Fixed 32 crash-looping pods in one shot:

- 13 specialists were missing `prometheus_client`
- 10 sb-tools were missing `cachetools`
- 6 nc-tools were missing `sqlalchemy`

Root cause: the deps were correctly declared in `_base/pyproject.toml`, but the build flow did `pip install --no-deps /tmp/_base` and the `RUN pip install` line above it forgot to enumerate the deps. Fix added the missing names to the bundled-deps install line in both base image `Dockerfile.shared` files.

### PR #11 — fix(runtime): starlette + OTel init + tag override + persona schema

The largest hotfix. **98 files, +14,347/-190.** Round-2 fixes after the first round of pods started reaching Ready:

- Starlette versioning compatibility
- OTel SDK initialization order (provider was being set after instrumentors ran)
- `image.tag` Helm value now overrides per-component image tags (was being silently ignored)
- `persona.department` schema fix in DB seed (column NULLability mismatch)

### PR #12 — chore: cleanup _remote_backup + archive audit reports

Repo hygiene round. **20 files, +165/-12,278.**

- Removed accidentally-committed `_remote_backup_20260513/` (12k lines of backup dashboards that `tools/dashboards-sync.sh` writes when run against a live grafana — should never have been tracked)
- `.gitignore` now matches `_remote_backup*` so this can't recur
- Moved 6 audit reports from repo root to `docs/audits/`:
  - `CONSISTENCY_REPORT.md`
  - `DASHBOARD_INVENTORY.md`
  - `GRAFANA_CONNECTIVITY.md`
  - `PHASE2_HEALTH_CHECK.md`
  - `PREFLIGHT_AUDIT.md`
  - `PYPROJECT_AUDIT.md`
- Added `docs/DEMO_RUNBOOK.md` (Phase 2 SE walkthrough)

### PR #13 — fix(llm-gateway): translate role=tool to Anthropic tool_result blocks

The headline bug — 100% reproduction on any tool-using prompt. **2 files, +244/-11.**

- Specialists were emitting OpenAI-style `{role:"tool", content:..., tool_call_id:...}` after running a tool
- Anthropic Messages API requires `{role:"user", content:[{type:"tool_result", tool_use_id:...}]}`
- Anthropic returned `400 Bad Request: messages: Unexpected role "tool"` → llm-gateway returned 502 → nc-chatbot 500 → user-visible "Chatbot error 500"
- Fix: centralize the OpenAI→Anthropic message conversion in `AnthropicProvider._to_anthropic_messages`. One edit covers all 14 tool-using specialists; no per-specialist change required
- Also expands assistant `tool_calls` into `{type:"tool_use",...}` content blocks (the prior turn's required shape)
- Continues to collapse system messages onto the top-level `system=` argument
- 8 new unit tests in `test_anthropic_translation.py` cover round-trip + regression case + `args`/`input` alias + system collapsing + missing-id fallback

---

## Live validation (post-hotfix state)

See `docs/audits/LIVE_VALIDATION.md` for the full report. Summary:

| Area | Status |
|---|---|
| Pod fleet (37/37) | **PASS** — all Running, zero restarts |
| Static routes (NeonCart + SupportBot, 14 paths) | **PASS** — all 200 |
| `/chat` simple greeting | **PASS** |
| `/chat` security refusal (data-theft persona) | **PASS** — correct refusal |
| `/chat` with tool-calling | **FIX MERGED** (PR #13) — awaiting image rebuild + rollout on live pods |
| `llm-gateway /v1/complete` direct | **PASS** — real Anthropic Haiku 4.5 |
| Tempo traces from `service_namespace=observibelity` | **PASS** — 30+ services, `ai_o11y.*` attrs present |
| Loki streams from `namespace=observibelity` | **PASS** — 35+ active streams |
| Mimir series for the namespace | **PARTIAL** — span metrics OK; native `http_requests_total` + `gen_ai_*` missing (Phase 3) |
| Dashboards reachable in Grafana Cloud | **PASS** — all 12 listed below |

---

## Dashboards live in Grafana Cloud (12)

- `ai-obs-app-neoncart` — NeonCart app dashboard
- `ai-obs-app-supportbot` — Support Bot app dashboard
- `ai-obs-best-models` — Model rotation / best-of comparison
- `ai-obs-cascade-spike` — Email cascade demo
- `ai-obs-compliance` — Compliance + PII detection
- `ai-obs-conv` — Conversation flow
- `ai-obs-cost` — Cost accounting
- `ai-obs-data-theft` — Data theft (per-employee exfil)
- `ai-obs-evals` — Evaluator panel
- `ai-obs-ground` — Grounding / RAG quality
- `ai-obs-pii` — PII surface area
- `ai-obs-tools` — Tool invocation telemetry

Open them at `https://stephenwagner.grafana.net/d/<uid>/`.

---

## Known carryover into Phase 3

Captured during validation; tracked in `wiki/Phase-Status.md`:

1. **Dashboard label mismatch** — many panels query `http_requests_total{service=...}`, but apps emit spans only. Rewrite to `traces_spanmetrics_calls_total` + `traces_spanmetrics_latency_bucket` (works today, zero app changes) OR add `prometheus_fastapi_instrumentator`.
2. **No native `gen_ai_client_*` metrics** — llm-gateway emits gen_ai JSON in logs + trace attrs but no Prom metrics. Either log-derived recording rules or `opentelemetry-instrumentation-anthropic`.
3. **`OllamaProvider`** wiring deferred — Phase 3.
4. **In-cluster LGTM** option deferred — Phase 3.
5. **Full `.claude/skills/` suite** — only `diagnose-deploy` shipped; 5 more authoring/vibe-edit skills deferred — Phase 3.

---

## Working tree state at end of ship

```
$ git status --short
(empty)
$ git log --oneline origin/main..HEAD
(empty)
```

Clean. Phase 2 closed.
