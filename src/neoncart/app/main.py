"""NeonCart FastAPI app.

Phase 1 contract (see ../README.md):

  GET  /                      -> home page with featured items
  GET  /products/{id}         -> product detail
  GET  /catalog               -> paginated catalog grid
  GET  /cart                  -> placeholder cart view
  POST /chat                  -> proxy to nc-chatbot specialist
  GET  /api/personas          -> persona dropdown data (JSON)
  POST /api/persona/select    -> set the persona cookie ("view as" picker)
  GET  /health                -> liveness
  GET  /readyz                -> readiness (pings postgres)
  GET  /metrics               -> Prometheus metrics

The chatbot proxy uses httpx; OTel httpx instrumentation propagates the
trace context to nc-chatbot, which is what makes the mice-rca demo flow
appear as one continuous trace from browser -> chatbot -> orchestrator ->
postgres (where the column-doesnt-exist error lights up).

Every endpoint resolves a ``persona_id`` from ``X-Persona-Id`` header or
``persona`` cookie via the ``get_persona_id`` dependency and stamps it on
the active OTel span as ``ai_o11y.persona_id``. The chat proxy forwards
the same value to nc-chatbot so it propagates all the way through to the
llm-gateway span.
"""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncIterator

import httpx
from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import db
from app.models import CatalogItem, Category, Persona
from app.personas import (
    GUEST_PERSONA_ID,
    get_persona_id,
    list_personas,
    pick_random_persona_id,
    set_persona_span_attr,
)

log = logging.getLogger(__name__)
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))

APP_DIR = Path(__file__).resolve().parent
TEMPLATE_DIR = APP_DIR / "templates"
STATIC_DIR = APP_DIR / "static"

CHATBOT_URL = os.getenv("CHATBOT_URL", "http://nc-chatbot/v1/run")
LLM_GATEWAY_URL = os.getenv("LLM_GATEWAY_URL", "http://llm-gateway:80")
DEFAULT_USECASE = os.getenv("AI_O11Y_DEFAULT_USECASE", "mice-rca")

BRANDING: dict[str, str] = {
    "name": os.getenv("BRANDING_NAME", "NeonCart"),
    "tagline": os.getenv("BRANDING_TAGLINE", "Future-forward retail"),
    "primary_color": os.getenv("BRANDING_PRIMARY_COLOR", "#7c3aed"),
    "logo_url": os.getenv("BRANDING_LOGO_URL", ""),
}

# Base URL of the Grafana stack hosting Sigil. The chat widget builds an
# "Open conversation in Sigil" deep-link from this + the session_id so demo
# users can jump from a turn in the storefront to the full conversation in
# Sigil. Empty string disables the link.
GRAFANA_BASE_URL = os.getenv("GRAFANA_BASE_URL", "").rstrip("/")


# ---- OTel bootstrap --------------------------------------------------------
def _instrument(app: FastAPI) -> None:
    """Best-effort OTel wiring: stand up a TracerProvider + OTLP/HTTP exporter,
    then auto-instrument FastAPI/httpx/asyncpg.

    Without an explicit TracerProvider, structured log records emit
    ``trace_id=""`` / ``span_id=""`` and traces never reach the collector,
    which breaks the "one continuous trace" demo storyline. Silently no-ops
    if the SDK libs aren't installed (keeps unit tests light)."""
    try:
        from opentelemetry import trace
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor

        service_name = os.environ.get("OTEL_SERVICE_NAME", "neoncart")
        namespace = os.environ.get("OBSERVIBELITY_NAMESPACE", "observibelity")
        if not isinstance(trace.get_tracer_provider(), TracerProvider):
            resource = Resource.create(
                {
                    "service.name": service_name,
                    "service.namespace": namespace,
                    "service.instance.id": os.environ.get("HOSTNAME", "unknown"),
                    "deployment.environment": os.environ.get(
                        "DEPLOYMENT_ENVIRONMENT", "demo"
                    ),
                    "telemetry.sdk.name": "opentelemetry",
                }
            )
            provider = TracerProvider(resource=resource)
            endpoint = os.environ.get(
                "OTEL_EXPORTER_OTLP_ENDPOINT", "http://otel-collector:4318"
            ).rstrip("/")
            # OTLP/HTTP exporter wants the fully qualified /v1/traces path,
            # not the collector root URL.
            from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
                OTLPSpanExporter,
            )

            exporter = OTLPSpanExporter(endpoint=f"{endpoint}/v1/traces")
            provider.add_span_processor(BatchSpanProcessor(exporter))
            trace.set_tracer_provider(provider)

        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
        from opentelemetry.instrumentation.asyncpg import AsyncPGInstrumentor

        FastAPIInstrumentor.instrument_app(app)
        HTTPXClientInstrumentor().instrument()
        AsyncPGInstrumentor().instrument()
        log.info("OTel instrumentation enabled (service=%s)", service_name)
    except Exception as exc:  # noqa: BLE001 — never crash on telemetry
        log.warning("OTel instrumentation skipped: %s", exc)


