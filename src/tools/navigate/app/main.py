"""FastAPI entrypoint for navigate."""
from tool_base.main import build_app

from .tool import Navigate

app = build_app(Navigate())
