"""FastAPI entrypoint for the update_ticket tool."""
from tool_base.main import build_app

from .tool import UpdateTicket

app = build_app(UpdateTicket())
