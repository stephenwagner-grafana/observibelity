"""FastAPI entrypoint for sb-escalator."""
from specialist_base.main import build_app

from .specialist import SbEscalator

app = build_app(SbEscalator())
