"""FastAPI entrypoint for verify_inventory."""
from tool_base.main import build_app

from .tool import VerifyInventory

app = build_app(VerifyInventory())
