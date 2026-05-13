# dashboards/

Grafana dashboards in JSON format. Git-synced to Grafana Cloud via `gcx`
(stub: `tools/dashboards-sync.sh` — Phase 2 wiring).

## Files

- `ai-obs-app-neoncart.json` — Phase 1 centerpiece; NeonCart health
  (request/error/latency stats), top use cases / specialists / tools, gen_ai
  token usage, cost over time, Sigil generation events, and the featured
  **"Show me mice — trace pivot"** panel that surfaces the latest `mice-rca`
  error trace end-to-end.
- (Phase 2 will add 11 more dashboards: tools, cost, latency, errors, evals,
  PII, hallucination, conversation, sub-agent, RAG, prompts.)

## Datasources

Each dashboard uses three datasource variables (resolved at import time):

- `${datasource_prom}` — Prometheus / Mimir
- `${datasource_loki}` — Loki
- `${datasource_tempo}` — Tempo

## Syncing

- `gcx push dashboards/` — push every dashboard to Grafana Cloud (Phase 2).
- For now, manually import in Grafana UI:
  **Dashboards → New → Import → paste JSON** (you will be prompted to bind the
  three datasource variables).
