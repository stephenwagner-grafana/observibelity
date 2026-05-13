"""Ollama provider.

Phase 0: signature locked, body raises so a misconfigured OLLAMA_BASE_URL
doesn't produce a confusing httpx connection error.

Phase 1: uncomment the sketch and add response parsing.
"""
from __future__ import annotations

import os

from .base import Provider, Suggestion


class OllamaProvider(Provider):
    """Ollama-backed diagnoser for users running a local model."""

    DEFAULT_MODEL = "llama3.1:8b"
    DEFAULT_BASE_URL = "http://localhost:11434"

    def __init__(self, config: dict | None = None) -> None:
        super().__init__(config)
        cfg = config or {}
        self.base_url = (
            cfg.get("base_url")
            or os.environ.get("OLLAMA_BASE_URL")
            or self.DEFAULT_BASE_URL
        )
        self.model = cfg.get("model", self.DEFAULT_MODEL)

    def diagnose(self, context: dict, system_prompt: str) -> list[Suggestion]:
        # Phase 0: signature locked, body raises.
        raise NotImplementedError(
            "OllamaProvider.diagnose() lands in Phase 1."
        )

        # ------------------------------------------------------------------
        # Phase 1 sketch:
        # ------------------------------------------------------------------
        # import json
        # import httpx
        # response = httpx.post(
        #     f"{self.base_url}/api/chat",
        #     json={
        #         "model": self.model,
        #         "stream": False,
        #         "messages": [
        #             {"role": "system", "content": system_prompt},
        #             {"role": "user", "content": json.dumps(context)},
        #         ],
        #     },
        #     timeout=120,
        # )
        # response.raise_for_status()
        # data = response.json()
        # return self._parse_suggestions(data["message"]["content"])
