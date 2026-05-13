"""FastAPI entrypoint for the reset_password tool."""
from tool_base.main import build_app

from .tool import ResetPassword

app = build_app(ResetPassword())
