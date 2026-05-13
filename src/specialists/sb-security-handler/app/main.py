"""FastAPI entrypoint for sb-security-handler."""
from specialist_base.main import build_app

from .specialist import SbSecurityHandler

app = build_app(SbSecurityHandler())
