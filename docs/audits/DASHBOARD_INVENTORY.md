# Dashboard Inventory — ObserVIBElity v0.3.0 vs Stephen's Grafana Cloud Stack

Generated: 2026-05-13

**Stack:** `https://stephenwagner.grafana.net` (Grafana Cloud, stack id 1372178, region `prod-us-east-2`)

**Folder (chart-deployed):** `AI Observability` (uid `ai-observability`)

**Folder (legacy demo-pack):** `AI O11y` (uid `ai-o11y`) — pre-existing dashboards from the original ai-o11y-demo-pack

---

## 1. The 12 chart dashboards (shipped in `/workspace/observibelity/dashboards/`)

All 12 are deployed to Grafana Cloud as of this push. UIDs collide with pre-existing demo-pack
dashboards — backup of pre-push state lives at `/workspace/observibelity/_remote_backup_20260513/`.
Push tool: `tools/dashboards-sync.sh`. Push transport: REST `/api/dashboards/db` with `overwrite=true`.

| UID | Title (chart) | Title (was on remote) | Panels (chart / was) | Datasource portability | Status |
|---|---|---|---|---|---|
| `ai-obs-app-neoncart` | AI o11y — NeonCart | AI Observability — NeonCart | 28 / 51 | `${datasource_prom,loki,tempo}` vars | LIVE |
| `ai-obs-app-supportbot` | AI o11y — SupportBot | AI Observability — Support Bot (Acme) | 20 / 68 | vars | LIVE |
| `ai-obs-best-models` | AI o11y — Best Models (ranked by ATC) | AI Obs · Best Models — Live ATC Feed | 11 / 13 | vars | LIVE |
| `ai-obs-cascade-spike` | AI o11y — Email Cascade | AI Obs · Cascade RCA — Live Spike | 13 / 11 | vars | LIVE |
| `ai-obs-compliance` | AI o11y — Compliance | AI Obs · Compliance | 12 / 11 | vars | LIVE |
| `ai-obs-conv` | AI o11y — Conversations (Refund, Frustration, Brand) | AI Obs · Conversation Quality | 12 / 8 | vars | LIVE |
| `ai-obs-cost` | AI o11y — Cost (per-user attribution) | AI Obs · Cost & Token Consumption | 13 / 13 | vars | LIVE |
| `ai-obs-data-theft` | AI o11y — Data Theft (per-employee exfil) | AI Obs · PII & Data Theft | 15 / 11 | vars | LIVE |
| `ai-obs-evals` | AI o11y — Evaluators (Toxicity + Overview) | AI Obs · Online Evaluators | 12 / 13 | vars | LIVE |
| `ai-obs-ground` | AI o11y — Groundedness (Hallucinations) | AI Obs · Hallucination & Groundedness | 12 / 6 | vars | LIVE |
| `ai-obs-pii` | AI o11y — PII, Injection, Disclosure | AI Obs · PII & Guardrails | 15 / 8 | vars | LIVE |
| `ai-obs-tools` | AI o11y — Tools (Runaway loops) | AI Obs · Tool Execution | 13 / 8 | vars | LIVE |

**Key trade-off:** our chart dashboards use template variables for datasources (portable across stacks).
The pre-existing demo-pack dashboards had hardcoded datasource UIDs (`grafanacloud-prom`, `grafanacloud-logs`)
that only worked on Stephen's specific stack. By overwriting, we lose some per-panel content
(SupportBot dropped from 68 → 20 panels; NeonCart from 51 → 28) but gain stack-agnostic portability —
the entire reason ObserVIBElity exists.

### Direct deeplinks (org=1, last 1h)

