# Topology

This page is the **system map** for ObserVIBElity. If you want to know what's
running, where it sits, what talks to what, and where the telemetry goes —
this is the page.

## System topology

```
        ┌───────────────────────────────────────────────────────────┐
        │  User browser                                             │
        └──────────────────────────┬────────────────────────────────┘
                                   │
                          ┌────────▼─────────┐
                          │  Ingress         │
                          └────────┬─────────┘
                                   │
              ┌────────────────────┼────────────────────┐
              │                                         │
       ┌──────▼──────┐                          ┌───────▼──────┐
       │ NeonCart    │                          │ Support Bot  │   (Phase 2)
       │ (FastAPI +  │                          │ (FastAPI +   │
       │  Jinja +    │                          │  Jinja +     │
       │  HTMX)      │                          │  HTMX)       │
       └──────┬──────┘                          └───────┬──────┘
              │                                         │
              ├──────► nc-* specialists                 ├──► sb-* specialists
              │        (~13 pods)                       │     (~11 pods)
              │                                         │
              └──────┬──────────────────────────────────┘
                     │
              ┌──────▼──────┐                  ┌──────────────┐
              │ Tools       │◄────────────────►│ Postgres     │
              │ (~21 pods,  │                  │ (28 tables,  │
              │  shared)    │                  │  app data +  │
              └──────┬──────┘                  │  KBs only)   │
                     │                         └──────────────┘
              ┌──────▼──────┐
              │ llm-gateway │
              │ (1 pod)     │
              └──┬────────┬─┘
                 │        │
        ┌────────▼┐    ┌──▼─────────┐
        │ Claude  │    │ Ollama     │
        │ API     │    │ (5090 LAN) │
        └─────────┘    └────────────┘

        OTel everywhere ──► OTel collector ──► Grafana Cloud
                                                  ├── Mimir (metrics)
                                                  ├── Loki (logs)
                                                  ├── Tempo (traces)
                                                  ├── Pyroscope (profiles)
                                                  └── Sigil (generations + evals)
```

## Component reference

Every workload that lands in the `observibelity` namespace, by phase.

| component | type | replicas | phase | notes |
|---|---|---|---|---|
| `postgres` | StatefulSet | 1 | P1 | Single PVC; Alembic migrations applied via init container |
| `postgres-seed` | Job | 1 | P1 | Runs once; loads catalog + 150 personas from CSV |
| `llm-gateway` | Deployment | 1 | P1 | Anthropic provider only in P1; Ollama provider added in P2 |
| `neoncart` | Deployment | 1 | P1 | FastAPI + Jinja + HTMX frontend with embedded chatbot widget |
| `supportbot` | Deployment | 1 | P2 | FastAPI + Jinja + HTMX frontend |
| `nc-chatbot` | Deployment | 1 | P1 | Chat specialist — entrypoint for NeonCart conversations |
| `nc-fraud-detector` | Deployment | 1 | P1 | Risk scoring specialist |
| `nc-fulfillment-orchestrator` | Deployment | 1 | P1 | Order placement + inventory specialist |
| `nc-product-finder` | Deployment | 1 | P2 | Product discovery + recommendations |
| `nc-checkout-helper` | Deployment | 1 | P2 | Cart-to-purchase flow |
| `nc-returns-agent` | Deployment | 1 | P2 | RMA + refund flow |
| `nc-shipping-tracker` | Deployment | 1 | P2 | Shipment status |
| `nc-account-manager` | Deployment | 1 | P2 | Account settings + profile |
| `nc-loyalty-agent` | Deployment | 1 | P2 | Rewards + points |
| `nc-pricing-agent` | Deployment | 1 | P2 | Discounts + coupons |
| `nc-recommendation-engine` | Deployment | 1 | P2 | Personalized recs |
| `nc-inventory-watcher` | Deployment | 1 | P2 | Stock + restock |
| `nc-judge` | Deployment | 1 | P2 | Evaluator-side LLM-as-judge |
| `nc-summarizer` | Deployment | 1 | P2 | Conversation summarization |
| `sb-policy-finder` | Deployment | 1 | P2 | Policy KB lookup |
| `sb-account-lookup` | Deployment | 1 | P2 | Customer record lookup |
| `sb-ticket-classifier` | Deployment | 1 | P2 | Triage routing |
| `sb-escalation-router` | Deployment | 1 | P2 | Tier-2 handoff |
| `sb-billing-resolver` | Deployment | 1 | P2 | Invoice + refund |
| `sb-tech-troubleshooter` | Deployment | 1 | P2 | Diagnostic flows |
| `sb-knowledge-base` | Deployment | 1 | P2 | Article search |
| `sb-feedback-collector` | Deployment | 1 | P2 | NPS + CSAT |
| `sb-summary-writer` | Deployment | 1 | P2 | Case notes |
| `sb-judge` | Deployment | 1 | P2 | LLM-as-judge for SB |
| `sb-orchestrator` | Deployment | 1 | P2 | Top-level SB flow |
| `tool-search-products` | Deployment | 1 | P1 | Catalog search |
| `tool-get-product` | Deployment | 1 | P1 | Single SKU lookup |
| `tool-get-order-history` | Deployment | 1 | P1 | Per-customer order list |
| `tool-geo-lookup` | Deployment | 1 | P1 | IP → region for fraud signals |
| `tool-get-inventory` | Deployment | 1 | P1 | Stock-on-hand |
| `tool-place-order` | Deployment | 1 | P1 | Checkout-side transactional |
| `tool-kb-search` | Deployment | 1 | P2 | Knowledge base retrieval |
| `tool-policy-lookup` | Deployment | 1 | P2 | Policy text retrieval |
| `tool-account-lookup` | Deployment | 1 | P2 | Customer record |
| `tool-ticket-create` | Deployment | 1 | P2 | Help-desk write |
| `tool-ticket-update` | Deployment | 1 | P2 | Help-desk state |
| `tool-refund-process` | Deployment | 1 | P2 | Refund execution |
| `tool-shipment-track` | Deployment | 1 | P2 | Carrier API |
| `tool-payment-charge` | Deployment | 1 | P2 | Payment gateway |
| `tool-coupon-apply` | Deployment | 1 | P2 | Discount logic |
| `tool-loyalty-points` | Deployment | 1 | P2 | Points ledger |
| `tool-recommend-items` | Deployment | 1 | P2 | Per-customer recs |
| `tool-summarize-conversation` | Deployment | 1 | P2 | Transcript → summary |
| `tool-classify-intent` | Deployment | 1 | P2 | Intent labeling |
| `tool-detect-pii` | Deployment | 1 | P2 | PII redaction |
| `tool-translate` | Deployment | 1 | P2 | Multi-locale |
| `tool-feedback-record` | Deployment | 1 | P2 | NPS write |
| `otel-collector` | DaemonSet | n | P1 | One per node; ships OTLP → Grafana Cloud |
| `k6` | Job (cron-triggered) | n | P2 | Scenario-driven continuous traffic |

