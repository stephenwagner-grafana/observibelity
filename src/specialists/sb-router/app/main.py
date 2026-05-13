"""FastAPI entrypoint for sb-router."""
from specialist_base.main import build_app

from .specialist import SbRouter

app = build_app(SbRouter())
