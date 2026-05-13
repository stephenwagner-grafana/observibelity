"""FastAPI entrypoint for the get_inventory tool."""
from tool_base.main import build_app

from .tool import GetInventory

app = build_app(GetInventory())