Phase tags: **P0** = scaffold-only (no workload yet), **P1** = mice-rca
centerpiece deploy, **P2** = full set.

## Storage layout

| PVC | bound to | size | StorageClass | phase |
|---|---|---|---|---|
| `postgres-data` | `postgres-0` pod | 1 GiB (default) | cluster default (`local-path` / `gp2` / `standard-rwo` / `default` depending on target) | P1 |

Phase 0 ships **no** PVCs — everything is template-only. Phase 1 introduces the
single `postgres-data` PVC. Phase 2 may grow this if Postgres footprint exceeds
1 GiB after KB seeding.

## Network flow

1. HTTP request hits the **ingress controller** (Traefik on k3s/k3d, NGINX/ALB
   on cloud).
2. Ingress routes by `Host` header:
   - `neoncart.*` → NeonCart frontend Service
   - `supportbot.*` → Support Bot frontend Service (Phase 2)
3. Frontend pod renders HTML; embeds the **chatbot widget** (HTMX). Widget
   POSTs to the frontend, which forwards to a specialist.
4. Specialist (sub-agent pod) receives the user message, plans tool calls
   against its allowlist, and calls **tools**.
5. **Tools** are shared microservice pods. They:
   - Read/write **Postgres** for app data + KB content.
   - Call out via **llm-gateway** when they need LLM reasoning (rare — most
     tools are pure data plane).
6. **llm-gateway** is the single egress point to **Claude API** (Anthropic)
   or **Ollama** (Phase 2, LAN at `5090`).
7. The response flows back through the same chain.
8. **Telemetry** is emitted by every pod:
   - OTel SDK auto-instruments HTTP server, HTTP client, SQLAlchemy, and the
     GenAI provider calls.
   - All signals are pushed via OTLP to the in-cluster `otel-collector`.
   - The collector batches, adds auth headers (instance ID + token), and
     pushes to the appropriate **Grafana Cloud** ingest endpoint.

## Telemetry sinks

All signals land in **Grafana Cloud**. Endpoints per signal:

| signal | sink | Grafana Cloud endpoint |
|---|---|---|
| metrics | Mimir | `https://prometheus-<region>.grafana.net/api/prom/push` |
| logs | Loki | `https://logs-<region>.grafana.net/loki/api/v1/push` |
| traces | Tempo | `https://tempo-<region>.grafana.net:443` (OTLP gRPC) |
| profiles | Pyroscope | `https://profiles-<region>.grafana.net` |
| GenAI events | Sigil | `https://genai-<region>.grafana.net/v1/events` |
| Frontend RUM | Faro | `https://faro-collector-<region>.grafana.net/collect/<app-id>` |

The wizard collects your region/stack and computes these for you; you don't
need to hand-type them.

## Port summary

| port | service | exposed via |
|---|---|---|
| 80 | `neoncart` | ClusterIP Service + ingress |
| 80 | `supportbot` (P2) | ClusterIP Service + ingress |
| 5432 | `postgres` | ClusterIP Service (intra-cluster only) |
| 8000 | `llm-gateway` | ClusterIP Service (intra-cluster only) |
| 8000 | `nc-*` and `sb-*` specialists | ClusterIP Service (intra-cluster only) |
| 8000 | `tool-*` pods | ClusterIP Service (intra-cluster only) |
| 4317 | `otel-collector` (OTLP gRPC) | ClusterIP Service |
| 4318 | `otel-collector` (OTLP HTTP) | ClusterIP Service |
| 13133 | `otel-collector` health | ClusterIP Service |
| 5090 | Ollama (out-of-cluster) | LAN host:port |

---

*Full system spec lives at https://claude.wombatwags.com/planner/ai-o11y/ (auth-gated).*
