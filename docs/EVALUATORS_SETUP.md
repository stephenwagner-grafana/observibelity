# Evaluator Setup Guide

> **Operational runbook** for getting ObserVIBElity evaluators live in Grafana
> Cloud. Complements `docs/EVALUATORS.md` (the per-evaluator catalog with all 44
> specs). Read this first if you're standing up evaluators for the first time.

## TL;DR — the 30-minute happy path

```bash
# Prereqs: AI Observability plugin installed in your stack; gateway emitting Sigil
# generations (SIGIL_GENERATION_EXPORT_ENDPOINT set in values-deploy.yaml — already
# wired in the chart since v0.3.0).

# 1. Mint a stack-level service-account token (see Step 3) and export it
export GRAFANA_URL=https://stephenwagner.grafana.net
export GRAFANA_TOKEN=glsa_xxxxxxxxxxxxxxxxxxxxxxxxxxxx_xxxxxxxx

# 2. Compile the 44 evaluator specs from registry/use_cases/*.yaml
make build-usecases

# 3. Push them to the AI Observability plugin
make evaluators-push

# 4. Verify Sigil is receiving evaluations
./tools/evaluators-sync.sh status
```

If `evaluators-push` works, jump to **Step 7 — Verify each evaluator is
firing**. If it returns `Sigil v0.17.0 does not yet expose evaluator CRUD`,
fall back to the manual UI flow in **`docs/EVALUATORS.md`**.

---

## Current vs target state

| Where evaluations could happen | Today | Target |
|---|---|---|
| Specialist pods (`sb-*`, `nc-*`) | **Nothing.** Pods just emit `sigil generation:` JSON with the prompt/completion + `ai_o11y.*` attrs. Specialists explicitly *do not* score — comments in `sb-security-handler/specialist.py` say "the evaluator will flag it". | Unchanged. Keep pods dumb. |
| `llm-gateway` pod | Emits one Sigil generation record per `/v1/complete` via the `sigil_sdk` gRPC client (`SIGIL_GENERATION_EXPORT_ENDPOINT`). Already wired in #34. | Unchanged. |
| `registry/use_cases/*.yaml` evaluator blocks | 42 specs declared (20 rule, 13 regex, 9 llm-judge). Several still reference `source: loki` with old AI o11y demo stream selectors. | All 42 + 3 baselines = 44 specs. Sigil-native sources only. |
| `registry/_generated/evaluators/*.json` | 32 compiled — most reference stale Loki streams. Regenerated on `make build-usecases`. | 44 compiled. |
| `tools/evaluators-sync.sh push` | Implemented. POSTs to `/api/plugins/grafana-aiobservability-app/resources/evaluators`. **Returns 404 on Sigil < v0.18** — the plugin's evaluator CRUD endpoint isn't shipped everywhere yet. | When plugin supports CRUD: `make evaluators-push` is one command. Until then: manual UI flow per `docs/EVALUATORS.md`. |
| Grafana Cloud — AI Observability plugin | Plugin **installed**. **Zero evaluators configured.** | 3 baseline + 41 per-use-case = 44 live. |
| Grafana Cloud — alert rules | Wired in chart via `tools/alerts-sync.sh`. **Some alerts reference evaluators that don't exist yet** → they read 0 and never fire. | All alerts paired with a live evaluator. |

**Key invariant:** the pods don't change. All the work is in
`registry/use_cases/*.yaml` + Grafana Cloud.

---

## Before you start (prereqs)

You need:

1. **A Grafana Cloud stack** with the AI Observability plugin enabled.
   - Verify at `https://<stack>.grafana.net/a/grafana-aiobservability-app` — if
     you see the plugin landing page, you're good.
   - If 404: install via *Apps → Connections → Add new connection → AI
     Observability*.

