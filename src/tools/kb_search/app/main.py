"""FastAPI entrypoint for the kb_search tool."""
from tool_base.main import build_app

from .tool import KbSearch

app = build_app(KbSearch())