def _build_sigil_url(session_id: str | None) -> str | None:
    """Build a deep-link into the Sigil Conversations view for ``session_id``.

    Falls back to a generic Conversations filter when GRAFANA_BASE_URL is
    set but the route shape can't be locked in until we ship — Sigil's
    conversation URL pattern has changed twice this quarter. Returning a
    list-with-filter URL still gets the demo viewer onto the right page.
    """
    if not GRAFANA_BASE_URL or not session_id:
        return None
    # Sigil hangs off the Grafana plugin route. The conversation list page
    # accepts a free-text filter param that matches session_id.
    return (
        f"{GRAFANA_BASE_URL}/a/grafana-sigil-app/conversations"
        f"?conversation_id={session_id}"
    )


def _set_usecase_attr(usecase: str = DEFAULT_USECASE) -> None:
    """Attach `ai_o11y.usecase` to the current span if tracing is active."""
    try:
        from opentelemetry import trace

        span = trace.get_current_span()
        if span and span.is_recording():
            span.set_attribute("ai_o11y.usecase", usecase)
    except Exception:  # noqa: BLE001
        pass


async def _render_with_personas(
    template_name: str,
    request: Request,
    session: AsyncSession,
    persona_id: str | None,
    extra: dict[str, Any],
) -> HTMLResponse:
    """Helper: render a template with ``personas`` + ``current_persona`` injected.

    If ``persona_id`` is None (no header/cookie), picks a random non-guest
    persona on each page load — replaces the old "Guest (no persona)" default
    so demos show realistic user attribution from the first paint.

    Catches DB failures gracefully — if Postgres is unreachable or the
    table isn't seeded yet, the picker simply shows the guest option
    rather than 500-ing the page.
    """
    try:
        personas = await list_personas(session)
    except Exception as exc:  # noqa: BLE001 — picker is nice-to-have
        log.warning("persona list query failed: %s", exc)
        personas = []
    resolved = persona_id or pick_random_persona_id(personas)
    request.state.persona_id = resolved
    set_persona_span_attr(resolved)
    # Find the email for the resolved persona so the chat widget can
    # embed it as a hidden input (server -> /chat -> nc-chatbot -> Sigil).
    email = ""
    for p in personas:
        if p.persona_id == resolved:
            email = p.email or ""
            break
    ctx: dict[str, Any] = {
        "branding": BRANDING,
        "personas": personas,
        "current_persona": resolved,
        "current_persona_email": email,
    }
    ctx.update(extra)
    return templates.TemplateResponse(request, template_name, ctx)


# ---- Lifespan --------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    log.info("neoncart starting — DATABASE_URL=%s", db.DATABASE_URL.split("@")[-1])
    _instrument(app)
    app.state.http = httpx.AsyncClient(timeout=15.0)
    try:
        yield
    finally:
        await app.state.http.aclose()
        await db.dispose()
        log.info("neoncart shutdown complete")


app = FastAPI(
    title="NeonCart",
    version="0.2.0",
    description="E-commerce frontend for the ObserVIBElity demo.",
    lifespan=lifespan,
)

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
templates = Jinja2Templates(directory=str(TEMPLATE_DIR))
templates.env.globals["branding"] = BRANDING
templates.env.globals["grafana_base_url"] = GRAFANA_BASE_URL


# ---- Schemas ---------------------------------------------------------------
class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=2048)
    # ``persona_id`` may arrive on the wire (e.g. from loadgen) but the
    # request-scoped dependency overrides it when set via header/cookie.
    persona_id: str | None = None
    usecase: str | None = None
    # Per-request routing knobs forwarded to nc-chatbot -> llm-gateway. The
    # loadgen sets these to drive the 80/20 Ollama vs Claude split that
    # populates the ai-obs-best-models dashboard. The interactive UI pins
    # provider_override="anthropic" so manual sessions always use Claude.
    provider_override: str | None = None
    model_override: str | None = None
    # Conversation grouping for Sigil. The web UI generates a fresh uuid per
    # page load so each visit is one conversation; loadgen omits this and
    # the gateway falls back to its persona+hour bucket.
    session_id: str | None = None
    # Surface the persona email so Sigil's Conversations view shows the
    # actual user instead of just the persona slug. Looked up server-side
    # from the personas table when not provided on the wire.
    email: str | None = None
    # Distinguishes hand-driven sessions (interactive) from loadgen runs
    # (continuous). Drives the Sigil traffic-origin facet.
    traffic_origin: str | None = None


