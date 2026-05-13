"""LLM-driven diagnoser.

Phase 0: signature locked, body raises NotImplementedError so callers see a
clear "Phase 1 only" message.

Phase 1: takes the Collector output dict, hands it to a Provider, and returns
a structured DiagnoseResult that __main__.py renders for the user.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .collect import Collector
from .providers.base import Provider, Suggestion

SYSTEM_PROMPT = (
    "You are diagnosing an ObserVIBElity (AI observability demo) deployment "
    "failure on Kubernetes. Read the kubectl events, helm status, and pod "
    "logs. Identify the first failure. Suggest concrete commands the user "
    "can run to fix it. Never recommend destructive operations without high "
    "confidence."
)


@dataclass
class DiagnoseResult:
    """Structured output of a diagnosis run."""
    summary: str
    suggestions: list[Suggestion] = field(default_factory=list)


class Diagnoser:
    """Drives a Provider with collected diagnostics."""

    def __init__(self, collector: Collector, provider: Provider) -> None:
        self.collector = collector
        self.provider = provider

    def diagnose(self) -> DiagnoseResult:
        # Phase 0: locked signature, no real call.
        raise NotImplementedError(
            "Diagnose mode is Phase 1. Use --collect-only for now."
        )

        # ------------------------------------------------------------------
        # Phase 1 sketch — uncomment when the Provider implementations land.
        # ------------------------------------------------------------------
        # context = self.collector.collect_all_as_dict()
        # suggestions = self.provider.diagnose(context, SYSTEM_PROMPT)
        # summary = (
        #     f"Inspected {len(context)} diagnostic sources. "
        #     f"Provider returned {len(suggestions)} suggestion(s)."
        # )
        # return DiagnoseResult(summary=summary, suggestions=suggestions)
