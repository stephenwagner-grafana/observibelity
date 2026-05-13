"""Emitters — turn a validated UseCase into derived chart artifacts.

Each emitter is responsible for one artifact kind. The Compiler runs all of
them in sequence and merges the resulting {kind: path} maps.
"""
from .alert import AlertEmitter
from .dashboard import DashboardEmitter
from .evaluator import EvaluatorEmitter
from .registry_row import RegistryRowEmitter
from .scenario import ScenarioEmitter
from .slo import SLOEmitter

__all__ = [
    "AlertEmitter",
    "DashboardEmitter",
    "EvaluatorEmitter",
    "RegistryRowEmitter",
    "ScenarioEmitter",
    "SLOEmitter",
]
