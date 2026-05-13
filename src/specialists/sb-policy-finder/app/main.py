"""FastAPI entrypoint for sb-policy-finder."""
from specialist_base.main import build_app

from .specialist import SbPolicyFinder

app = build_app(SbPolicyFinder())
