"""observibelity-tool-base — shared microservice runtime for ObserVIBElity tools."""
from .tool import Tool
from .main import build_app

__all__ = ["Tool", "build_app"]
__version__ = "0.2.0"
