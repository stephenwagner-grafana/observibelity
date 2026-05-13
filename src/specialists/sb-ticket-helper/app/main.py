"""FastAPI entrypoint for sb-ticket-helper."""
from specialist_base.main import build_app

from .specialist import SbTicketHelper

app = build_app(SbTicketHelper())