class ChatResponse(BaseModel):
    """Wire shape the widget renders. Mirrors fields the specialist forwards
    plus a couple of UI-only conveniences (sigil_url, session_id echo)."""

    reply: str
    tool_calls: list[dict[str, Any]] = Field(default_factory=list)
    usecase: str
    model: str | None = None
    provider: str | None = None
    actions: list[dict[str, Any]] = Field(default_factory=list)
    products: list[dict[str, Any]] = Field(default_factory=list)
    cost_usd: float = 0.0
    session_id: str | None = None
    span_id: str | None = None
    sigil_url: str | None = None


class PersonaSelectRequest(BaseModel):
    persona_id: str = Field(..., min_length=1, max_length=64)


# ---- HTML routes -----------------------------------------------------------
@app.get("/", response_class=HTMLResponse)
async def home(
    request: Request,
    persona_id: str | None = Depends(get_persona_id),
    session: AsyncSession = Depends(db.get_session),
) -> HTMLResponse:
    _set_usecase_attr()
    result = await session.execute(select(CatalogItem).limit(8))
    items = result.scalars().all()
    return await _render_with_personas(
        "index.html", request, session, persona_id, {"items": items}
    )


@app.get("/products/{product_id}", response_class=HTMLResponse)
async def product_detail(
    product_id: int,
    request: Request,
    persona_id: str | None = Depends(get_persona_id),
    session: AsyncSession = Depends(db.get_session),
) -> HTMLResponse:
    _set_usecase_attr()
    item = await session.get(CatalogItem, product_id)
    if item is None:
        raise HTTPException(status_code=404, detail="product not found")
    return await _render_with_personas(
        "products/detail.html", request, session, persona_id, {"item": item}
    )


@app.get("/catalog", response_class=HTMLResponse)
async def catalog(
    request: Request,
    page: int = Query(1, ge=1),
    per_page: int = Query(24, ge=1, le=100),
    category: str | None = Query(None, min_length=1, max_length=64),
    persona_id: str | None = Depends(get_persona_id),
    session: AsyncSession = Depends(db.get_session),
) -> HTMLResponse:
    """Catalog grid. ``?category=<slug>`` filters by joining categories.slug.

    The chat widget routes the page here when the bot emits a navigate
    action, so the grid filters to match the conversation (e.g. "show me
    keyboards" → /catalog?category=peripherals).
    """
    _set_usecase_attr()
    offset = (page - 1) * per_page
    items_q = select(CatalogItem)
    if category:
        items_q = items_q.join(Category, CatalogItem.category_id == Category.id).where(
            Category.slug == category
        )
    items_q = items_q.offset(offset).limit(per_page)
    cats_q = select(Category)
    items = (await session.execute(items_q)).scalars().all()
    categories = (await session.execute(cats_q)).scalars().all()
    return await _render_with_personas(
        "catalog.html",
        request,
        session,
        persona_id,
        {
            "items": items,
            "categories": categories,
            "page": page,
            "active_category": category,
        },
    )


@app.get("/cart", response_class=HTMLResponse)
async def cart(
    request: Request,
    persona_id: str | None = Depends(get_persona_id),
    session: AsyncSession = Depends(db.get_session),
) -> HTMLResponse:
    # TODO(phase1): wire actual cart state once orders schema lands.
    return await _render_with_personas(
        "base.html",
        request,
        session,
        persona_id,
        {"body_block": "Cart is empty."},
    )


