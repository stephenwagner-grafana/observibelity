"""FastAPI entrypoint for the get_product tool."""
from tool_base.main import build_app

from .tool import GetProduct

app = build_app(GetProduct())
