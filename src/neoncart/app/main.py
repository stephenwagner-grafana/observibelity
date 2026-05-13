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
from app.models import CatalogItem, Category
from app.personas import (
    GUEST_PERSONA_ID,
    get_persona_id,
    list_personas,
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


# ---- OTel bootstrap --------------------------------------------------------
def _instrument(app: FastAPI) -> None:
    """Best-effort OTel wiring. Silently no-ops if libs aren't installed
    (keeps unit tests light)."""
    try:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
        from opentelemetry.instrumentation.asyncpg import AsyncPGInstrumentor

        FastAPIInstrumentor.instrument_app(app)
        HTTPXClientInstrumentor().instrument()
        AsyncPGInstrumentor().instrument()
        log.info("OTel instrumentation enabled")
    except Exception as exc:  # noqa: BLE001 — never crash on telemetry
        log.warning("OTel instrumentation skipped: %s", exc)


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
    persona_id: str,
    extra: dict[str, Any],
) -> HTMLResponse:
    """Helper: render a template with ``personas`` + ``current_persona`` injected.

    Catches DB failures gracefully — if Postgres is unreachable or the
    table isn't seeded yet, the picker simply shows the guest option
    rather than 500-ing the page.
    """
    try:
        personas = await list_personas(session)
    except Exception as exc:  # noqa: BLE001 — picker is nice-to-have
        log.warning("persona list query failed: %s", exc)
        personas = []
    ctx: dict[str, Any] = {
        "request": request,
        "branding": BRANDING,
        "personas": personas,
        "current_persona": persona_id,
    }
    ctx.update(extra)
    return templates.TemplateResponse(template_name, ctx)


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


# ---- Schemas ---------------------------------------------------------------
class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=2048)
    # ``persona_id`` may arrive on the wire (e.g. from loadgen) but the
    # request-scoped dependency overrides it when set via header/cookie.
    persona_id: str | None = None
    usecase: str | None = None


class ChatResponse(BaseModel):
    reply: str
    tool_calls: list[dict[str, Any]] = Field(default_factory=list)
    usecase: str


class PersonaSelectRequest(BaseModel):
    persona_id: str = Field(..., min_length=1, max_length=64)


# ---- HTML routes -----------------------------------------------------------
@app.get("/", response_class=HTMLResponse)
async def home(
    request: Request,
    persona_id: str = Depends(get_persona_id),
    session: AsyncSession = Depends(db.get_session),
) -> HTMLResponse:
    _set_usecase_attr()
    set_persona_span_attr(persona_id)
    result = await session.execute(select(CatalogItem).limit(8))
    items = result.scalars().all()
    return await _render_with_personas(
        "index.html", request, session, persona_id, {"items": items}
    )


@app.get("/products/{product_id}", response_class=HTMLResponse)
async def product_detail(
    product_id: int,
    request: Request,
    persona_id: str = Depends(get_persona_id),
    session: AsyncSession = Depends(db.get_session),
) -> HTMLResponse:
    _set_usecase_attr()
    set_persona_span_attr(persona_id)
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
    persona_id: str = Depends(get_persona_id),
    session: AsyncSession = Depends(db.get_session),
) -> HTMLResponse:
    _set_usecase_attr()
    set_persona_span_attr(persona_id)
    offset = (page - 1) * per_page
    items_q = select(CatalogItem).offset(offset).limit(per_page)
    cats_q = select(Category)
    items = (await session.execute(items_q)).scalars().all()
    categories = (await session.execute(cats_q)).scalars().all()
    return await _render_with_personas(
        "catalog.html",
        request,
        session,
        persona_id,
        {"items": items, "categories": categories, "page": page},
    )


@app.get("/cart", response_class=HTMLResponse)
async def cart(
    request: Request,
    persona_id: str = Depends(get_persona_id),
    session: AsyncSession = Depends(db.get_session),
) -> HTMLResponse:
    # TODO(phase1): wire actual cart state once orders schema lands.
    set_persona_span_attr(persona_id)
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
    persona_id: str = Depends(get_persona_id),
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

    client: httpx.AsyncClient = request.app.state.http
    body = {
        "message": payload.message,
        "persona_id": effective_persona,
        "usecase": usecase,
    }
    try:
        resp = await client.post(CHATBOT_URL, json=body)
    except httpx.RequestError as exc:
        log.warning("chatbot unreachable: %s", exc)
        # HTMX-friendly: return an HTML fragment so the chat widget keeps working
        return HTMLResponse(
            f'<div class="chat-msg chat-msg--bot">Chatbot unreachable: {exc}</div>',
            status_code=503,
        )

    if resp.status_code >= 400:
        return HTMLResponse(
            f'<div class="chat-msg chat-msg--bot chat-msg--err">'
            f"Chatbot error {resp.status_code}</div>",
            status_code=resp.status_code,
        )

    # HTMX expects an HTML fragment; JSON consumers still get a parseable body.
    accept = request.headers.get("accept", "")
    if "application/json" in accept:
        return JSONResponse(resp.json())

    data = resp.json()
    reply = data.get("reply") or data.get("message") or ""
    return HTMLResponse(
        f'<div class="chat-msg chat-msg--user">{payload.message}</div>'
        f'<div class="chat-msg chat-msg--bot">{reply}</div>'
    )


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
