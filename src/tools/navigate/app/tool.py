"""navigate — agent-visible "send the shopper to a page" action.

Purely synthesizes a URL + label from a structured (target, value) pair.
The neoncart frontend reads the returned URL and redirects the browser
when the chat widget sees the action come back from /chat.

Why a tool (not a synthesized action from the specialist)? So Sigil sees
`gen_ai.tool.name="navigate"` per turn and dashboards can answer
"how often does the agent send the user somewhere?" without joining
HTTP logs. Also gives the model an explicit verb to reach for when the
user says "show me X" instead of inferring intent from keywords.
"""
from __future__ import annotations

import logging
from typing import ClassVar, Literal

from pydantic import AliasChoices, BaseModel, Field
from prometheus_client import Counter

from tool_base import Tool

log = logging.getLogger(__name__)


NAV_COUNTER = Counter(
    "nc_navigate_total",
    "Browser-navigation events emitted by an agent via the navigate tool.",
    ["target", "agent_name", "model"],
)


class NavigateArgs(BaseModel):
    """Inputs for ``navigate``.

    ``target`` selects the URL shape; ``value`` is the slug/query/id the
    URL embeds. The tool does no validation against the live catalog — it
    just builds the URL string. If the catalog has no matches for the
    value, the catalog page will render its empty state, which is fine.
    """

    target: Literal["category", "search", "product", "cart"] = Field(
        ..., description="What to navigate to: category page, search results, product page, or cart."
    )
    # Models sometimes guess intuitive names like "slug" / "query" / "term" /
    # "category" / "product_id" / "id" depending on target. Accept any of them
    # so a small phrasing miss doesn't break the redirect.
    value: str = Field(
        default="",
        max_length=128,
        validation_alias=AliasChoices(
            "value", "slug", "query", "q", "term", "category", "product_id", "id"
        ),
        description=(
            "Slug for category (e.g. 'peripherals'), free-text for search "
            "(e.g. 'mice'), id for product. Empty for cart."
        ),
    )

    model_config = {"populate_by_name": True}
    agent_name: str | None = Field(default=None, max_length=64)
    model: str | None = Field(default=None, max_length=128)


class NavigateResult(BaseModel):
    """URL + human label returned to the specialist (forwarded to the widget)."""

    url: str
    label: str
    target: str
    value: str


def _pretty_slug(slug: str) -> str:
    return " ".join(s.capitalize() for s in (slug or "").split("-") if s)


class Navigate(Tool):
    NAME: ClassVar[str] = "navigate"
    SIDE_EFFECT: ClassVar[bool] = False
    IDEMPOTENT: ClassVar[bool] = True
    TIMEOUT_SEC: ClassVar[int] = 2
    MAX_CONCURRENCY: ClassVar[int] = 100
    CACHE_TTL_SEC: ClassVar[int] = 0
    RETRIES: ClassVar[int] = 0
    BACKING_TABLES: ClassVar[list[str]] = []
    REPLICAS: ClassVar[int] = 1

    Args = NavigateArgs
    Result = NavigateResult

    async def execute(self, args: NavigateArgs, session=None) -> NavigateResult:
        target = args.target
        value = (args.value or "").strip()
        if target == "category":
            url = f"/catalog?category={value}"
            label = f"Browse {_pretty_slug(value) or 'catalog'}"
        elif target == "search":
            url = f"/catalog?q={value}"
            label = f'Search "{value}"' if value else "Browse catalog"
        elif target == "product":
            url = f"/products/{value}"
            label = "View product"
        else:
            url = "/cart"
            label = "Go to cart"
        NAV_COUNTER.labels(
            target=target,
            agent_name=args.agent_name or "",
            model=args.model or "",
        ).inc()
        log.info(
            "navigate target=%s value=%s url=%s agent_name=%s model=%s",
            target, value, url, args.agent_name or "", args.model or "",
        )
        return NavigateResult(url=url, label=label, target=target, value=value)
