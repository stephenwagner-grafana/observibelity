"""FastAPI entrypoint for the get_employee_history tool."""
from tool_base.main import build_app

from .tool import GetEmployeeHistory

app = build_app(GetEmployeeHistory())
