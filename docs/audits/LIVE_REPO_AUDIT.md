# Live ↔ Repo Reconciliation Audit

**Date:** 2026-05-13
**Stack:** `https://stephenwagner.grafana.net` (Grafana Cloud, stack id 1372178, region `prod-us-east-2`)
**Folder:** `ObserVIBElity` (uid `observibelity`)
**Cluster:** k3s, namespace `observibelity`
**Helm release:** `observibelity` v22 (chart `observibelity-0.3.0`)

This audit reconciles the live Grafana Cloud + k8s state with the `observibelity` GitHub repo per the standing directive: **every improvement made to the real environment must persist to the repo**.

---

## TL;DR

| Surface | Live count | Repo count (before) | Repo count (after) | Action |
|---|---|---|---|---|
| Dashboards in `ObserVIBElity` folder | 17 | 12 | 17 | **synced live → repo** |
| Helm-managed ConfigMaps | 5 | 5 (templated) | 5 (templated) | no drift |
| Helm-managed Secrets | 3 | 3 (templated) | 3 (templated) | no drift |
| k6 `baseline.js` | 21,785 B | 18,771 B (HEAD) / 21,785 B (working tree) | 21,785 B | **HEAD lagged live — working tree already had the live version; committed in this PR** |
| Helm `userSuppliedValues` vs `values-deploy.yaml` | — | — | — | formatting-only drift (no semantic delta) |

---

## 1. Dashboards (the big one)

Listed all dashboards with `folderUIDs=observibelity` via Grafana Cloud's `/api/search`. **17 dashboards** are live in that folder, not 12 as the prompt assumed.

### 1a. 12 dashboards already in repo — *semantically identical to live*

The 12 chart-shipped dashboards round-tripped through jq (`del(.id,.version,.uid)`) match live byte-for-byte. The on-disk diff that `git status` shows on these 12 files is **cosmetic only**:

1. `jq` reorders object keys alphabetically; the previously-stored repo files preserved Grafana's original (non-alphabetic) key order.
2. `jq` emits the literal em-dash character `—`, where the previous repo files used the JSON `—` escape.

Both forms are equivalent JSON. We chose to make the repo match live byte-for-byte, since "live is authoritative" per the standing rule and a future `pull` workflow will write live's form anyway.

### 1b. 5 dashboards that were live-only — now in repo

| UID | Title | Panels |
|---|---|---|
| `ai-obs-app-landing` | AI Observability — Apps | 9 |
| `ai-obs-landing` | AI Observability — Landing Page (Demo Agenda) | 17 (heavy: embedded base64 imagery → ~2 MB) |
| `ai-obs-playbook-neoncart` | AI Observability — NeonCart Playbook | 6 |
| `ai-obs-playbook-supportbot` | AI Observability — Support Bot Playbook | 6 |
| `neoncart-ai-o11y` | NeonCart — AI Observability RCA | 20 |

All five were edited or created in-place via Grafana UI during recent agent runs and never round-tripped to the repo. After this audit, all 17 live dashboards exist at `/workspace/observibelity/dashboards/<uid>.json` with `id = null` and `.version` removed (the conventional storage form).

---

## 2. Other live-vs-repo surfaces

### 2a. ConfigMaps (namespace `observibelity`)

All 5 ConfigMaps carry `app.kubernetes.io/managed-by=Helm` — every one is owned by the chart, no manual edits to capture back:

- `k6-scenarios` (component `traffic`)
- `llm-gateway-config` (component `llm-gateway`)
- `neoncart-branding` (component `neoncart`)
- `otel-collector-config` (component `otel-collector`)
- `supportbot-branding` (component `supportbot`)

The `k6-scenarios.baseline.js` payload (21,785 B) matches the working-tree `/workspace/observibelity/registry/_generated/scenarios/baseline.js` byte-for-byte, but **HEAD was 18,771 B** — the working-tree version had been updated (added `K6_VUS` / `K6_DURATION` env-var overrides + re-weighted `refund-policy-compliance` and `customer-frustration` scenarios from `weight: 2` → `weight: 3`) and deployed to the cluster, but never committed. This PR captures that drift.

### 2b. Secrets (namespace `observibelity`)

All 3 Secrets are Helm-managed:

- `llm-gateway-creds`
- `otel-grafanacloud-creds`
- `postgres-creds`

(Plus 10 `sh.helm.release.v1.*` versioned release secrets — release v22 is current.)

### 2c. Helm release values

`helm get values observibelity -n observibelity` round-tripped against `values-deploy.yaml` shows only formatting differences (Helm normalizes inline maps to expanded form, reorders keys, drops comments). No semantic drift.

### 2d. Alert rules

Helm release has `alerts.enabled: false`, so no rules are provisioned by ObserVIBElity. The 7 alert rules with `obs/neoncart/supportbot` in their title that are live in Grafana Cloud all live under folder `ai-observability` (the legacy demo-pack) and `grafanacloud-ml` — they belong to the older AI o11y demo, not to ObserVIBElity. **No action.**

### 2e. Grafana folders

Two folders exist on this stack:

- `ObserVIBElity` (uid `observibelity`) — the active target of this repo
- `AI Observability` (uid `ai-observability`) — the legacy demo-pack folder

`tools/dashboards-sync.sh` still hardcodes `folderUid: "ai-observability"` in its push payload. **Not changed in this PR** — flagged here as a follow-up because the existing push path is unrelated to today's pull-back work and is best touched alongside the broader sync-tooling cleanup.

---

## 3. What changed in this PR

- Added 5 dashboards live-only → repo (`dashboards/ai-obs-{app-landing,landing,playbook-neoncart,playbook-supportbot}.json` + `neoncart-ai-o11y.json`).
- Re-serialized the existing 12 dashboards through `jq` so their on-disk form matches the live JSON byte-for-byte (no semantic change to any panel, query, variable, or layout).
- Committed `registry/_generated/scenarios/baseline.js` — the working-tree version was already deployed to the cluster but HEAD lagged behind.
- Added `.github/workflows/dashboards-pull-back.yml` — daily 03:00 UTC pull from Grafana Cloud's `observibelity` folder, opens a PR if any dashboard JSON drifts.
- This audit document.

## 4. What was *not* changed (and why)

- `tools/dashboards-sync.sh` still pushes to `ai-observability` folder — fix is unrelated to today's pull-back work, leaving it for a focused sync-tooling PR.
- The legacy `ai-observability` folder content was not pulled — out of scope; this audit is for the `ObserVIBElity` folder per the prompt.
- The pre-existing `git status` modifications to `src/llm-gateway/app/pricing.py` and `templates/llm-gateway/configmap.yaml` were left alone. They are working-tree-only — the **live** `llm-gateway-config` ConfigMap still has the old prices ($1/$5 for haiku), confirming those edits have **not yet** been deployed. They belong to a separate in-flight workstream and intentionally fall outside this "live → repo" sync.

---

## 5. Verification

After this PR is merged, `tools/dashboards-sync.sh pull` (when run with `GRAFANA_TOKEN` + `GRAFANA_URL`) should produce zero `git diff` against `dashboards/`. The new `dashboards-pull-back.yml` workflow runs that same check nightly and opens a PR if drift reappears.
