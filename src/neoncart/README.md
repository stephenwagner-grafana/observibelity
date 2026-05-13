# neoncart — e-commerce frontend

A FastAPI + Jinja2 + HTMX e-commerce site that serves as the "showcase" surface for the demo. Includes a chatbot widget that calls the `nc-chatbot` specialist.

## Phase 1 contract

- `GET /` — home page (catalog listings from Postgres)
- `GET /products/{id}` — product detail
- `GET /cart` — cart view
- `POST /chat` — chat endpoint → calls nc-chatbot specialist
- `GET /health` — liveness/readiness
- `GET /metrics` — Prometheus metrics

## Branding

All UI text + colors come from a ConfigMap (`values.yaml → neoncart.branding`):
```yaml
neoncart:
  branding:
    name: "NeonCart"
    tagline: "Future-forward retail"
    primaryColor: "#7c3aed"
    logoUrl: ""
```

Jinja templates reference `{{ branding.name }}` etc.

## Telemetry

- Span name convention: `<verb>.<resource>` (e.g., `view.catalog`, `submit.cart`)
- Attributes: `ai_o11y.usecase`, `ai_o11y.persona_id`, `traffic_origin`
- See [planner § Telemetry](https://claude.wombatwags.com/planner/ai-o11y/#telemetry)

## Files (when Phase 1 lands)

```
neoncart/
├── Dockerfile
├── pyproject.toml
├── app/
│   ├── main.py
│   ├── templates/   Jinja2 templates
│   ├── static/      CSS + HTMX
│   └── db.py
└── tests/
```

## Running locally

```
cd src/neoncart
pip install -e .
DATABASE_URL=postgresql+asyncpg://postgres:pass@localhost:5432/observibelity \
LLM_GATEWAY_URL=http://localhost:8001 \
uvicorn app.main:app --reload --port 8000
```

Optional env vars:

- `CHATBOT_URL` (default `http://nc-chatbot/v1/run`) — where `/chat` proxies to.
- `BRANDING_NAME`, `BRANDING_TAGLINE`, `BRANDING_PRIMARY_COLOR`,
  `BRANDING_LOGO_URL` — overrides for what templates render.
- `AI_O11Y_DEFAULT_USECASE` (default `mice-rca`) — value placed on the
  `ai_o11y.usecase` span attribute.

Run the tests:

```
pip install -e ".[dev]"
pytest
```