2. **A stack-level service-account token** (NOT the cloud-level `glc_…` token
   that's in `.env` already). See **Step 3** to mint one.

3. **The ObserVIBElity stack already deployed**, with `k6-traffic` driving
   traffic so evaluators have data to score against. Check with:
   ```bash
   kubectl get pods -n observibelity -l app.kubernetes.io/component=traffic
   ```

4. **`jq`** + **`curl`** on the operator's machine (the sync script needs
   both).

---

## Step 1 — Verify Sigil ingest is alive

Before configuring evaluators, confirm the gateway is sending generations to
Sigil. Without this, evaluators have nothing to score.

```bash
# Tail the gateway and look for sigil generation lines
GW=$(kubectl get pod -n observibelity -l app.kubernetes.io/component=llm-gateway \
  -o jsonpath='{.items[0].metadata.name}')
kubectl logs -n observibelity "$GW" --tail=20 | grep "sigil generation"
```

Expected output: JSON lines containing `gen_ai.system`, `gen_ai.request.model`,
`ai_o11y.usecase`, `ai_o11y.persona_id`, `ai_o11y.specialist`. If you see those
fields, ingest is working.

**Cross-check from Grafana:** *Explore* → AI Observability → *Conversations*.
You should see ~7–10 rows per second.

If you see nothing in Grafana but the pod logs the line: the
`SIGIL_GENERATION_EXPORT_ENDPOINT` env var probably isn't set or the SDK is
hitting an invalid endpoint. Check the chart values:

```bash
helm get values -n observibelity observibelity | grep -A 3 sigil:
```

Should show `enabled: true` and a non-empty `endpoint`.

---

## Step 2 — Install the AI Observability plugin

(Skip if `https://<stack>.grafana.net/a/grafana-aiobservability-app` already
loads a landing page.)

1. Open `https://<stack>.grafana.net`.
2. Hamburger → **Connections** → **Add new connection**.
3. Search for **AI Observability**.
4. Click **Install**, then **Enable** on the plugin's detail page.
5. The plugin appears under Hamburger → **Apps** → **AI Observability**.

There's no per-tenant config to fill in — Sigil ingest is keyed on the OTLP
auth token the gateway already uses (`GRAFANA_CLOUD_OTLP_ENDPOINT`).

---

## Step 3 — Mint a stack-level service-account token

This is the single most common blocker. The `glc_…` token in `.env`
(`GRAFANA_CLOUD_API_TOKEN`) is a **cloud-level** token — it can manage stacks
but cannot reach stack-internal APIs like `/api/dashboards/db` or the AI
Observability plugin's `/resources/evaluators`. You need a separate
**stack-level service-account token** (token format: `glsa_…`).

### One-time setup

1. In the stack: hamburger → **Administration** → **Users and access** →
   **Service accounts**.
2. **Add service account**:
   - Name: `observibelity-sync`
   - Role: **Editor** (Editor can manage dashboards + plugin resources; Admin
     is overkill here)
3. After creation: **Add service account token**.
   - Name: `observibelity-sync-token`
   - Expiration: **No expiration** for dev; **90 days** for prod
4. **Copy the token immediately** — Grafana shows it once. It starts with
   `glsa_`.

### Add it to your environments

```bash
# Local .env (gitignored)
echo "GRAFANA_TOKEN=glsa_xxxxxxxxxxxxxxxxxxxxxxxxxxxx_xxxxxxxx" >> .env
echo "GRAFANA_URL=https://stephenwagner.grafana.net" >> .env

# GitHub Actions (for sync.yml workflow)
gh secret set GRAFANA_TOKEN -b "glsa_xxxxxxxxxxxxxxxxxxxxxxxxxxxx_xxxxxxxx" \
  --repo stephenwagner-grafana/observibelity
gh secret set GRAFANA_URL -b "https://stephenwagner.grafana.net" \
  --repo stephenwagner-grafana/observibelity
```

