"""FastAPI entrypoint for the create_expense tool."""
from tool_base.main import build_app

from .tool import CreateExpense

app = build_app(CreateExpense())
