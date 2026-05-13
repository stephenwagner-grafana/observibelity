"""FastAPI entrypoint for sb-expense-helper."""
from specialist_base.main import build_app

from .specialist import SbExpenseHelper

app = build_app(SbExpenseHelper())
