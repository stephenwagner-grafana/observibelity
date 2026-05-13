"""FastAPI entrypoint for sb-employee-info."""
from specialist_base.main import build_app

from .specialist import SbEmployeeInfo

app = build_app(SbEmployeeInfo())
