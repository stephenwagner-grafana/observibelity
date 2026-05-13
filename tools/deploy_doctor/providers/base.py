"""Provider base class and shared data types.

This module is intentionally dependency-free so the llm-gateway can vendor it
without dragging in `anthropic` or `httpx`. Concrete providers live in
sibling modules.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum


class Urgency(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


@dataclass
class Suggestion:
    """One concrete suggestion the diagnoser returns to the user."""
    text: str
    command: str | None = None
    urgency: Urgency = Urgency.MEDIUM
    confidence: float = 0.5  # 0.0–1.0


class Provider(ABC):
    """Base class for LLM providers. Same abstraction used by the llm-gateway."""

    def __init__(self, config: dict | None = None) -> None:
        self.config = config or {}

    @abstractmethod
    def diagnose(self, context: dict, system_prompt: str) -> list[Suggestion]:
        """Given context (kubectl events, helm status, etc.), return suggestions."""
        ...
