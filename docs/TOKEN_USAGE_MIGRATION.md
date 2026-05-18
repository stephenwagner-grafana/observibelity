# Token usage metric migration: counter → histogram

**Status**: Prep landed (dashboards archived + queries migrated locally).
**Backend flip**: parked until after the AI-justifies-AI demo on 2026-05-18.
**Owner**: stephenwagner-grafana

## Why this migration exists

The Grafana AI Observability plugin's "Consumption (Tokens)" panel queries
`gen_ai_client_token_usage_count` / `_sum` — the histogram form mandated by
the OpenTelemetry GenAI semantic convention. The llm-gateway today emits
`gen_ai_client_token_usage_total` (counter form), so the plugin panel sits
empty even though the data is being captured.

Switching the gateway's instrument from `create_counter` to `create_histogram`
makes the plugin work out of the box, removes the bespoke `_total` series
from circulation, and aligns us with the semconv.

## Blast radius (verified 2026-05-17)

| Layer | Count | Type | Migration |
| --- | --- | --- | --- |
| Recording sites | 2 `.add()` calls (`src/llm-gateway/app/main.py:1485,1488`) | code | `.add(...)` → `.record(...)` |
| Active dashboards | 20 dashboards × 67 query expressions | PromQL | done (archived to `dashboards/old/`, in-place migrated to `_sum`) |
| Alert YAMLs | 3 expressions across 2 files in `registry/use_cases/` | PromQL | pending |
| Dashboard builder | 6 expressions in `dashboards/_rebuild_ai_obs_welcome.py` | PromQL | pending |
| Sigil pipeline | — | — | unaffected (Sigil owns its own token instrumentation) |
| Specialist / supportbot / neoncart | — | — | unaffected (they emit, don't query) |

## Pre-flight (run before the flip)

```bash
# 1. Confirm nothing else has started querying _total since the inventory
grep -rln "gen_ai_client_token_usage_total\|gen_ai.client.token.usage" \
  src/ registry/ dashboards/ .claude/ \
  | grep -v dashboards/old/ \
  | grep -v dashboards/_patches/

# 2. Snapshot current cardinality so we can compare after
gcx metrics query --datasource grafanacloud-prom \
  'count(group by (gen_ai_token_type, gen_ai_system, ai_o11y_specialist, ai_o11y_usecase, user_id) (gen_ai_client_token_usage_total))'
# Note the number. Histogram will multiply by ~9 buckets.

# 3. Verify no demo dashboard is still on the legacy path
git diff main --name-only dashboards/ | xargs -I{} grep -l "token_usage_total" {} || echo "clean"
```

## The flip (Tuesday, post-demo)

### Step 1 — Gateway code

Three edits in `src/llm-gateway/app/main.py`:

**Edit 1** — instrument type (around line 417):

```python
# was: _meter.create_counter(...)
GEN_AI_TOKEN_USAGE = _meter.create_histogram(
    name="gen_ai.client.token.usage",
    description="Tokens consumed by GenAI requests.",
    unit="{token}",
)
```

**Edit 2** — recording calls (lines 1485, 1488):

```python
# was: GEN_AI_TOKEN_USAGE.add(input_tokens, {...})
GEN_AI_TOKEN_USAGE.record(
    input_tokens, {**gen_ai_attrs, "gen_ai.token.type": "input"}
)
GEN_AI_TOKEN_USAGE.record(
    output_tokens, {**gen_ai_attrs, "gen_ai.token.type": "output"}
)
```

**Edit 3** — bucket boundaries + View (near line 375, alongside
`_DURATION_BUCKETS`):

```python
# Bucket boundaries tuned for LLM token counts. Range covers sub-prompt
# (<100), typical chat (100-1k), long context (1k-10k), and big batch
# completions (10k-100k).
_TOKEN_USAGE_BUCKETS = [
    10, 50, 100, 500, 1000, 5000, 10000, 50000, 100000,
]
```

And add to `duration_views` list (around line 388):

```python
View(
    instrument_name="gen_ai.client.token.usage",
    aggregation=ExplicitBucketHistogramAggregation(_TOKEN_USAGE_BUCKETS),
    # Drop user_id from the histogram to keep cardinality bounded.
    # Per-user spend lives on gen_ai.client.cost.total (counter), which
    # is where it actually matters.
    attribute_keys={"gen_ai.system", "gen_ai.token.type",
                    "ai_o11y.specialist", "ai_o11y.usecase",
                    "service.namespace"},
),
```

### Step 2 — Alert YAMLs

`registry/use_cases/cost-anomaly-per-user.yaml`, line 57:

```yaml
# was: sum_over_time(gen_ai_client_token_usage_total{...}[1h])
sum_over_time(gen_ai_client_token_usage_sum{service_namespace="observibelity",user_id=~".*@.*"}[1h])
```

`registry/use_cases/outlier-users-tim-eric.yaml`, lines 62-63:

```yaml
max by (user_id) (sum_over_time(gen_ai_client_token_usage_sum{service_namespace="observibelity",user_id=~".*@.*"}[1h]))
  / sum(rate(gen_ai_client_token_usage_sum{service_namespace="observibelity"}[1h]) * 3600) > 0.25
```

⚠️ **`user_id` won't exist on the histogram** (we dropped it via the
View). The cost-anomaly + outlier-users alerts need to either pivot to
`gen_ai_client_cost_USD_total` (which keeps `user_id`) or be reworked to
key on `ai_o11y.specialist` / `ai_o11y.usecase`. **Decide before flipping**
— don't deploy alert YAMLs that reference a label that no longer exists.

