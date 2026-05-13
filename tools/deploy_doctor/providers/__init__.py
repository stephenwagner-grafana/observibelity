"""Provider plugins for deploy-doctor.

The same Provider abstraction is re-used by the eventual llm-gateway, which
is why the factory + base class live here rather than inline in __main__.py.
"""
from .base import Provider, Suggestion


def make_provider(name: str) -> Provider:
    """Factory: resolves a provider name to an instance."""
    if name == "anthropic":
        from .anthropic import AnthropicProvider
        return AnthropicProvider()
    elif name == "ollama":
        from .ollama import OllamaProvider
        return OllamaProvider()
    else:
        raise ValueError(f"Unknown provider: {name}")


__all__ = ["Provider", "Suggestion", "make_provider"]
