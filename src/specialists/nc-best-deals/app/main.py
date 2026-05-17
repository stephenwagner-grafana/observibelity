"""FastAPI entrypoint for nc-best-deals."""
from specialist_base.main import build_app

from .specialist import NcBestDeals

app = build_app(NcBestDeals())
