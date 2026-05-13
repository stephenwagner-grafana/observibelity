"""FastAPI entrypoint for nc-fulfillment-orchestrator."""
from specialist_base.main import build_app

from .specialist import NcFulfillmentOrchestrator

app = build_app(NcFulfillmentOrchestrator())
