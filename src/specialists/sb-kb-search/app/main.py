"""FastAPI entrypoint for sb-kb-search."""
from specialist_base.main import build_app

from .specialist import SbKbSearch

app = build_app(SbKbSearch())
