"""Support Bot ("Ask Acme") FastAPI app.

Phase 2 contract (see ../README.md):

  GET  /                     -> landing page + featured KB
  GET  /tickets              -> list the persona's tickets
  GET  /ticket/{id}          -> ticket detail
  POST /chat                 -> proxy to sb-router specialist
  GET  /kb                   -> browse KB articles
  GET  /api/personas         -> persona picker data
  POST /api/persona/select   -> sets persona cookie
  GET  /health, /readyz, /metrics

Same OTel + persona-cookie pattern as NeonCart. Service name: `supportbot`.
The chat proxy POSTs to sb-router which classifies and forwards to the right
SB specialist (kb-search / policy-finder / ticket-helper / etc.). The W3C
tracecontext header propagates from browser -> supportbot -> sb-router ->
downstream specialist -> tool, so a single chat turn shows up as one trace
in Tempo.
"""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncIterator

import httpx
from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import db
from app.models import Persona, SupportbotKb, Ticket

log = logging.getLogger(__name__)
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))

APP_DIR = Path(__file__).resolve().parent
TEMPLATE_DIR = APP_DIR / "templates"
STATIC_DIR = APP_DIR / "static"

ROUTER_URL = os.getenv("ROUTER_URL", "http://sb-router/v1/run")
LLM_GATEWAY_URL = os.getenv("LLM_GATEWAY_URL", "http://llm-gateway:80")
DEFAULT_USECASE = os.getenv("AI_O11Y_DEFAULT_USECASE", "supportbot-general")
PERSONA_COOKIE = "supportbot_persona_id"

BRANDING: dict[str, str] = {
    "name": os.getenv("BRANDING_NAME", "Ask Acme"),
    "tagline": os.getenv("BRANDING_TAGLINE", "Internal support, on tap."),
    "primary_color": os.getenv("BRANDING_PRIMARY_COLOR", "#2563eb"),
    "logo_url": os.getenv("BRANDING_LOGO_URL", ""),
}


# ---- OTel bootstrap --------------------------------------------------------
def _instrument(app: FastAPI) -> None:
    """Best-effort OTel wiring: stand up a TracerProvider + OTLP/HTTP exporter,
    then auto-instrument FastAPI/httpx/asyncpg.

    Without an explicit TracerProvider, structured log records emit
    ``trace_id=""`` / ``span_id=""`` and traces never reach the collector,
    which breaks the "one continuous trace" demo storyline. Silently no-ops
    if libs aren't installed (keeps unit tests light)."""
    try:
        from opentelemetry import trace
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor

        service_name = os.environ.get("OTEL_SERVICE_NAME", "supportbot")
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
            from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
                OTLPSpanExporter,
            )

            exporter = OTLPSpanExporter(endpoint=f"{endpoint}/v1/traces")
            provider.add_span_processor(BatchSpanProcessor(exporter))
            trace.set_tracer_provider(provider)

        from opentelemetry.instrumentation.asyncpg import AsyncPGInstrumentor
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor

        FastAPIInstrumentor.instrument_app(app)
        HTTPXClientInstrumentor().instrument()
        AsyncPGInstrumentor().instrument()
        log.info("OTel instrumentation enabled (service=%s)", service_name)
    except Exception as exc:  # noqa: BLE001
        log.warning("OTel instrumentation skipped: %s", exc)


def _set_usecase_attr(usecase: str = DEFAULT_USECASE, persona_id: str | None = None) -> None:
    """Attach ai_o11y attributes to the current span if tracing is active."""
    try:
        from opentelemetry import trace

        span = trace.get_current_span()
        if span and span.is_recording():
            span.set_attribute("ai_o11y.usecase", usecase)
            span.set_attribute("ai_o11y.app", "supportbot")
            if persona_id:
                span.set_attribute("ai_o11y.persona_id", persona_id)
    except Exception:  # noqa: BLE001
        pass


def _persona_id(request: Request) -> str | None:
    """Resolve the active persona: X-Persona-Id header beats the cookie."""
    return request.headers.get("X-Persona-Id") or request.cookies.get(PERSONA_COOKIE)