- [ai-obs-app-neoncart](https://stephenwagner.grafana.net/d/ai-obs-app-neoncart/?orgId=1&from=now-1h&to=now)
- [ai-obs-app-supportbot](https://stephenwagner.grafana.net/d/ai-obs-app-supportbot/?orgId=1&from=now-1h&to=now)
- [ai-obs-best-models](https://stephenwagner.grafana.net/d/ai-obs-best-models/?orgId=1&from=now-1h&to=now)
- [ai-obs-cascade-spike](https://stephenwagner.grafana.net/d/ai-obs-cascade-spike/?orgId=1&from=now-1h&to=now)
- [ai-obs-compliance](https://stephenwagner.grafana.net/d/ai-obs-compliance/?orgId=1&from=now-1h&to=now)
- [ai-obs-conv](https://stephenwagner.grafana.net/d/ai-obs-conv/?orgId=1&from=now-1h&to=now)
- [ai-obs-cost](https://stephenwagner.grafana.net/d/ai-obs-cost/?orgId=1&from=now-1h&to=now)
- [ai-obs-data-theft](https://stephenwagner.grafana.net/d/ai-obs-data-theft/?orgId=1&from=now-1h&to=now)
- [ai-obs-evals](https://stephenwagner.grafana.net/d/ai-obs-evals/?orgId=1&from=now-1h&to=now)
- [ai-obs-ground](https://stephenwagner.grafana.net/d/ai-obs-ground/?orgId=1&from=now-1h&to=now)
- [ai-obs-pii](https://stephenwagner.grafana.net/d/ai-obs-pii/?orgId=1&from=now-1h&to=now)
- [ai-obs-tools](https://stephenwagner.grafana.net/d/ai-obs-tools/?orgId=1&from=now-1h&to=now)

---

## 2. Existing dashboards (in Grafana Cloud, NOT in our chart) — candidates to inherit

These already live in `https://stephenwagner.grafana.net` and use the same `gen_ai.*` / `ai_o11y.*`
telemetry conventions. They are referenced for the runbook, NOT re-shipped (yet) in our chart because
their datasource UIDs are hardcoded — they need to be genericized to `${datasource_prom}` etc. before
ObserVIBElity ships them.

### Tier A — runbook entry points (link from README/runbook now; genericize for chart later)

| UID | Title | Panels | Vars | Why feature it | Caveats |
|---|---|---|---|---|---|
| `ai-obs-use-case-selector` | AI Observability — Use Case Builder | 44 | 4 | "Meta dashboard for picking which use case to view" — natural homepage of the demo | Hardcoded `grafanacloud-prom` / `grafanacloud-logs` |
| `ai-obs-landing` | AI Observability — Landing Page (Demo Agenda) | 17 | 0 | Demo agenda navigation | 2MB locally (embedded images) — not chart-portable yet |
| `ai-obs-app-landing` | AI Observability — Apps | 9 | 0 | Apps navigation hub | hardcoded ds |
| `ai-obs-galvanic` | The Black Box of Galvanic — AI Observability Playbook | 12 | 0 | Customer-facing playbook narrative | hardcoded ds |
| `ai-obs-demo-playbook` | AI Observability — Demo SE Playbook | 6 | 0 | SE-facing demo flow | hardcoded ds |

### Tier B — lens dashboards (existing demo-pack ones we don't yet ship)

| UID | Title | Panels | Why useful | Recommendation |
|---|---|---|---|---|
| `ai-obs-traces` | AI Obs · Multi-step Traces | 7 | Tempo-anchored multi-step trace lens | Genericize + add to chart in v0.4 |
| `ai-obs-errors` | AI Obs · Errors & Stop Reasons | 7 | Error breakdown by stop reason | Genericize + add in v0.4 |
| `ai-obs-latency` | AI Obs · Latency & TTFT | 8 | TTFT/p95/p99 latency | Genericize + add in v0.4 |
| `ai-obs-rag` | AI Obs · RAG Quality | 7 | RAG recall/precision/coverage | If RAG use case exists |
| `ai-obs-prompts` | AI Obs · Prompt & Agent Insights | 5 | Prompt-level breakdown | Genericize + add in v0.4 |
| `ai-obs-subagent` | AI Obs · Sub-Agent Visualizer | 5 | Sub-agent call tree | Useful for agentic demos |
| `ai-obs-biz` | AI Obs · Custom Business KPIs | 7 | Business KPI overlay | Template for users to extend |

### Tier C — app-specific deep dives (NeonCart only — Stephen's local addition)

| UID | Title | Panels | Why featured |
|---|---|---|---|
| `neoncart-ai-rca-conv` | NeonCart — AI RCA (Single Conversation) | 17 | Single-conversation drill-down — explicitly called out in original prompt |
| `neoncart-ai-o11y` | NeonCart — AI Observability RCA | 20 | Multi-conversation RCA view |
| `neoncart-ai-business` | NeonCart — AI Business KPIs | 24 | Per-store NeonCart business view |
| `neoncart-convos` | NeonCart — AI Operations | 21 | Conversation operations |
| `neoncart-demo` | NeonCart Demo — SRE Failure + AI Behavior | 17 | SRE failure scenarios |
| `app-o11y-neoncart` | Application Observability — NeonCart | 17 | Application Observability product view |
| `ai-obs-playbook-neoncart` | AI Observability — NeonCart Playbook | 6 | Demo playbook |
| `ai-obs-playbook-supportbot` | AI Observability — Support Bot Playbook | 6 | Demo playbook |

These are kept in Grafana Cloud but NOT in our chart — they are app-specific deep-dives that
predate the modular use-case architecture in ObserVIBElity v0.3.

### Tier D — auxiliary/test/internal (DO NOT inherit — noise)

UIDs `ai-obs-app-test-app-1` ... `ai-obs-app-test-app-23`, `ai-obs-uc-test-*`, `ai-obs-builder-tracker`,
`ai-obs-use-case-builder`, `ai-obs-use-case-overviews`, `ai-obs-app-doc-summarizer`,
`ai-obs-app-hrbot`, `ai-obs-app-model-tester` — these are demo-pack test scaffolding from the
mcp-uc-builder MCP server (jobs that spawned synthetic dashboards). Leave them where they are;
they don't belong in the chart.

---

## 3. Recommendations for the demo runbook

**Primary entry point (Phase 1 demo open):**
1. [`ai-obs-app-neoncart`](https://stephenwagner.grafana.net/d/ai-obs-app-neoncart/?orgId=1&from=now-1h&to=now) — chart-shipped NeonCart dashboard
2. From there → trace pivot → mice-rca panel

**Phase 2 use-case dashboards (open in sequence during demo):**
3. [`ai-obs-evals`](https://stephenwagner.grafana.net/d/ai-obs-evals/) — show toxicity / online evaluators are running
4. [`ai-obs-pii`](https://stephenwagner.grafana.net/d/ai-obs-pii/) — PII / injection / disclosure
5. [`ai-obs-data-theft`](https://stephenwagner.grafana.net/d/ai-obs-data-theft/) — per-employee data exfil
6. [`ai-obs-cascade-spike`](https://stephenwagner.grafana.net/d/ai-obs-cascade-spike/) — email cascade RCA
7. [`ai-obs-best-models`](https://stephenwagner.grafana.net/d/ai-obs-best-models/) — model leaderboard

**Optional deep-dive links (from existing demo-pack):**
- [`ai-obs-use-case-selector`](https://stephenwagner.grafana.net/d/ai-obs-use-case-selector/) — entry point for picking a use case (44 panels — Stephen's local meta dashboard)
- [`neoncart-ai-rca-conv`](https://stephenwagner.grafana.net/d/neoncart-ai-rca-conv/) — single-conversation drill-down

---

## 4. Compatibility issues found

1. **Datasource UIDs hardcoded vs templated.** Our 12 chart dashboards use template variables
   (`${datasource_prom}`, `${datasource_loki}`, `${datasource_tempo}`). The pre-existing demo-pack
   dashboards we did NOT ship hardcode `grafanacloud-prom` / `grafanacloud-logs` / `grafanacloud-traces`.
   To inherit them into the chart, we must run a sed-style rewrite to convert datasource refs to
   the variable form. Not done yet — future work.

2. **Label namespace.** Both our 12 and the pre-existing demo-pack dashboards consume `gen_ai.*` and
   `ai_o11y.*` labels. No mismatch detected — the conventions are aligned. **OK.**

3. **Folder.** Our chart dashboards all landed in folder `AI Observability` (uid `ai-observability`).
   Pre-existing demo-pack dashboards live in both `AI Observability` and `AI O11y` (uid `ai-o11y`)
   inconsistently. Not a blocker — just an organizational nit. If we want one canonical folder for
   the chart's output, the current state (all 12 in `AI Observability`) is correct.

4. **Title naming convention.** Chart dashboards prefix with "AI o11y —" (e.g. "AI o11y — NeonCart").
   Pre-existing demo-pack dashboards used "AI Observability —" or "AI Obs ·". The chart's titles
   are now the authoritative ones in the user's stack. Existing bookmarks and runbooks that reference
   the old titles by string would need updates; deeplinks by `/d/<uid>/` continue to work.

5. **No panel ID overlap risk.** Confirmed each chart dashboard has its own panel ID space; no
   cross-dashboard ID collisions occur because each dashboard is upserted by uid.

---

## 5. Backup location

Pre-push remote snapshots stored at `/workspace/observibelity/_remote_backup_20260513/`:
12 files, one per UID. If we ever need to restore the pre-ObserVIBElity dashboards (e.g. for a
51-panel NeonCart deep-dive view), the JSON is recoverable from there.

---

## 6. Counts summary

- Chart dashboards: **12 of 12 confirmed live** in Grafana Cloud
- Pre-existing AI o11y demo dashboards in the user's stack: **62**
- Worth featuring in runbook (existing): **2** (`ai-obs-use-case-selector`, `neoncart-ai-rca-conv`)
- Inheritance candidates to add to chart in v0.4 (need datasource genericization): **7**
  (`ai-obs-traces`, `ai-obs-errors`, `ai-obs-latency`, `ai-obs-rag`, `ai-obs-prompts`,
  `ai-obs-subagent`, `ai-obs-biz`)
- Conflicts: **0 blocking**, several cosmetic (titles, folder org)
