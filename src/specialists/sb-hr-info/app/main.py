"""FastAPI entrypoint for sb-hr-info."""
from specialist_base.main import build_app

from .specialist import SbHrInfo

app = build_app(SbHrInfo())