# ---- Lifespan --------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    log.info("supportbot starting — DATABASE_URL=%s", db.DATABASE_URL.split("@")[-1])
    _instrument(app)
    app.state.http = httpx.AsyncClient(
        timeout=httpx.Timeout(connect=5.0, read=15.0, write=5.0, pool=5.0),
        limits=httpx.Limits(
            max_connections=100,
            max_keepalive_connections=20,
            keepalive_expiry=30.0,
        ),
    )
    try:
        yield
    finally:
        await app.state.http.aclose()
        await db.dispose()
        log.info("supportbot shutdown complete")


app = FastAPI(
    title="Support Bot — Ask Acme",
    version="0.3.0",
    description="Internal HR/IT support assistant for the ObserVIBElity demo.",
    lifespan=lifespan,
)

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
templates = Jinja2Templates(directory=str(TEMPLATE_DIR))
templates.env.globals["branding"] = BRANDING


# ---- Schemas ---------------------------------------------------------------
class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=4096)
    persona_id: str | None = None
    usecase: str | None = None
    # Forwarded to llm-gateway so loadgen-set conversation IDs survive the
    # supportbot -> sb-router -> specialist -> gateway chain. Without this
    # the gateway falls back to hash(persona+UTC_hour), bucketing 1000+
    # messages into one Sigil conversation for heavy personas.
    session_id: str | None = None
    # Per-request routing knobs forwarded to sb-router -> llm-gateway. The
    # loadgen sets these to drive the 80/20 Ollama vs Claude split that
    # populates the ai-obs-best-models dashboard.
    provider_override: str | None = None
    model_override: str | None = None


class PersonaSelectRequest(BaseModel):
    persona_id: str = Field(..., min_length=1, max_length=64)


# ---- HTML routes -----------------------------------------------------------
@app.get("/", response_class=HTMLResponse)
async def home(
    request: Request, session: AsyncSession = Depends(db.get_session)
) -> HTMLResponse:
    _set_usecase_attr(persona_id=_persona_id(request))
    # The KB row's "confidential" flag is encoded in the tags string —
    # the schema doesn't have a boolean column. Exclude rows whose tags
    # include the "confidential" marker; NULL tags pass through.
    kb_q = (
        select(SupportbotKb)
        .where(
            (SupportbotKb.tags.is_(None))
            | (~SupportbotKb.tags.ilike("%confidential%"))
        )
        .limit(6)
    )
    featured = (await session.execute(kb_q)).scalars().all()
    return templates.TemplateResponse(
        request,
        "index.html",
        {"featured": featured, "branding": BRANDING},
    )


@app.get("/tickets", response_class=HTMLResponse)
async def list_tickets(
    request: Request,
    session: AsyncSession = Depends(db.get_session),
) -> HTMLResponse:
    pid = _persona_id(request)
    _set_usecase_attr(persona_id=pid)
    stmt = select(Ticket)
    # Ticket.persona_id is the string slug (FK to personas.persona_id) per
    # migrations/versions/0006_tickets.py. An earlier draft cast pid to int
    # which would never match (the DB stores "tim.lewis@acme.com" not 42).
    if pid:
        stmt = stmt.where(Ticket.persona_id == pid)
    stmt = stmt.order_by(Ticket.created_at.desc()).limit(50)
    tickets = (await session.execute(stmt)).scalars().all()
    return templates.TemplateResponse(
        request,
        "tickets.html",
        {"tickets": tickets, "branding": BRANDING},
    )


@app.get("/ticket/{ticket_id}", response_class=HTMLResponse)
async def ticket_detail(
    ticket_id: int,
    request: Request,
    session: AsyncSession = Depends(db.get_session),
) -> HTMLResponse:
    _set_usecase_attr(persona_id=_persona_id(request))
    ticket = await session.get(Ticket, ticket_id)
    if ticket is None:
        raise HTTPException(status_code=404, detail="ticket not found")
    return templates.TemplateResponse(
        request,
        "ticket_detail.html",
        {"ticket": ticket, "branding": BRANDING},
    )


