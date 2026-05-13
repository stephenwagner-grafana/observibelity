"""FastAPI entrypoint for sb-hiring-helper."""
from specialist_base.main import build_app

from .specialist import SbHiringHelper

app = build_app(SbHiringHelper())
