# ObserVIBElity — Remaining live ↔ repo parity work

> **Status (2026-05-13):** repo is at ~95% parity with the live home-cluster deploy. Three follow-ups remain — total ~90 min if you do all of them. None are deploy-blockers; the demo runs fine without them, but they're the gap between "ours works" and "anyone's works."

---

## Quick links

| What | Where |
|---|---|
| Canonical repo | https://github.com/stephenwagner-grafana/observibelity |
| Live planner | https://claude.wombatwags.com/planner/ai-o11y/ |
| Live Grafana stack | https://stephenwagner.grafana.net |
| Live audit (what's already reconciled) | [`docs/audits/LIVE_REPO_AUDIT.md`](https://github.com/stephenwagner-grafana/observibelity/blob/main/docs/audits/LIVE_REPO_AUDIT.md) |
| Evaluator click-through playbook | [`docs/EVALUATORS.md`](https://github.com/stephenwagner-grafana/observibelity/blob/main/docs/EVALUATORS.md) |
| Persistence rule | every live change must persist to repo — see locked decisions in the planner |

---

## What's already done (2026-05-13)

| PR | Title | Effect |
|---|---|---|
| [#36](https://github.com/stephenwagner-grafana/observibelity/pull/36) | feat(cost): Ollama pricing + dashboard breakdown | Cost dashboard panels populated; pricing config in chart |
| [#37](https://github.com/stephenwagner-grafana/observibelity/pull/37) | fix(dashboards): consistent selectors | 13 broken Loki queries pointed at legacy namespaces — now use `{namespace="observibelity", container=...}` |
| [#38](https://github.com/stephenwagner-grafana/observibelity/pull/38) | chore: live → repo dashboard audit | All 17 live dashboards pulled into repo; nightly pull-back workflow added |
| [#39](https://github.com/stephenwagner-grafana/observibelity/pull/39) | fix(evaluators-sync): correct plugin id + values shape | `evaluators-sync.sh` now targets `grafana-sigil-app` (not the phantom `grafana-aiobservability-app`); `values.yaml` gained `anthropic.apiKey` + `ollama.model` shapes |

After these, every dashboard, configmap, secret, k6 scenario, Postgres seed, and Helm value in the live cluster has a matching artifact in the repo. The remaining gap is on the **live Sigil** side, plus two repo-side bugs.

---

## 1. Fix the 5 schema-failing use-case YAMLs (~15 min)

**Why:** `./tools/usecase-build.sh` currently compiles 17 of 22 use cases. The other 5 fail validation, which means `registry/_generated/evaluators/` contains 32 JSON files instead of the full 44. Today this is silent — the YAMLs themselves are the source of truth and the dashboards/alerts work — but anyone running the compiler sees `failed=5` and has to know it's expected.

**Run this to reproduce:** `./tools/usecase-build.sh` (from repo root).

### 1a. Three cascade-archetype YAMLs need a second scenario

The `cascade` archetype expects ≥2 scenarios per use case (one for the trigger, one for the spiral). Each of these currently has 1:

| File | Current scenario count |
|---|---|
| [`registry/use_cases/email-cascade.yaml`](https://github.com/stephenwagner-grafana/observibelity/blob/main/registry/use_cases/email-cascade.yaml) | 1 |
| [`registry/use_cases/token-spikes.yaml`](https://github.com/stephenwagner-grafana/observibelity/blob/main/registry/use_cases/token-spikes.yaml) | 1 |
| [`registry/use_cases/tool-call-runaway.yaml`](https://github.com/stephenwagner-grafana/observibelity/blob/main/registry/use_cases/tool-call-runaway.yaml) | 1 |

**Fix:** add a second `scenarios:` entry under each. The simplest pattern is to copy the existing scenario and rename it (e.g. `*-stage-2`) so the cascade has a "now it really blows up" follow-up. Look at any compiling cascade YAML for shape — `data-theft-tim.yaml` has the canonical 2-scenario structure.

### 1b. Two single-event-severity YAMLs need a critical evaluator

The `single-event-severity` archetype requires ≥1 evaluator with `severity: critical`. Both injection YAMLs currently top out at `high`:

| File | Evaluators with `severity: critical` |
|---|---|
| [`registry/use_cases/prompt-injection.yaml`](https://github.com/stephenwagner-grafana/observibelity/blob/main/registry/use_cases/prompt-injection.yaml) | 0 |
| [`registry/use_cases/prompt-injection-llm01.yaml`](https://github.com/stephenwagner-grafana/observibelity/blob/main/registry/use_cases/prompt-injection-llm01.yaml) | 0 |

**Fix:** promote one evaluator per file from `severity: high` to `severity: critical`. The `*.detector_flagged` rule is the natural pick (a confirmed detector hit *is* critical).

### Verify

```bash
./tools/usecase-build.sh 2>&1 | tail -3
# expect: usecase-build: compiled=22 failed=0 skipped=0 total=22

ls registry/_generated/evaluators/*.json | wc -l
# expect: 44
```

---

## 2. Fix `dashboards-sync.sh push` folderUid (~5 min)

**Why:** the script hardcodes the legacy `ai-observability` folder as its push target. The audit ([`docs/audits/LIVE_REPO_AUDIT.md`](https://github.com/stephenwagner-grafana/observibelity/blob/main/docs/audits/LIVE_REPO_AUDIT.md) §2e) flagged this. Pull works (the nightly workflow uses `folderUIDs=observibelity`); only manual `./tools/dashboards-sync.sh push` would write to the wrong folder.

**Fix:** [`tools/dashboards-sync.sh:40`](https://github.com/stephenwagner-grafana/observibelity/blob/main/tools/dashboards-sync.sh#L40)

```diff
- payload=$(jq -n --slurpfile d "$f" '{dashboard: $d[0], overwrite: true, message: "synced via observibelity dashboards-sync.sh", folderUid: "ai-observability"}')
+ payload=$(jq -n --slurpfile d "$f" '{dashboard: $d[0], overwrite: true, message: "synced via observibelity dashboards-sync.sh", folderUid: "observibelity"}')
```

Lines 76/79 also reference `tag=ai-observability` — those are the delete/list paths for the *legacy* folder. Decide intent and update or leave; not blocking.

---

## 3. Create the 44 evaluators in Sigil UI (~70 min, one operator)

**Why this matters most:** the 44 evaluator specs in `registry/use_cases/*.yaml` are the canonical source, but **Sigil v0.17.0 doesn't expose evaluator CRUD over REST**. The plugin id is `grafana-sigil-app` and every `/resources/*` path returns 404 (verified during PR #39). Until Grafana ships that API, evaluators only exist in live Sigil after a human clicks through the UI.

**Until you do this, these dashboards silently fall back to LogQL heuristics:**
- `ai-obs-pii` (every panel)
- `ai-obs-compliance` (hiring discrimination, confidential paste, policy circumvention)
- `ai-obs-data-theft` (the Tim story)
- `ai-obs-evals` (refusal rate, toxicity verdict, injection)
- Plus quality columns on `ai-obs-cost`, `ai-obs-ground`, `ai-obs-best-models`

**How:** follow [`docs/EVALUATORS.md`](https://github.com/stephenwagner-grafana/observibelity/blob/main/docs/EVALUATORS.md). The playbook is structured for the keyboard-only path — paste each spec into the Sigil → Evaluators form. Phase A (15 evaluators) is the demo-headline minimum and is ~30 min.

**Open Sigil here:** https://stephenwagner.grafana.net/a/grafana-sigil-app (Hamburger → Apps → AI Observability → Evaluators).

**Verify each as you save:**
```promql
sum by (verdict) (rate(sigil_eval_result_total{evaluator="<name>"}[5m]))
```
Expect non-zero within ~1 minute (assuming traffic exists for the parent use case).

---

## Lower priority / future

- **Compiler emits `_generated/evaluators/null.json`** on at least one path. Source not pinpointed; safe to delete repeatedly until fixed. Likely a missing `name` field or a baseline path that doesn't run through `EvaluatorEmitter`.
- **Sigil REST API watch.** When Grafana ships evaluator CRUD under `/api/plugins/grafana-sigil-app/resources/evaluators`, `./tools/evaluators-sync.sh push` becomes the one-shot replacement for task #3. Periodically re-probe:
  ```bash
  SA_TOKEN=$(kubectl get secret grafana-mcp-token -n claude-code -o jsonpath='{.data.GRAFANA_SERVICE_ACCOUNT_TOKEN}' | base64 -d)
  curl -sS -H "Authorization: Bearer $SA_TOKEN" https://stephenwagner.grafana.net/api/plugins/grafana-sigil-app/resources/evaluators
  ```
  If you stop getting `404 page not found`, the API has landed — wire it up and retire the UI playbook.
- **Image tags are all `:latest`.** Fine for the home cluster; a third-party SE running the demo can't pin to a known-good version. Consider tagging by chart version (`v0.3.0`, `v0.4.0`, …) in `release.yml` so `values.yaml` can default to a real version string.

---

## What's intentionally NOT on this list

- **The 12 stash files / 3 stashes** — all triaged and dropped during PR #39's prep; superseded by merged PRs.
- **Cross-namespace Ollama reference** (`ollama.neoncart.svc.cluster.local`) — the chart shape exists in [`values.yaml`](https://github.com/stephenwagner-grafana/observibelity/blob/main/values.yaml#L73) and the comment now documents in-cluster/LAN/NetworkPolicy options. A fresh deploy on a clean cluster will use whatever the user supplies; the existing home-cluster value is correct for the home cluster.
- **Cloudflared chart additions / `.helmignore` / `docs/INSTALL.md` edits** — your in-progress local work, intentionally left for you to commit on your own branch.

---

*Authored 2026-05-13 by Claude during the live ↔ repo reconciliation pass.*
