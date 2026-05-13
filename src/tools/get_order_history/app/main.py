"""FastAPI entrypoint for the get_order_history tool."""
from tool_base.main import build_app

from .tool import GetOrderHistory

app = build_app(GetOrderHistory())
