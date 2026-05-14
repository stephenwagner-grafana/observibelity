"""FastAPI entrypoint for add_to_cart."""
from tool_base.main import build_app

from .tool import AddToCart

app = build_app(AddToCart())
