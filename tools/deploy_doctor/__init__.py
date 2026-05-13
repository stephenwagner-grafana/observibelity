"""deploy-doctor: diagnostic collector + LLM-driven diagnoser for ObserVIBElity deployments."""
from .collect import Collector
from .diagnose import Diagnoser
from .providers.base import Provider, Suggestion

__all__ = ["Collector", "Diagnoser", "Provider", "Suggestion"]
__version__ = "0.1.0"
