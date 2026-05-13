"""FastAPI entrypoint for the list_tickets tool."""
from tool_base.main import build_app

from .tool import ListTickets

app = build_app(ListTickets())
