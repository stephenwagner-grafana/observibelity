"""Anthropic (Claude) provider.

Phase 0: signature locked, body raises so callers can see a clear "Phase 1"
message rather than failing deep inside the SDK with a missing API key.

Phase 1: uncomment the sketch, add response parsing, and wire prompt caching
on the system block per the claude-api skill.
"""
from __future__ import annotations

import os

from .base import Provider, Suggestion


class AnthropicProvider(Provider):
    """Claude-backed diagnoser."""

    DEFAULT_MODEL = "claude-haiku-4-5-20251001"

    def __init__(self, config: dict | None = None) -> None:
        super().__init__(config)
        cfg = config or {}
        self.api_key = cfg.get("api_key") or os.environ.get("ANTHROPIC_API_KEY")
        self.model = cfg.get("model", self.DEFAULT_MODEL)

    def diagnose(self, context: dict, system_prompt: str) -> list[Suggestion]:
        # Phase 0: signature locked, body raises.
        raise NotImplementedError(
            "AnthropicProvider.diagnose() lands in Phase 1."
        )

        # ------------------------------------------------------------------
        # Phase 1 sketch:
        # ------------------------------------------------------------------
        # import json
        # from anthropic import Anthropic
        # client = Anthropic(api_key=self.api_key)
        # response = client.messages.create(
        #     model=self.model,
        #     max_tokens=2000,
        #     system=system_prompt,
        #     messages=[{"role": "user", "content": json.dumps(context)}],
        # )
        # return self._parse_suggestions(response.content[0].text)
