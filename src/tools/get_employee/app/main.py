"""FastAPI entrypoint for the get_employee tool."""
from tool_base.main import build_app

from .tool import GetEmployee

app = build_app(GetEmployee())
