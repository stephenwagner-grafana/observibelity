"""FastAPI entrypoint for the request_access tool."""
from tool_base.main import build_app

from .tool import RequestAccess

app = build_app(RequestAccess())
