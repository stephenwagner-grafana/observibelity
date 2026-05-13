"""FastAPI entrypoint for sb-it-troubleshoot."""
from specialist_base.main import build_app

from .specialist import SbItTroubleshoot

app = build_app(SbItTroubleshoot())