> The existing `GRAFANA_CLOUD_API_TOKEN` secret keeps working for cloud-level
> operations (creating stacks, etc.) — don't replace it. The two coexist.

### Verify

```bash
source .env
curl -sS -H "Authorization: Bearer $GRAFANA_TOKEN" \
  "$GRAFANA_URL/api/access-control/user/permissions" | jq 'keys | length'
# Should print a number, not the "Invalid API key" error.
```

---

## Step 4 — Compile the evaluator specs

```bash
make build-usecases
```

What this does:

1. Loads every `registry/use_cases/*.yaml`.
2. Runs them through `tools/usecase_build/compiler.py`.
3. Writes per-evaluator JSON to `registry/_generated/evaluators/<usecase>.<evaluator>.json`.
4. Also emits `registry/_generated/{dashboards,alerts,scenarios,slos}/` (other artefacts).

Verify the output:

```bash
ls registry/_generated/evaluators/ | wc -l   # expect ~44
jq . registry/_generated/evaluators/data-theft-tim.data_theft_tim.cc_paste_detected.json
```

Each JSON should have: `name`, `kind`, `severity`, `expression`, `tags`,
`params`.

### Known compile gotchas

| Symptom | Cause | Fix |
|---|---|---|
| `"params": {"source": "loki", "stream": "{namespace=\"supportbot\",...}"}` | The YAML uses a Loki source pointing at the **old** demo namespace. | Rewrite the YAML eval's `params` to `{"source": "prompt"}` or `{"source": "response"}` or `{"source": "attribute", "attribute": "ai_o11y.specialist"}`. Sigil scores on the generation text + attrs, not on pod logs. |
| `null.json` appears in output dir | A use case YAML is missing `name:` or the compiler hit a None branch. | Run `make test-usecases` to see which YAML is malformed. |
| Compiled file has retired `support_copilot_*` references | A YAML evaluator spec still uses old AI o11y demo metric names. | Update the YAML — the compiler doesn't rewrite metric names, only structure. |

---

## Step 5 — Push to Grafana Cloud

### Path A — automated (preferred)

```bash
make evaluators-push
```

Behind the scenes: `./tools/evaluators-sync.sh push` POSTs every JSON to
`$GRAFANA_URL/api/plugins/grafana-aiobservability-app/resources/evaluators`.

Expected output:
```
[push] Pushing evaluators to https://stephenwagner.grafana.net
  push data_theft_tim.cc_paste_detected
    ✓ data_theft_tim.cc_paste_detected
  push data_theft_tim.exfil_score_threshold
    ✓ data_theft_tim.exfil_score_threshold
  ...
[ok] Summary: 44 pushed, 0 failed
```

### Path B — manual UI (fallback when Path A returns 404)

The AI Observability plugin's evaluator CRUD endpoint isn't shipped in every
plugin version. If `evaluators-push` fails with 404 or "Sigil v0.17.0 does not
yet expose evaluator CRUD", drop to the UI:

1. Open `https://<stack>.grafana.net/a/grafana-aiobservability-app/evaluators`.
2. Click **+ New evaluator** (top-right).
3. Walk through `docs/EVALUATORS.md` — it has the exact field values for all 44
   evaluators with copy-pasteable specs.
4. Recommended order from `EVALUATORS.md`:
   - **Phase A** (30 min) — 3 baselines + 12 centerpieces. Demo headlines work.
   - **Phase B** (45 min) — high-value singleton + cascade evaluators.
   - **Phase C** (30 min) — rubric + llm-judge.
   - **Phase D** (30 min) — leaderboard long-tail.

### Path C — GitHub Actions

Once `GRAFANA_TOKEN` is set as a repo secret, the workflow
`.github/workflows/sync.yml` runs on every push to `main` that touches
`registry/_generated/**` (among other paths). It calls
`./tools/evaluators-sync.sh push` automatically. No manual run needed
post-merge.

---

## Step 6 — Verify each evaluator is firing

