"""FastAPI entrypoint for the geo_lookup tool."""
from tool_base.main import build_app

from .tool import GeoLookup

app = build_app(GeoLookup())
