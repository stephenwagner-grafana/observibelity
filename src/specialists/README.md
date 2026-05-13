# specialists/ — sub-agent pods

Each specialist is its own FastAPI pod. Specialists:
- Receive requests from an app (or from another specialist for orchestration)
- Call the `llm-gateway` for LLM completion (with a tool allowlist)
- Call tools from `src/tools/` to do actual work
- Return structured responses

## Phase 1 specialists

| name | app | role | tools allowed |
|---|---|---|---|
| nc-chatbot | neoncart | chat-driven shopping assistant | search_products, get_product, get_order_history, place_order |
| nc-fraud-detector | neoncart | per-order fraud scoring | get_order_history, geo_lookup |
| nc-fulfillment-orchestrator | neoncart | order fulfillment workflow | get_inventory, place_order, geo_lookup |

## Phase 2 adds 21 more specialists
- 10 more NeonCart specialists (gift-finder, recommender, cart-optimizer, etc.)
- 11 Support Bot specialists (sb-router, sb-policy-finder, sb-kb-search, etc.)

## Specialist contract

Every specialist exposes:
- `POST /v1/run` — main entry, accepts a request, returns a response
- `GET /health` — readiness
- `GET /metrics` — Prometheus

The `Specialist` base class (Phase 1) handles:
- Pydantic Args/Result validation
- OTel span creation with `ai_o11y.specialist` attr
- llm-gateway client
- Tool registry lookup (which tools is this specialist allowed to call?)
- Sigil event emission

## Adding a new specialist

1. Create `src/specialists/<name>/` with main.py, Dockerfile, pyproject.toml, tests/
2. Subclass `Specialist` base
3. Declare `tool_allowlist` in `registry/specialists.yaml`
4. Build image: `make images SPECIALIST=<name>`
5. Add to `registry/specialists.yaml` to make it discoverable
6. Deploy: `make dev` (the chart auto-discovers from registry)

See [Live planner § 02 Specialists](https://claude.wombatwags.com/planner/ai-o11y/#specialists).
