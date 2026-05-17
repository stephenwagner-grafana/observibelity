"""FastAPI entrypoint for the query_skus_latest tool."""
from tool_base.main import build_app

from .tool import QuerySkusLatest

app = build_app(QuerySkusLatest())