For each pushed evaluator, run within ~1 minute:

```promql
sum by (verdict) (rate(sigil_eval_result_total{evaluator="<name>"}[5m]))
```

Expectations:
- A non-zero result series.
- Both `pass` and `fail` verdicts unless the use case is purely critical (e.g.
  `data_theft_tim.cc_paste_detected` is fail-only).
- Pass/fail ratio in the rough range the planner expects (see `EVALUATORS.md`
  *Skip impact* column for sanity bounds).

### Batch verify

```bash
python3 - <<'EOF'
import json, glob, os, subprocess
NAMES = []
for f in glob.glob('registry/_generated/evaluators/*.json'):
    name = json.load(open(f)).get('name')
    if name: NAMES.append(name)
print(f"Checking {len(NAMES)} evaluators…")
url = os.environ['GRAFANA_URL'] + '/api/datasources/proxy/uid/grafanacloud-prom/api/v1/query'
tok = os.environ['GRAFANA_TOKEN']
missing = []
for n in NAMES:
    q = f'sum(rate(sigil_eval_result_total{{evaluator="{n}"}}[5m]))'
    r = subprocess.check_output(['curl','-sS','-H',f'Authorization: Bearer {tok}',
                                 '--data-urlencode',f'query={q}', url]).decode()
    if '"result":[]' in r or '"result":[{"metric":{},"value":[' not in r:
        missing.append(n)
print(f"  Live: {len(NAMES)-len(missing)} / {len(NAMES)}")
if missing:
    print("  Not yet firing:")
    for m in missing: print(f"    - {m}")
EOF
```

If an evaluator never fires after 5 minutes:

- Is the parent use case driving traffic? (`kubectl logs -n observibelity
  k6-traffic-* --tail 30 | grep "<usecase>"`)
- Is the evaluator's `source:` field referencing data Sigil actually sees?
  Sigil sees `prompt`, `response`, `attribute`, plus `loki` if the plugin
  version supports it. `loki` sources are deprecated — switch to `prompt` /
  `response` / `attribute`.
- Is sampling > 0%? Default is 100% for rule/regex; rubric/llm-judge defaults
  to 10% — check `EVALUATORS.md` *Cost & sampling guardrails* section.

---

## Step 7 — Wire alerts to fired evaluators

Each evaluator has an alert paired with it in the use-case YAML's `alerts:`
block. The pairing pattern: alert PromQL queries `sigil_eval_result_total{evaluator="<name>",verdict="fail"}`.

Push alerts to Grafana Cloud:

```bash
make alerts-push     # or: ./tools/alerts-sync.sh push
```

Verify in *Alerting → Alert rules* that each one is **Normal** (not
**NoData**). A `NoData` state usually means the paired evaluator is missing.

Routing destinations are defined in the use-case YAML's `alerts[].route`:

| Route | Who gets paged |
|---|---|
| `security@acme.local` | data exfil, PII echo, sensitive-data, prompt-injection |
| `safety@acme.local` | toxicity (baseline + use-case) |
| `hr-compliance@acme.local` | hiring discrimination (P0) |
| `compliance@acme.local` | policy circumvention |
| `finance-ops@acme.local` | cost anomalies |
| `oncall@acme.local` | tool runaway, cascade, hallucination, refund policy, mice-rca |
| `brand@acme.local` | brand voice drift |
| `customer-success@acme.local` | customer frustration |
| `quality@acme.local` | refusal rate |

Edit `registry/use_cases/*.yaml` alerts → route fields to retarget.

---

## The end-to-end pipeline

