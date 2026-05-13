"""NeonCart FastAPI app.

Phase 1 contract (see ../README.md):

  GET  /              -> home page with featured items
  GET  /products/{id} -> product detail
  GET  /catalog       -> paginated catalog grid
  GET  /cart          -> placeholder cart view
  POST /chat          -> proxy to nc-chatbot specialist
  GET  /health        -> liveness
  GET  /readyz        -> readiness (pings postgres)
  GET  /metrics       -> Prometheus metrics

The chatbot proxy uses httpx; OTel httpx instrumentation propagates the
trace context to nc-chatbot, which is what makes the mice-rca demo flow
appear as one continuous trace from browser -> chatbot -> orchestrator ->
postgres (where the column-doesnt-exist error lights up).
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
    persona_id: int | None = None
    usecase: str | None = None


class ChatResponse(BaseModel):
    reply: str
    tool_calls: list[dict[str, Any]] = Field(default_factory=list)
    usecase: str


# ---- HTML routes -----------------------------------------------------------
@app.get("/", response_class=HTMLResponse)
async def home(request: Request, session: AsyncSession = Depends(db.get_session)) -> HTMLResponse:
    _set_usecase_attr()
    result = await session.execute(select(CatalogItem).limit(8))
    items = result.scalars().all()
    return templates.TemplateResponse(
        "index.html",
        {"request": request, "items": items, "branding": BRANDING},
    )


@app.get("/products/{product_id}", response_class=HTMLResponse)
async def product_detail(
    product_id: int,
    request: Request,
    session: AsyncSession = Depends(db.get_session),
) -> HTMLResponse:
    _set_usecase_attr()
    item = await session.get(CatalogItem, product_id)
    if item is None:
        raise HTTPException(status_code=404, detail="product not found")
    return templates.TemplateResponse(
        "products/detail.html",
        {"request": request, "item": item, "branding": BRANDING},
    )


@app.get("/catalog", response_class=HTMLResponse)
async def catalog(
    request: Request,
    page: int = Query(1, ge=1),
    per_page: int = Query(24, ge=1, le=100),
    session: AsyncSession = Depends(db.get_session),
) -> HTMLResponse:
    _set_usecase_attr()
    offset = (page - 1) * per_page
    items_q = select(CatalogItem).offset(offset).limit(per_page)
    cats_q = select(Category)
    items = (await session.execute(items_q)).scalars().all()
    categories = (await session.execute(cats_q)).scalars().all()
    return templates.TemplateResponse(
        "catalog.html",
        {
            "request": request,
            "items": items,
            "categories": categories,
            "branding": BRANDING,
            "page": page,
        },
    )


@app.get("/cart", response_class=HTMLResponse)
async def cart(request: Request) -> HTMLResponse:
    # TODO(phase1): wire actual cart state once orders schema lands.
    return templates.TemplateResponse(
        "base.html",
        {"request": request, "branding": BRANDING, "body_block": "Cart is empty."},
    )


# ---- API routes ------------------------------------------------------------
@app.post("/chat")
async def chat(request: Request, payload: ChatRequest) -> Response:
    """Proxy to the nc-chatbot specialist.

    The httpx OTel instrumentation injects W3C tracecontext headers; the
    specialist picks them up and continues the span tree. That's how the
    mice-rca flow shows up as one trace in Tempo.
    """
    usecase = payload.usecase or DEFAULT_USECASE
    _set_usecase_attr(usecase)

    client: httpx.AsyncClient = request.app.state.http
    body = {
        "message": payload.message,
        "persona_id": payload.persona_id,
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
