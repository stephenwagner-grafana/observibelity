"""FastAPI entrypoint for the search_products tool."""
from tool_base.main import build_app

from .tool import SearchProducts

app = build_app(SearchProducts())