```
┌─────────────────────────────┐
│ registry/use_cases/*.yaml   │  ← humans edit this
│   (22 files, eval blocks)   │
└──────────────┬──────────────┘
               │ make build-usecases
               ▼
┌─────────────────────────────┐
│ registry/_generated/        │  ← generated, gitignored except for review
│   evaluators/*.json (44)    │
│   dashboards/*.json         │
│   alerts/*.yaml             │
│   scenarios/*.js (k6)       │
│   slos/*.yaml               │
└──────────────┬──────────────┘
               │ make evaluators-push  (or sync.yml on push)
               ▼
┌─────────────────────────────┐
│ Grafana Cloud               │
│   AI Observability plugin   │  ← scoring runs here
│   Alerting                  │
│   Dashboards                │
└──────────────┬──────────────┘
               │ pages
               ▼
   security@ / safety@ / oncall@ …
```

The 8 dashboard annotation queries I fixed in PR #37
(`cc_paste`, `hiring_discrimination_risk`, `brand_drift`, `evaluator fail
hallucination`, etc.) will start lighting up automatically once the paired
evaluators are live in Grafana Cloud and emitting `sigil_eval_result_total`
events.

---

## What's in the pods today — and what to remove

**Nothing to remove in src/**. The specialists (`sb-router`,
`sb-security-handler`, `sb-hiring-helper`, `nc-fraud-detector`, etc.) do not
contain scoring logic. They have comments that *reference* evaluators ("the
evaluator will flag it") but no detection code runs in-pod. Confirmed via:

```bash
grep -rnE 'def evaluate|score\s*=\s*[0-9]|EXFIL_|judge\(' src/
# (returns nothing — all eval logic lives in Sigil, by design)
```

The chart is also clean: the planner explicitly removed
`sb-csat-judge`, `sb-groundedness-judge`, `sb-access-leakage-judge`,
`sb-safety-judge`, `sb-tone-checker`, `nc-review-moderator`, `sb-pii-detector`
when ObserVIBElity moved to "Sigil-only" architecture.

**The only cleanup left is in `registry/use_cases/*.yaml`:** any evaluator
spec with `params.source: loki` should switch to `prompt` / `response` /
`attribute`. Audit:

```bash
grep -B 1 -A 2 'source:\s*loki' registry/use_cases/*.yaml
```

For each match: rewrite the regex pattern to match against the actual prompt
or completion text instead of a log line shape. E.g. for
`data_theft_tim.cc_paste_detected`:

```yaml
# Before
- name: data_theft_tim.cc_paste_detected
  kind: regex
  spec: |
    cc_paste\s+employee=\S+\s+last4=\d{4}
  params:
    source: loki
    stream: '{namespace="supportbot",app_kubernetes_io_name="acme-bot-api"}'

# After
- name: data_theft_tim.cc_paste_detected
  kind: regex
  spec: |
    \b(?:\d[ -]*?){13,16}\b
  params:
    source: prompt
    require_attribute: ai_o11y.persona_id   # tag so the leaderboard groups by user
```

---

## Cost guardrails

Even at full coverage the daily cost is modest, but the rubric/llm-judge
evaluators dominate. Set in *Sigil → Settings → Cost Controls*:

| Setting | Value | Why |
|---|---|---|
| `sigil.judge.max_per_minute` | 100 | Hard cap on judge calls/minute. |
| `sigil.judge.daily_budget_usd` | 15 | Stops the whole judge pool at $15. |
| `sigil.judge.alert_at_pct` | 80 | Pages finance-ops@ at 80% of budget. |

Per-evaluator sampling defaults (override on each evaluator in the UI):

| Kind | Default sampling |
|---|---:|
| `rule` | 100% (free) |
| `regex` | 100% (free) |
| `rubric` | 10% (~$0.0001/eval) |
| `llm-judge` (info severity) | 25% |
| `llm-judge` (critical severity) | 100% (e.g. `toxicity.hateful_output`) |

Full per-evaluator cost table lives in `docs/EVALUATORS.md` → *Cost & sampling
guardrails*.

---

## Troubleshooting

### "Invalid API key" from `evaluators-push`
You're using the cloud-level `glc_…` token. Mint a **stack-level** `glsa_…`
token per Step 3.

### `Summary: 0 pushed, 44 failed (404)`
The AI Observability plugin's evaluator CRUD endpoint isn't shipped in this
plugin version. Switch to manual UI flow per Step 5 Path B. Watch for plugin
v0.18+ which is expected to expose `/resources/evaluators` POST.

### Evaluator pushes succeed but never fire
- Confirm parent use case has traffic: `kubectl logs -n observibelity
  k6-traffic-* --tail=20 | grep <usecase>`.
- Confirm the evaluator's `source:` resolves to data Sigil sees. Old `loki`
  sources are deprecated — rewrite to `prompt`/`response`/`attribute`.
- Check sampling rate in the UI.
- Tail Sigil: *Explore → grafanacloud-logs → `{job="sigil"}` |~ "evaluator
  <name>"*.

### Alerts in `NoData` state
The paired evaluator isn't pushed yet, or its name in the alert PromQL doesn't
match the evaluator's `name` in Grafana Cloud. Compare:

```bash
diff <(jq -r '.name' registry/_generated/evaluators/*.json | sort) \
     <(yq '.alerts[].condition' registry/use_cases/*.yaml | \
       grep -oE 'evaluator="[^"]+"' | tr -d '"' | sort -u)
```

### `make build-usecases` produces `null.json`
A YAML evaluator spec is missing `name:`. Run `make test-usecases` to find
the malformed file; fix the YAML.

### Sigil ingest works in the gateway but Grafana shows no conversations
The plugin can be installed but receive data via a different OTLP token than
the one in `.env`. Sanity-check by tailing OTel exporter logs:

```bash
kubectl logs -n observibelity deploy/otel-collector --tail=50 | grep -i sigil
```

---

## Cross-references

| Doc | What it covers |
|---|---|
| **This file** (`EVALUATORS_SETUP.md`) | Operational setup, auth, pipeline, verify, troubleshoot. |
| `docs/EVALUATORS.md` | Per-evaluator catalog: all 44 specs, manual UI walkthrough, cost-per-evaluator. |
| `docs/ARCHITECTURE.md` | Full system architecture; where evaluators sit in the data flow. |
| `docs/INSTALL.md` | First-time install of the ObserVIBElity stack. |
| `docs/PROVIDERS.md` | LLM provider config (Claude/Ollama) — independent of evaluators. |
| `docs/GITOPS.md` | Argo CD / sync workflow patterns; includes the `sync.yml` flow. |
| `registry/use_cases/*.yaml` | Source of truth for evaluator specs. |
| `tools/evaluators-sync.sh` | The push/pull/diff/status script wrapping the plugin REST API. |
| `tools/usecase_build/` | Python compiler that produces `registry/_generated/`. |

---

## Quick-reference checklist

Print and tick.

- [ ] AI Observability plugin installed in the stack
- [ ] Sigil ingest verified — generations visible in Conversations view
- [ ] Stack-level service-account token minted (`glsa_…`)
- [ ] `GRAFANA_URL` + `GRAFANA_TOKEN` exported (local) and set (GH secrets)
- [ ] `make build-usecases` produces ~44 JSON files in `registry/_generated/evaluators/`
- [ ] All YAML evaluator specs use `source: prompt|response|attribute` (no `loki`)
- [ ] `make evaluators-push` succeeds (or manual UI flow per Phase A → D in `EVALUATORS.md`)
- [ ] Verification PromQL returns non-zero for at least the 3 baselines + 12 centerpieces
- [ ] `make alerts-push` succeeds; alerts in *Normal* state, not *NoData*
- [ ] Routing destinations match the on-call team's channels
- [ ] Cost controls set in Sigil → Settings (max_per_minute, daily_budget_usd)

*Last reviewed: 2026-05-13. Source: `registry/use_cases/*.yaml`, `tools/evaluators-sync.sh`, `Makefile`.*