# ---- API routes ------------------------------------------------------------
@app.post("/chat")
async def chat(
    request: Request,
    payload: ChatRequest,
    persona_id: str | None = Depends(get_persona_id),
    session: AsyncSession = Depends(db.get_session),
) -> Response:
    """Proxy to the nc-chatbot specialist.

    The httpx OTel instrumentation injects W3C tracecontext headers; the
    specialist picks them up and continues the span tree. That's how the
    mice-rca flow shows up as one trace in Tempo.

    The persona resolved from header/cookie wins over any wire payload, so
    the loadgen path (which sets ``persona_id`` in the body) and the
    "view as" picker (header/cookie) both end up with the correct value
    flowing through to llm-gateway span attributes.
    """
    usecase = payload.usecase or DEFAULT_USECASE
    _set_usecase_attr(usecase)

    effective_persona = persona_id or payload.persona_id or GUEST_PERSONA_ID
    set_persona_span_attr(effective_persona)

    # Resolve the email — prefer what the form sent (kept hidden on every
    # rendered page so the lookup happens once at render time), then fall
    # back to a DB query so curl/loadgen still get attribution.
    email = payload.email
    if not email and effective_persona != GUEST_PERSONA_ID:
        try:
            result = await session.execute(
                select(Persona).where(Persona.persona_id == effective_persona)
            )
            persona = result.scalar_one_or_none()
            if persona and persona.email:
                email = persona.email
        except Exception as exc:  # noqa: BLE001 — attribution is best-effort
            log.warning("persona email lookup failed: %s", exc)

    client: httpx.AsyncClient = request.app.state.http
    body: dict[str, Any] = {
        "message": payload.message,
        "persona_id": effective_persona,
        "usecase": usecase,
    }
    if payload.provider_override:
        body["provider_override"] = payload.provider_override
    if payload.model_override:
        body["model_override"] = payload.model_override
    if payload.session_id:
        body["session_id"] = payload.session_id
    # Context bag the specialist forwards into ai_o11y so Sigil can show
    # email + traffic_origin on the Conversations + Generations views.
    context: dict[str, Any] = {}
    if email:
        context["email"] = email
    if payload.traffic_origin:
        context["traffic_origin"] = payload.traffic_origin
    if context:
        body["context"] = context
    try:
        resp = await client.post(CHATBOT_URL, json=body)
    except httpx.RequestError as exc:
        log.warning("chatbot unreachable: %s", exc)
        return JSONResponse(
            {
                "reply": f"Chatbot unreachable: {exc}",
                "tool_calls": [],
                "usecase": usecase,
                "session_id": payload.session_id,
                "error": "unreachable",
            },
            status_code=503,
        )

    if resp.status_code >= 400:
        return JSONResponse(
            {
                "reply": f"Chatbot error {resp.status_code}",
                "tool_calls": [],
                "usecase": usecase,
                "session_id": payload.session_id,
                "error": f"http_{resp.status_code}",
            },
            status_code=resp.status_code,
        )

    data = resp.json()
    sigil_url = _build_sigil_url(payload.session_id) if payload.session_id else None
    out = ChatResponse(
        reply=data.get("reply") or data.get("message") or "",
        tool_calls=data.get("tool_calls") or [],
        usecase=usecase,
        model=data.get("model"),
        provider=data.get("provider"),
        actions=data.get("actions") or [],
        products=data.get("products") or [],
        cost_usd=float(data.get("cost_usd") or 0.0),
        session_id=payload.session_id,
        span_id=data.get("span_id"),
        sigil_url=sigil_url,
    )
    return JSONResponse(out.model_dump())


# ---- Persona API -----------------------------------------------------------
@app.get("/api/personas")
async def api_list_personas(
    session: AsyncSession = Depends(db.get_session),
) -> JSONResponse:
    """List all personas as JSON for UI dropdowns + scripts.

    Returns a stable shape (id, name, role, archetype, offender_pattern)
    even if the underlying schema gains columns later.
    """
    personas = await list_personas(session)
    payload = [
        {
            "persona_id": p.persona_id,
            "name": p.name,
            "role": p.role,
            "archetype": p.archetype,
            "offender_pattern": p.offender_pattern,
        }
        for p in personas
    ]
    return JSONResponse(payload)


@app.post("/api/persona/select")
async def api_persona_select(payload: PersonaSelectRequest) -> JSONResponse:
    """Set the ``persona`` cookie so subsequent requests act as that user.

    The cookie is HttpOnly + SameSite=Lax + Path=/. HTMX-driven select boxes
    POST here on change; the server response is small enough to be a no-op
    swap target.
    """
    response = JSONResponse({"persona_id": payload.persona_id, "ok": True})
    response.set_cookie(
        key="persona",
        value=payload.persona_id,
        httponly=True,
        samesite="lax",
        path="/",
        max_age=60 * 60 * 24 * 30,  # 30 days — demo sessions are long-lived
    )
    return response


# ---- Ops endpoints ---------------------------------------------------------
@app.get("/health", response_class=PlainTextResponse)
async def health() -> str:
    return "ok"


@app.get("/readyz")
async def readyz() -> JSONResponse:
    ok = await db.ping()
    return JSONResponse({"postgres": ok}, status_code=200 if ok else 503)


@app.get("/metrics")
async def metrics() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
