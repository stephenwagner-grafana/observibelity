"""FastAPI entrypoint for the get_ticket tool."""
from tool_base.main import build_app

from .tool import GetTicket

app = build_app(GetTicket())