@app.get("/kb", response_class=HTMLResponse)
async def kb_browse(
    request: Request,
    category: str | None = Query(default=None),
    session: AsyncSession = Depends(db.get_session),
) -> HTMLResponse:
    _set_usecase_attr(persona_id=_persona_id(request))
    # tags-based exclusion mirrors the schema in 0007_supportbot_kb.
    stmt = select(SupportbotKb).where(
        (SupportbotKb.tags.is_(None))
        | (~SupportbotKb.tags.ilike("%confidential%"))
    )
    if category:
        # Category is a tags-prefix match (CSV tag list, ';'-separated).
        stmt = stmt.where(SupportbotKb.tags.ilike(f"{category};%") | SupportbotKb.tags.ilike(f"%;{category};%") | SupportbotKb.tags.ilike(f"%;{category}") | (SupportbotKb.tags == category))
    articles = (await session.execute(stmt.order_by(SupportbotKb.title).limit(100))).scalars().all()
    return templates.TemplateResponse(
        request,
        "kb.html",
        {"articles": articles, "branding": BRANDING, "category": category},
    )


# ---- API routes ------------------------------------------------------------
@app.get("/api/personas")
async def personas_list(session: AsyncSession = Depends(db.get_session)) -> JSONResponse:
    rows = (await session.execute(select(Persona).limit(200))).scalars().all()
    # Persona schema (0001_initial): id, persona_id slug, name, email, role,
    # archetype, offender_pattern, weight. An earlier version of this
    # endpoint returned a non-existent ``department`` column and 500'd.
    return JSONResponse(
        [
            {
                "id": p.id,
                "persona_id": p.persona_id,
                "name": p.name,
                "role": p.role,
                "archetype": p.archetype,
                "offender_pattern": p.offender_pattern,
            }
            for p in rows
        ]
    )


@app.post("/api/persona/select")
async def persona_select(payload: PersonaSelectRequest) -> JSONResponse:
    resp = JSONResponse({"ok": True, "persona_id": payload.persona_id})
    # 30-day cookie — long enough for the demo, short enough for hygiene.
    resp.set_cookie(
        PERSONA_COOKIE,
        payload.persona_id,
        max_age=60 * 60 * 24 * 30,
        httponly=False,  # readable by the picker JS
        samesite="lax",
    )
    return resp


@app.post("/chat")
async def chat(request: Request, payload: ChatRequest) -> Response:
    """Proxy to sb-router, which classifies and forwards to the right SB specialist."""
    pid = payload.persona_id or _persona_id(request)
    usecase = payload.usecase or DEFAULT_USECASE
    _set_usecase_attr(usecase, persona_id=pid)

    client: httpx.AsyncClient = request.app.state.http
    body: dict[str, Any] = {
        "message": payload.message,
        "persona_id": pid,
        "usecase": usecase,
    }
    if payload.session_id:
        body["session_id"] = payload.session_id
    if payload.provider_override:
        body["provider_override"] = payload.provider_override
    if payload.model_override:
        body["model_override"] = payload.model_override
    try:
        resp = await client.post(ROUTER_URL, json=body)
    except httpx.RequestError as exc:
        log.warning("router unreachable: %s", exc)
        return HTMLResponse(
            f'<div class="ab-chat-msg ab-chat-msg--bot">Support bot unreachable: {exc}</div>',
            status_code=503,
        )

    if resp.status_code >= 400:
        return HTMLResponse(
            f'<div class="ab-chat-msg ab-chat-msg--bot ab-chat-msg--err">'
            f"Support bot error {resp.status_code}</div>",
            status_code=resp.status_code,
        )

    accept = request.headers.get("accept", "")
    if "application/json" in accept:
        return JSONResponse(resp.json())

    data = resp.json()
    reply = data.get("reply") or data.get("message") or ""
    return HTMLResponse(
        f'<div class="ab-chat-msg ab-chat-msg--user">{payload.message}</div>'
        f'<div class="ab-chat-msg ab-chat-msg--bot">{reply}</div>'
    )


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
