"""FastAPI entrypoint for the place_order tool."""
from tool_base.main import build_app

from .tool import PlaceOrder

app = build_app(PlaceOrder())
