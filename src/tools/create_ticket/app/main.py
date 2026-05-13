"""FastAPI entrypoint for the create_ticket tool."""
from tool_base.main import build_app

from .tool import CreateTicket

app = build_app(CreateTicket())