### Step 3 — Builder script

`dashboards/_rebuild_ai_obs_welcome.py`, lines 57, 455-459, 469:

```python
# Replace every `gen_ai_client_token_usage_total` with
# `gen_ai_client_token_usage_sum`. All existing rate()/increase() calls
# stay semantically equivalent.
```

Then rebuild:

```bash
python3 dashboards/_rebuild_ai_obs_welcome.py
git diff dashboards/ai-obs-welcome.json | head -50
```

### Step 4 — `ai-obs-gateway-signals` (the standalone dashboard)

Has two panels still using `_total` (id 14 "Tokens / min" + id 51 "Token
economics"). Run the same sed/Python replace as the in-place migration:

```bash
python3 -c "
import json
p = 'dashboards/ai-obs-gateway-signals.json'
d = json.load(open(p))
def fix(n):
    if isinstance(n, dict):
        for k,v in n.items():
            if isinstance(v, str): n[k] = v.replace('gen_ai_client_token_usage_total','gen_ai_client_token_usage_sum')
            else: fix(v)
    elif isinstance(n, list):
        for v in n: fix(v)
fix(d)
json.dump(d, open(p,'w'), indent=2, ensure_ascii=False)
"
```

### Step 5 — Deploy gateway + push dashboards

```bash
# 1. Commit code + alert + builder changes
git add src/llm-gateway/app/main.py \
        registry/use_cases/cost-anomaly-per-user.yaml \
        registry/use_cases/outlier-users-tim-eric.yaml \
        dashboards/_rebuild_ai_obs_welcome.py \
        dashboards/ai-obs-welcome.json \
        dashboards/ai-obs-gateway-signals.json
git commit -m "gateway: flip token_usage to histogram per OTel semconv"

# 2. Rebuild + push image (or wait for CI), then restart
kubectl -n observibelity rollout restart deploy/llm-gateway
kubectl -n observibelity rollout status deploy/llm-gateway --timeout=120s

# 3. Verify new metric is flowing
gcx metrics query --datasource grafanacloud-prom \
  'sum(rate(gen_ai_client_token_usage_sum[5m]))'
# Expect a number > 0 within ~30s. If 0, the gateway didn't pick up the
# new code — check the rollout, check the pod logs for OTel init errors.

# 4. Push the migrated dashboards to Grafana (they've been on disk since
# 2026-05-17 — use whichever upload mechanism this repo standardizes on;
# `gcx dashboards update` per file is the simplest).
for f in dashboards/*.json; do
  [[ "$f" == *"/old/"* ]] && continue
  gcx dashboards update "$f"
done

# 5. Regenerate + push alerts
# (depends on your alert provisioning flow — alerts/upload.sh in
# ai-o11y-demo-pack mirrors the same pattern if you don't have one here)
```

### Verification

```bash
# Cardinality check — should be close to (or a bit higher than) the
# pre-flight number. If it's 10x bigger, you didn't drop user_id from
# the View.
gcx metrics query --datasource grafanacloud-prom \
  'count(group by (gen_ai_token_type, gen_ai_system, ai_o11y_specialist, ai_o11y_usecase) (gen_ai_client_token_usage_sum))'

# Plugin panel: open the AI Observability plugin "Consumption" page —
# the Tokens panel should populate within a minute.

# Visual sanity: open ai-obs-cost, ai-obs-app-neoncart, ai-obs-wags-ai
# and confirm token-usage panels show real numbers (no "No data").
```

### Rollback

```bash
# 1. Restore code
git revert <flip-commit-sha>
kubectl -n observibelity rollout restart deploy/llm-gateway

# 2. Restore dashboards (copy archives back into place)
cp dashboards/old/*.json dashboards/
git commit -am "rollback: restore _total dashboards"
for f in dashboards/old/*.json; do
  gcx dashboards update "dashboards/$(basename $f)"
done

# 3. Old _total series persist in Prometheus through the existing
# retention window — no data backfill needed.
```

## Why the alerts need a decision

The two alert rules currently key on `user_id`, which we plan to drop
from the new histogram. Before flipping:

- **Option A** — keep `user_id` on the histogram. Cardinality goes up by
  ~9× × number of distinct users. Acceptable if user count is bounded.
- **Option B** — move the alerts to `gen_ai_client_cost_USD_total` (the
  cost counter, which keeps `user_id`). Per-user *cost* is arguably a
  better signal than per-user *tokens* anyway, since pricing per token
  varies by model.
- **Option C** — re-key the alerts on `ai_o11y.specialist` /
  `ai_o11y.usecase` instead. Loses per-user resolution but the histogram
  becomes cheap.

Pick before the flip. Default leaning: **B** (cost is the truer outlier
signal).

## What the 20 archived dashboards do after the flip

They sit in `dashboards/old/` and continue to work in *git* (their
queries reference `_total`, which Prometheus retains until TTL expires
— a few weeks). They are **not** uploaded to live Grafana after the
flip. To revert a single dashboard, copy `old/<name>.json` over the
in-place file and re-upload via `gcx dashboards update`. The backend
must also be reverted, or the `_total` series will be flatlining at
its last value when the gateway stopped emitting.
