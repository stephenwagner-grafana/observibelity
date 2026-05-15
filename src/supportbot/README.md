# Support Bot ("Ask Acme")

Internal HR/IT support assistant — Phase 2 frontend for the ObserVIBElity demo.

Contract (`app/main.py`):

```
GET  /                     -> landing page + featured KB
GET  /tickets              -> list the persona's tickets
GET  /ticket/{id}          -> single ticket detail
POST /chat                 -> proxy to sb-router specialist
GET  /kb                   -> browse KB articles
GET  /api/personas         -> persona picker data
POST /api/persona/select   -> sets persona cookie
GET  /health               -> liveness
GET  /readyz               -> readiness (pings postgres)
GET  /metrics              -> Prometheus metrics
```

Runs behind the same OTel pipeline as NeonCart. Service name: `supportbot`.

## "View as" persona picker

The navbar dropdown lets a demo SE act as any persona seeded by migration
`0001_initial` (50 personas, 5 offenders). Resolution order on every
request:

1. `X-Persona-Id` header (loadgen / curl / specialist-to-specialist)
2. `supportbot_persona_id` cookie (set by `POST /api/persona/select`)
3. `guest@acme.com` fallback

The persona flows through to `sb-router` via the `persona_id` field in the
chat request body, which the specialist base passes to the llm-gateway in
the `ai_o11y.persona_id` field. Every span on the path gets
`ai_o11y.persona_id` set so dashboards/evaluators can filter by it.

`app/personas.py` mirrors the NeonCart pattern (FastAPI dependency,
list helper, span attr setter). The picker UI itself is JS-driven (see
`app/static/app.js`) rather than the HTMX-select pattern NeonCart uses —
both end up calling the same `POST /api/persona/select` endpoint.
