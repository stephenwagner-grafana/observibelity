"""FastAPI entrypoint for nc-fraud-detector."""
from specialist_base.main import build_app

from .specialist import NcFraudDetector

app = build_app(NcFraudDetector())
