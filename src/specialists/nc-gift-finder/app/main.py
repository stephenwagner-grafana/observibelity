"""FastAPI entrypoint for nc-gift-finder."""
from specialist_base.main import build_app

from .specialist import NcGiftFinder

app = build_app(NcGiftFinder())
